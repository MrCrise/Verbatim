import gc
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
        self.model_name = settings.ML_GIGAAM_MODEL_NAME
        self.chunk_sec = settings.ML_ASR_CHUNK_SEC
        self.target_sr = settings.ML_TARGET_SR
        self.overlap_sec = settings.ML_ASR_OVERLAP_SEC

        self.min_speakers = settings.ML_DIAR_MIN_SPEAKERS
        self.max_speakers = settings.ML_DIAR_MAX_SPEAKERS
        
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
            try:
                self.asr_model = gigaam.load_model(self.model_name)
            except AssertionError:
                import shutil
                cache_path = Path("/root/.cache/gigaam")
                if cache_path.exists():
                    shutil.rmtree(cache_path)
                logger.warning("GigaAM cache cleared. Retrying model load...")
                self.asr_model = gigaam.load_model(self.model_name)

        if self.diar_pipeline is None:
            logger.info("Loading pyannote diarization...")

            hf_token = settings.HF_TOKEN
            if not hf_token:
                raise RuntimeError("HF_TOKEN not set in environment")

            loaded = False

            try:
                self.diar_pipeline = DiarizationPipeline.from_pretrained(
                    settings.ML_DIAR_PIPELINE_NAME,
                    token=hf_token,
                )
                loaded = True
            except TypeError:
                pass

            if not loaded:
                try:
                    self.diar_pipeline = DiarizationPipeline.from_pretrained(
                        settings.ML_DIAR_PIPELINE_NAME,
                        use_auth_token=hf_token,
                    )
                    loaded = True
                except TypeError:
                    pass

            if not loaded:
                from huggingface_hub import login
                login(token=hf_token, add_to_git_credential=False)
                self.diar_pipeline = DiarizationPipeline.from_pretrained(
                    settings.ML_DIAR_PIPELINE_NAME,
                )
                loaded = True

        if self.diar_pipeline is None:
            raise RuntimeError(
                "Pyannote model returned None. "
                "You MUST accept the user agreements on HuggingFace:\n"
                "1. https://huggingface.co/pyannote/speaker-diarization-3.1\n"
                "2. https://huggingface.co/pyannote/segmentation-3.0\n"
                "Check your HF_TOKEN permissions as well."
            )
            
        if self.diar_pipeline is not None:
            # Берём обновлённые параметры из конфига
            thr = settings.ML_DIAR_CLUSTER_THRESHOLD
            min_off = settings.ML_DIAR_MIN_DUR_OFF
            
            try:
                # ВАЖНО: убрали min_cluster_size, чтобы включить автоматическую калибровку Pyannote
                self.diar_pipeline.instantiate({
                    "clustering": {
                        "threshold": thr,
                    },
                    "segmentation": {
                        "min_duration_off": min_off,
                    },
                })
                logger.info(
                    f"[Diarization] Auto-calibration enabled | Params: threshold={thr}, min_duration_off={min_off}"
                )
            except Exception as e:
                logger.warning(f"[Diarization] Failed to instantiate custom params: {e}")
        
        self.diar_pipeline.to(torch.device(self.device))

    def preprocess_audio(self, audio_path: Path) -> tuple:
        """
        Convert any input audio/video file to mono 16kHz WAV format.

        Uses FFmpeg via subprocess for secure execution.
        Temporary files are automatically cleaned up.
        """
        logger.info(f"[Preprocess] Converting {audio_path.name}")

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
        Split waveform into overlapping chunks to reduce ASR boundary artifacts.
        Returns list of (chunk_waveform, offset_sec).
        """
        chunk_samples = int(self.chunk_sec * sr)
        overlap_samples = int(self.overlap_sec * sr)
        step = chunk_samples - overlap_samples
        if step <= 0:
            raise ValueError("overlap_sec must be smaller than chunk_sec")

        chunks = []
        for start in range(0, len(waveform), step):
            end = start + chunk_samples
            chunk = waveform[start:end]
            if len(chunk) == 0:
                break
            offset = start / sr
            chunks.append((chunk, offset))

        logger.info(
            f"[Chunking] {len(chunks)} chunks | chunk={self.chunk_sec}s overlap={self.overlap_sec}s"
        )
        return chunks

    def run_asr(self, chunks: List[tuple], sr: int) -> Dict:
        """
        Perform ASR on overlapping chunks and drop words that fall into the leading
        overlap region of each chunk (except the first one).
        """
        logger.info(f"[ASR] Starting ({len(chunks)} chunks)...")
        start_time = time.time()

        all_words = []
        full_text_parts = []

        for i, (chunk, offset) in enumerate(chunks):
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_chunk_file:
                tmp_path = Path(tmp_chunk_file.name)

            try:
                sf.write(str(tmp_path), chunk, sr)
                result = self.asr_model.transcribe(str(tmp_path), word_timestamps=True)
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()

            chunk_text = result.text.strip()
            if chunk_text:
                full_text_parts.append(chunk_text)

            drop_until = offset + (self.overlap_sec if i > 0 else 0.0)

            for w in result.words:
                abs_start = w.start + offset
                abs_end = w.end + offset

                if i > 0 and abs_end <= drop_until:
                    continue

                all_words.append({
                    "word": w.text,
                    "start": round(abs_start, 3),
                    "end": round(abs_end, 3),
                })

        runtime = time.time() - start_time
        logger.info(f"[ASR] Done in {runtime:.2f}s | Words: {len(all_words)}")

        full_text = " ".join(w["word"] for w in all_words)

        return {
            "text": full_text,
            "words": all_words,
            "runtime_sec": round(runtime, 3),
        }

    def run_diarization(self, waveform: np.ndarray, sr: int) -> Dict:
        """
        Perform speaker diarization on full audio signal (Pyannote).

        Post-processing:
        - merge consecutive same-speaker segments if gap is small
        - drop ultra-short segments considered noise
        """
        logger.info("[Diarization] Starting...")
        start_time = time.time()

        waveform_tensor = torch.tensor(waveform, dtype=torch.float32).unsqueeze(0)
        audio_input = {"waveform": waveform_tensor, "sample_rate": sr}

        with torch.no_grad():
            try:
                diar_out = self.diar_pipeline(
                    audio_input,
                    min_speakers=self.min_speakers,
                    max_speakers=self.max_speakers,
                )
            except TypeError:
                diar_out = self.diar_pipeline(audio_input)

        annotation = getattr(diar_out, "speaker_diarization", diar_out)

        segments = []
        for turn, _, speaker in annotation.itertracks(yield_label=True):
            segments.append({
                "start": round(turn.start, 3),
                "end": round(turn.end, 3),
                "speaker": speaker,
            })

        segments = sorted(segments, key=lambda x: (x["start"], x["end"]))

        MERGE_GAP = settings.ML_DIAR_SMOOTH_MERGE_GAP
        MIN_DUR = settings.ML_DIAR_SMOOTH_MIN_DUR


        smoothed: List[Dict] = []
        for seg in segments:
            dur = seg["end"] - seg["start"]
            if dur < MIN_DUR:
                continue

            if smoothed and seg["speaker"] == smoothed[-1]["speaker"]:
                gap = seg["start"] - smoothed[-1]["end"]
                if gap <= MERGE_GAP:
                    smoothed[-1]["end"] = seg["end"]
                    continue

            smoothed.append(seg)

        segments = smoothed

        runtime = time.time() - start_time
        speakers = sorted(set(s["speaker"] for s in segments))

        logger.info(
            f"[Diarization] Done in {runtime:.2f}s | Speakers: {speakers} | Segments: {len(segments)}"
        )

        diar_result = {
            "segments": segments,
            "speakers": speakers,
            "runtime_sec": round(runtime, 3),
        }
        logger.info("[Diarization] Starting filtering of ghost speakers...")
        diar_result = self._clean_ghost_speakers(diar_result, min_total_duration=1.8)

        return diar_result

    def merge_asr_diarization(self, asr_result: Dict, diar_result: Dict) -> List[Dict]:
        """
        Align word-level ASR output with speaker segments.
        """
        logger.info("[Merge] Merging words with speakers...")

        def find_speaker(word_start, word_end, diar_segments):
            best_speaker = "unknown"
            best_overlap = 0.0

            for seg in diar_segments:
                overlap = max(0.0, min(word_end, seg["end"]) - max(word_start, seg["start"]))
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_speaker = seg["speaker"]

            if best_overlap > 0.0:
                return best_speaker

            mid = (word_start + word_end) / 2
            TOL = settings.ML_WORD_SPEAKER_TOL
            nearest = None
            nearest_dist = 1e9

            for seg in diar_segments:
                if seg["start"] - TOL <= mid <= seg["end"] + TOL:
                    dist = 0.0 if seg["start"] <= mid <= seg["end"] else min(
                        abs(mid - seg["start"]), abs(mid - seg["end"])
                    )
                    if dist < nearest_dist:
                        nearest_dist = dist
                        nearest = seg["speaker"]

            return nearest if nearest is not None else "unknown"

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

        Post-processing policy:
        - Merge ONLY 'unknown' micro-segments into nearest neighbor
        - Merge consecutive same-speaker segments if gap is small
        - Do NOT merge short segments across different known speakers
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
                    "text": " ".join(x["word"] for x in current_words),
                    "word_count": len(current_words),
                })
                current_speaker = w["speaker"]
                current_words = [w]

        segments.append({
            "speaker": current_speaker,
            "start": current_words[0]["start"],
            "end": current_words[-1]["end"],
            "text": " ".join(x["word"] for x in current_words),
            "word_count": len(current_words),
        })

        MIN_UNKNOWN_WORDS = 3
        MIN_UNKNOWN_DUR = 0.7

        cleaned = []
        for seg in segments:
            dur = seg["end"] - seg["start"]
            is_unknown_micro = (
                seg["speaker"] == "unknown" and
                (seg["word_count"] < MIN_UNKNOWN_WORDS or dur < MIN_UNKNOWN_DUR)
            )

            if is_unknown_micro and cleaned:
                cleaned[-1]["text"] += " " + seg["text"]
                cleaned[-1]["end"] = seg["end"]
                cleaned[-1]["word_count"] += seg["word_count"]
            else:
                cleaned.append(seg)

        MAX_SAME_SPEAKER_GAP = 0.3

        result = []
        for seg in cleaned:
            if result and result[-1]["speaker"] == seg["speaker"]:
                gap = seg["start"] - result[-1]["end"]
                if gap <= MAX_SAME_SPEAKER_GAP:
                    result[-1]["text"] += " " + seg["text"]
                    result[-1]["end"] = seg["end"]
                    result[-1]["word_count"] += seg["word_count"]
                    continue
            result.append(seg)

        for seg in result:
            seg.pop("word_count", None)

        return result


    def build_segments_from_diarization(
        self,
        merged_words: List[Dict],
        diar_segments: List[Dict],
    ) -> List[Dict]:
        """
        Build transcript segments using diarization turns as boundaries.

        This reduces speaker fragmentation caused by word-level assignment jitter.
        """
        if not merged_words:
            return []

        import re
        valid_words = []
        for w in merged_words:
            word_text = w.get("word", "").strip()
            if re.search(r'[a-zA-Zа-яА-ЯёЁ0-9]', word_text):
                valid_words.append(w)

        if not valid_words:
            return []

        words = sorted(valid_words, key=lambda x: x["start"])
        
        result = []
        current_speaker = words[0]["speaker"]
        current_words = [words[0]]

        for w in words[1:]:
            if w["speaker"] == current_speaker:
                current_words.append(w)
            else:
                result.append({
                    "speaker": current_speaker,
                    "start": current_words[0]["start"],
                    "end": current_words[-1]["end"],
                    "text": " ".join(x["word"] for x in current_words).strip(),
                })
                current_speaker = w["speaker"]
                current_words = [w]

        result.append({
            "speaker": current_speaker,
            "start": current_words[0]["start"],
            "end": current_words[-1]["end"],
            "text": " ".join(x["word"] for x in current_words).strip(),
        })

        MAX_SAME_SPEAKER_GAP = settings.ML_SEG_MERGE_GAP
        
        smoothed = []
        for seg in result:
            if not seg["text"]:
                continue
                
            if smoothed and smoothed[-1]["speaker"] == seg["speaker"]:
                gap = seg["start"] - smoothed[-1]["end"]
                if gap <= MAX_SAME_SPEAKER_GAP:
                    smoothed[-1]["text"] += " " + seg["text"]
                    smoothed[-1]["end"] = seg["end"]
                    continue
            smoothed.append(seg)

        return smoothed

    def _clean_ghost_speakers(self, diar_result: Dict, min_total_duration: float = 1.8) -> Dict:
        """
        Finds speakers who have spoken for less than min_total_duration seconds,
        and removes them, moving their segments to the nearest legitimate speakers.
        """
        segments = diar_result["segments"]
        if not segments:
            return diar_result

        speaker_durations = {}
        for seg in segments:
            dur = seg["end"] - seg["start"]
            speaker_durations[seg["speaker"]] = speaker_durations.get(seg["speaker"], 0.0) + dur

        ghost_speakers = {spk for spk, dur in speaker_durations.items() if dur < min_total_duration}
        
        if not ghost_speakers:
            return diar_result

        logger.info(f"[Diarization Filter] False speakers found: {ghost_speakers}. Removing...")

        cleaned_segments = []
        for seg in segments:
            if seg["speaker"] in ghost_speakers:
                seg["speaker"] = "unknown" 
            cleaned_segments.append(seg)

        diar_result["segments"] = cleaned_segments
        diar_result["speakers"] = sorted(set(s["speaker"] for s in cleaned_segments if s["speaker"] != "unknown"))
        return diar_result

    def process(self, audio_path: str) -> Dict[str, Any]:
        """
        Execute full speech processing pipeline.

        Returns structured JSON-ready output with:
        - Transcript
        - Speaker segments
        - Performance metrics
        """
        try:
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
            segments = self.build_segments_from_diarization(merged_words, diar_result["segments"])

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
        finally:
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            logger.info("[Pipeline] GPU/RAM cache cleared")


ml_pipeline = MLPipeline()