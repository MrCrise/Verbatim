import uuid
import asyncio
import os
from pathlib import Path
from typing import Optional
from celery import Task

from src.celery_app import celery_app
from src.logger import setup_logger
from src.db.database import async_session_maker
from src.db.models import Meeting, MeetingStatus
from src.services.s3 import s3_service
from src.services.ml_pipeline import ml_pipeline
from src.config import get_settings

logger = setup_logger("worker")
settings = get_settings()


async def _process_audio_logic(
    meeting_id: str,
    storage_path: str,
    language: Optional[str] = None
):
    """
    Core audio processing routine executed inside an async context.

    Workflow:
    1. Download file from object storage (S3/MinIO)
    2. Run ML speech processing pipeline (ASR + diarization)
    3. Persist structured transcript into database
    4. Clean up temporary files
    """

    temp_dir = Path(settings.UPLOAD_DIR)
    temp_dir.mkdir(parents=True, exist_ok=True)
    local_path = temp_dir / f"orig_{storage_path}"

    async with async_session_maker() as session:
        try:
            logger.info(f"[Task {meeting_id}] Downloading from storage: {storage_path}")

            file_bytes = await s3_service.download_file(storage_path)

            with open(local_path, "wb") as f:
                f.write(file_bytes)

            logger.info(f"[Task {meeting_id}] File stored locally: {local_path}")

            logger.info(f"[Task {meeting_id}] Executing ML pipeline...")

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                ml_pipeline.process,
                str(local_path)
            )

            logger.info(
                f"[Task {meeting_id}] Pipeline finished | RTF={result['rtf']:.3f}"
            )

            meeting = await session.get(Meeting, uuid.UUID(meeting_id))

            if meeting:
                meeting.status = MeetingStatus.COMPLETED

                meeting.transcript_data = {
                    "speakers": result["speakers"],
                    "segments": result["segments"],
                    "full_text": result["full_text"],
                    "metadata": {
                        "duration_sec": result["duration_sec"],
                        "runtime_sec": result["runtime_sec"],
                        "rtf": result["rtf"],
                        "model": result["metadata"]["model"],
                        "device": result["metadata"]["device"],
                        "language": language or "ru",
                    }
                }

                await session.commit()
                logger.info(f"[Task {meeting_id}] Results saved to database")

            else:
                logger.error(f"[Task {meeting_id}] Meeting record not found")

        except Exception as e:
            logger.error(f"[Task {meeting_id}] Processing failed", exc_info=True)

            meeting = await session.get(Meeting, uuid.UUID(meeting_id))
            if meeting:
                meeting.status = MeetingStatus.FAILED
                await session.commit()

            raise e

        finally:
            if local_path.exists():
                os.remove(local_path)
                logger.info(f"[Task {meeting_id}] Temporary file removed")


@celery_app.task(bind=True, name="process_audio_task")
def process_audio_task(
    self,
    meeting_id: str,
    storage_path: str,
    language: Optional[str] = None
):
    """
    Celery task entry point.

    Bridges synchronous Celery worker execution with
    asynchronous processing logic.
    """
    logger.info(f"[Celery Task] Received job: {meeting_id}")
    return asyncio.run(
        _process_audio_logic(meeting_id, storage_path, language)
    )