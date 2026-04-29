import os
import uuid
import asyncio
from pathlib import Path
from typing import Optional
from celery import Task

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import update

from src.celery_app import celery_app
from src.logger import setup_logger
from src.db.models import Meeting, MeetingStatus
from src.services.s3 import s3_service
from src.services.ml_pipeline import ml_pipeline
from src.config import get_settings
logger = setup_logger("worker")
settings = get_settings()


# --- 1. ИЗОЛИРОВАННЫЕ АСИНХРОННЫЕ "ВСПЫШКИ" ---

async def _download_s3_isolated(storage_path: str, local_path: str):
    """Отдельный цикл для скачивания."""
    await s3_service.download_file(storage_path, local_path)


async def _update_db_isolated(meeting_id: str, data: dict):
    """Отдельный цикл для работы с БД."""
    parsed_uuid = uuid.UUID(meeting_id)
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI, poolclass=NullPool)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_maker() as session:
            query = update(Meeting).where(Meeting.id == parsed_uuid).values(**data)
            await session.execute(query)
            await session.commit()
    except Exception as e:
        logger.error(f"DB Error for {meeting_id}: {e}")
    finally:
        await engine.dispose()


# --- 2. СИНХРОННЫЙ ВОРКЕР ---

class BaseTask(Task):
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        meeting_id = kwargs.get("meeting_id") or (args[0] if args else None)
        logger.error(f"Task {task_id} failed: {exc}")
        if meeting_id:
            asyncio.run(_update_db_isolated(meeting_id, {"status": MeetingStatus.FAILED}))
        super().on_failure(exc, task_id, args, kwargs, einfo)


@celery_app.task(bind=True, base=BaseTask, name="process_audio_task")
def process_audio_task(self, meeting_id: str, storage_path: str, language: Optional[str] = None):
    """
    Главная задача. Она СИНХРОННАЯ.
    Никаких долгих Event Loops во время ML вычислений!
    """
    logger.info(f"--- [TASK STARTED] ID: {meeting_id} ---")

    temp_dir = Path(settings.UPLOAD_DIR)
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Файл защищен от Race Condition уникальным ID
    local_path = temp_dir / f"orig_{meeting_id}.audio"

    try:
        # ЭТАП 1: Скачивание (открыли петлю, скачали, закрыли петлю)
        logger.info(f"[{meeting_id}] 1. Downloading audio...")
        asyncio.run(_download_s3_isolated(storage_path, str(local_path)))

        # ЭТАП 2: Нейросети (строго синхронно, процессор занят, асинхронности нет)
        logger.info(f"[{meeting_id}] 2. ML Pipeline working...")
        result = ml_pipeline.process(str(local_path), unique_id=meeting_id)

        # ЭТАП 3: Сохранение (открыли новую петлю, записали, закрыли петлю)
        logger.info(f"[{meeting_id}] 3. ML Done! Saving to DB...")
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

        asyncio.run(_update_db_isolated(meeting_id, {
            "status": MeetingStatus.COMPLETED,
            "transcript_data": transcript_data,
            "speakers_map": {spk: spk for spk in result["speakers"]}
        }))

    except Exception as e:
        logger.error(f"[{meeting_id}] CRITICAL ERROR: {str(e)}")
        raise e

    finally:
        # Очистка диска
        if local_path.exists():
            local_path.unlink()