import json
import time
import warnings
from pathlib import Path
from typing import Dict, List, Any
import os
import subprocess
import tempfile

import torch
import numpy as np
import soundfile as sf
import gigaam
from pyannote.audio import Pipeline as DiarizationPipeline
from huggingface_hub import login


from src.logger import setup_logger
from src.config import get_settings

warnings.filterwarnings("ignore")
logger = setup_logger("ml_pipeline")
settings = get_settings()

class MLPipeline:
    """
    End-to-end speech processing pipeline.

    Combines:
    - GigaAM v3_e2e_rnnt for automatic speech recognition (ASR)
    - Pyannote speaker-diarization-3.1 for speaker segmentation

    Designed for GPU-accelerated batch meeting processing.
    """
    def __init__(self):
        """
        Initialize pipeline configuration and runtime parameters.
        Models are loaded lazily to optimize worker startup time.
        """
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model_name = "v3_e2e_rnnt"
        self.chunk_sec = 20.0
        self.target_sr = 16000
        
        self.asr_model = None
        self.diar_pipeline = None
        
        logger.info(f"MLPipeline initialized | Device: {self.device}")

    def _load_models(self):
        """
        Lazily load ASR and diarization models.

        Ensures models are instantiated only once per worker process.
        """
        if self.asr_model is None:
            logger.info(f"Loading GigaAM {self.model_name}...")
            self.asr_model = gigaam.load_model(self.model_name)
        
        if self.diar_pipeline is None:
            logger.info("Loading pyannote diarization...")
            
            hf_token = settings.HF_TOKEN
            if not hf_token:
                raise RuntimeError("HF_TOKEN not set in environment")
            
            self.diar_pipeline = DiarizationPipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=hf_token
        )

        if self.diar_pipeline is None:
            raise RuntimeError(
                "Pyannote model returned None. "
                "You MUST accept the user agreements on HuggingFace:\n"
                "1. https://huggingface.co/pyannote/speaker-diarization-3.1\n"
                "2. https://huggingface.co/pyannote/segmentation-3.0\n"
                "Check your HF_TOKEN permissions as well."
            )

        self.diar_pipeline.to(torch.device(self.device))


    def preprocess_audio(self, audio_path: Path) -> tuple:
        """
        Convert any input audio/video file to mono 16kHz WAV format.

        Uses FFmpeg via subprocess for secure execution.
        Temporary files are automatically cleaned up.
        """
        logger.info(f"[Preprocess] Converting {audio_path.name} → WAV 16kHz mono")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            tmp_wav_path = Path(tmp_file.name)

        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i", str(audio_path),
                    "-ac", "1",
                    "-ar", "16000",
                    str(tmp_wav_path),
                    "-loglevel", "error",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            if result.returncode != 0:
                logger.error(f"FFmpeg error: {result.stderr.decode()}")
                raise RuntimeError("FFmpeg conversion failed")

            waveform, sr = sf.read(str(tmp_wav_path), dtype="float32")

            duration = len(waveform) / sr
            logger.info(f"[Preprocess] Duration: {duration:.1f}s")

            return waveform, sr

        finally:
            if tmp_wav_path.exists():
                tmp_wav_path.unlink()

    def split_into_chunks(self, waveform: np.ndarray, sr: int) -> List[tuple]:
        """
        Split waveform into fixed-length chunks for stable ASR decoding.
        """
        chunk_samples = int(self.chunk_sec * sr)
        chunks = []
        
        for i in range(0, len(waveform), chunk_samples):
            chunk = waveform[i:i + chunk_samples]
            offset = i / sr
            chunks.append((chunk, offset))
        
        logger.info(f"[Chunking] {len(chunks)} chunks x {self.chunk_sec}s")
        return chunks
    
    def run_asr(self, chunks: List[tuple], sr: int) -> Dict:
        """        
        Perform automatic speech recognition with word-level timestamps.

        Returns:
            - Full transcript
            - Word-level timing information
            - ASR runtime statistics
        """
        logger.info(f"[ASR] Starting ({len(chunks)} chunks)...")
        start_time = time.time()
        
        all_words = []
        full_text_parts = []
        
        for i, (chunk, offset) in enumerate(chunks, start=1):
            tmp_path = Path("/tmp/pipeline_chunk.wav")
            sf.write(str(tmp_path), chunk, sr)
            
            result = self.asr_model.transcribe(str(tmp_path), word_timestamps=True)
            chunk_text = result.text.strip()
            full_text_parts.append(chunk_text)
            
            for w in result.words:
                all_words.append({
                    "word": w.text,
                    "start": round(w.start + offset, 3),
                    "end": round(w.end + offset, 3),
                })
        
        runtime = time.time() - start_time
        logger.info(f"[ASR] Done in {runtime:.2f}s | Words: {len(all_words)}")
        
        return {
            "text": " ".join(full_text_parts),
            "words": all_words,
            "runtime_sec": round(runtime, 3),
        }
    
    def run_diarization(self, waveform: np.ndarray, sr: int) -> Dict:
        """
        Perform speaker diarization on full audio signal.

        Returns speaker segments with timestamps.
        """
        logger.info("[Diarization] Starting...")
        start_time = time.time()
        
        waveform_tensor = torch.tensor(waveform, dtype=torch.float32).unsqueeze(0)
        audio_input = {"waveform": waveform_tensor, "sample_rate": sr}
        
        annotation = self.diar_pipeline(audio_input)
        
        segments = []
        for turn, _, speaker in annotation.itertracks(yield_label=True):
            segments.append({
                "start": round(turn.start, 3),
                "end": round(turn.end, 3),
                "speaker": speaker,
            })
        
        runtime = time.time() - start_time
        speakers = sorted(set(s["speaker"] for s in segments))
        logger.info(f"[Diarization] Done in {runtime:.2f}s | Speakers: {speakers}")
        
        return {
            "segments": segments,
            "speakers": speakers,
            "runtime_sec": round(runtime, 3),
        }
    
    def merge_asr_diarization(self, asr_result: Dict, diar_result: Dict) -> List[Dict]:
        """
        Align word-level ASR output with speaker segments.
        """
        logger.info("[Merge] Merging words with speakers...")
        
        def find_speaker(word_start, word_end, diar_segments):
            word_mid = (word_start + word_end) / 2
            speakers = []
            for seg in diar_segments:
                if seg["start"] <= word_mid <= seg["end"]:
                    speakers.append(seg["speaker"])
            
            if not speakers:
                return "unknown"
            uniq = sorted(set(speakers))
            return uniq[0] if len(uniq) == 1 else uniq[0]
        
        merged_words = []
        for w in asr_result["words"]:
            if w["start"] is None or w["end"] is None:
                continue
            word = w["word"].strip()
            if not word:
                continue
            
            merged_words.append({
                "word": word,
                "start": w["start"],
                "end": w["end"],
                "speaker": find_speaker(w["start"], w["end"], diar_result["segments"]),
            })
        
        logger.info(f"[Merge] {len(merged_words)} words with speakers")
        return merged_words
    
    def build_segments(self, merged_words: List[Dict]) -> List[Dict]:
        """
        Construct coherent speaker segments from word-level alignment.
        """
        if not merged_words:
            return []
        
        segments = []
        current_speaker = merged_words[0]["speaker"]
        current_words = [merged_words[0]]
        
        for w in merged_words[1:]:
            if w["speaker"] == current_speaker:
                current_words.append(w)
            else:
                segments.append({
                    "speaker": current_speaker,
                    "start": current_words[0]["start"],
                    "end": current_words[-1]["end"],
                    "text": " ".join(cw["word"] for cw in current_words),
                    "words": current_words.copy(),
                })
                current_speaker = w["speaker"]
                current_words = [w]
        
        segments.append({
            "speaker": current_speaker,
            "start": current_words[0]["start"],
            "end": current_words[-1]["end"],
            "text": " ".join(cw["word"] for cw in current_words),
            "words": current_words.copy(),
        })
        
        MIN_WORDS = 3
        MIN_DURATION = 0.7 

        cleaned = []

        for seg in segments:
            duration = seg["end"] - seg["start"]
            word_count = len(seg["words"])

            if cleaned and (word_count < MIN_WORDS or duration < MIN_DURATION):
                cleaned[-1]["text"] += " " + seg["text"]
                cleaned[-1]["end"] = seg["end"]
                cleaned[-1]["words"].extend(seg["words"])
            else:
                cleaned.append(seg)

        for seg in cleaned:
            seg.pop("words", None)

        result = []

        for seg in cleaned:
            if result and result[-1]["speaker"] == seg["speaker"]:
                result[-1]["text"] += " " + seg["text"]
                result[-1]["end"] = seg["end"]
            else:
                result.append(seg)

        for seg in result:
            words = seg["text"].split()
            deduped = []
            for w in words:
                if not deduped or deduped[-1] != w:
                    deduped.append(w)
            seg["text"] = " ".join(deduped)

        return result
    
    def process(self, audio_path: str) -> Dict[str, Any]:
        """
        Execute full speech processing pipeline.

        Returns structured JSON-ready output with:
        - Transcript
        - Speaker segments
        - Performance metrics
        """
        audio_path = Path(audio_path)
        logger.info(f"[Pipeline] Processing: {audio_path.name}")
        
        pipeline_start = time.time()
        
        self._load_models()
        
        waveform, sr = self.preprocess_audio(audio_path)
        duration_sec = len(waveform) / sr
        
        chunks = self.split_into_chunks(waveform, sr)
        asr_result = self.run_asr(chunks, sr)
        diar_result = self.run_diarization(waveform, sr)
        merged_words = self.merge_asr_diarization(asr_result, diar_result)
        segments = self.build_segments(merged_words)
        
        total_runtime = time.time() - pipeline_start
        rtf = total_runtime / duration_sec
        
        logger.info(f"[Pipeline] Done | Runtime: {total_runtime:.2f}s | RTF: {rtf:.3f}")
        
        return {
            "speakers": diar_result["speakers"],
            "segments": segments,
            "full_text": asr_result["text"],
            "duration_sec": round(duration_sec, 3),
            "runtime_sec": round(total_runtime, 3),
            "rtf": round(rtf, 4),
            "metadata": {
                "model": self.model_name,
                "device": self.device,
                "asr_runtime_sec": asr_result["runtime_sec"],
                "diar_runtime_sec": diar_result["runtime_sec"],
            }
        }


ml_pipeline = MLPipeline()