import os
import uuid
import asyncio
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
from sqlalchemy import update


logger = setup_logger("worker")
settings = get_settings()


async def update_meeting_status(meeting_id: str, data: dict):
    """Вспомогательная функция для обновления статуса в БД."""

    async with async_session_maker() as session:
        query = update(Meeting).where(Meeting.id == uuid.UUID(meeting_id)).values(**data)
        await session.execute(query)
        await session.commit()
        logger.info(f"Database updated for meeting {meeting_id}: {data.get('status')}")


class BaseTask(Task):
    """Базовый класс для автоматического логирования ошибок."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        meeting_id = args[0] if args else "unknown"
        logger.error(f"Task {task_id} failed: {exc}")
        asyncio.run(update_meeting_status(meeting_id, {"status": MeetingStatus.FAILED}))
        super().on_failure(exc, task_id, args, kwargs, einfo)


async def _process_audio_logic(meeting_id: str, storage_path: str, language: Optional[str] = None):
    # Используем временную папку для работы с тяжелыми файлами.
    temp_dir = Path(settings.UPLOAD_DIR)
    temp_dir.mkdir(parents=True, exist_ok=True)
    local_path = temp_dir / f"orig_{storage_path}"

    try:
        logger.info(f"[Task {meeting_id}] Downloading from S3: {storage_path}")
        
        await s3_service.download_file(storage_path, str(local_path))

        logger.info(f"[Task {meeting_id}] Executing ML pipeline (GigaAM + Pyannote)...")

        # Тяжелый ML процесс в отдельном потоке, чтобы не блокировать asyncio.
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            ml_pipeline.process,
            str(local_path)
        )

        logger.info(f"[Task {meeting_id}] Pipeline finished | RTF={result['rtf']:.3f}")

        transcript_data = {
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

        await update_meeting_status(meeting_id, {
            "status": MeetingStatus.COMPLETED,
            "transcript_data": transcript_data
        })

    except Exception as e:
        logger.error(f"[Task {meeting_id}] Processing failed: {str(e)}", exc_info=True)
        await update_meeting_status(meeting_id, {"status": MeetingStatus.FAILED})
        raise e

    finally:
        if local_path.exists():
            os.remove(local_path)
            logger.info(f"[Task {meeting_id}] Temporary file removed")


@celery_app.task(bind=True, base=BaseTask, name="process_audio_task")
def process_audio_task(self, meeting_id: str, storage_path: str, language: Optional[str] = None):
    """Точка входа Celery."""

    logger.info(f"[Celery Task] Started job for meeting: {meeting_id}")
    return asyncio.run(_process_audio_logic(meeting_id, storage_path, language))
