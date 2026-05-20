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


async def _download_s3_isolated(storage_path: str, local_path: str):
    """Отдельный цикл для скачивания файла."""

    await s3_service.download_file(storage_path, local_path)


async def _update_db_isolated(meeting_id: str, data: dict):
    """
    Отдельный цикл для работы с БД.
    Создаем временный engine с NullPool, чтобы избежать конфликтов пула в Celery.
    """

    local_engine = create_async_engine(
        settings.SQLALCHEMY_DATABASE_URI, 
        poolclass=NullPool
    )
    local_session_maker = async_sessionmaker(
        local_engine, 
        class_=AsyncSession, 
        expire_on_commit=False
    )

    try:
        parsed_uuid = uuid.UUID(meeting_id)
        async with local_session_maker() as session:
            query = update(Meeting).where(Meeting.id == parsed_uuid).values(**data)
            await session.execute(query)
            await session.commit()
            logger.info(f"Database updated for meeting {meeting_id}: {data.get('status')}")
    except Exception as e:
        logger.error(f"Failed to update meeting {meeting_id}: {e}")
    finally:
        await local_engine.dispose()


class BaseTask(Task):
    """Базовый класс для автоматического логирования ошибок."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        meeting_id = kwargs.get("meeting_id")
        if not meeting_id and args:
            meeting_id = args[0]

        logger.error(f"Task {task_id} failed: {exc}")

        if meeting_id:
            try:
                asyncio.run(_update_db_isolated(meeting_id, {"status": MeetingStatus.FAILED}))
            except Exception as db_exc:
                logger.error(f"Failed to update DB inside on_failure: {db_exc}")

        super().on_failure(exc, task_id, args, kwargs, einfo)


@celery_app.task(bind=True, base=BaseTask, name="process_audio_task")
def process_audio_task(self, meeting_id: str, storage_path: str, language: Optional[str] = None):
    """
    Главная синхронная задача Celery.
    Открывает Event Loop только для I/O операций.
    """

    logger.info(f"[{meeting_id}] Downloading from S3: {storage_path}")

    temp_dir = Path(settings.UPLOAD_DIR)
    temp_dir.mkdir(parents=True, exist_ok=True)
    local_path = temp_dir / f"orig_{meeting_id}.audio"

    try:
        logger.info(f"[{meeting_id}] Step 1. Downloading from S3...")
        asyncio.run(_download_s3_isolated(storage_path, str(local_path)))

        logger.info(f"[{meeting_id}] Step 2. Running ML pipeline...")
        result = ml_pipeline.process(str(local_path))

        logger.info(f"[{meeting_id}] Pipeline finished | RTF={result['rtf']:.3f}")
        logger.info(f"[{meeting_id}] Step 3. Saving results to DB...")

        transcript_data = {
            "speakers": result["speakers"],
            "segments": result["segments"],
            "full_text": result["full_text"],
            "metadata": {
                **result["metadata"],
                "language": language or "ru",
                "duration_sec": result["duration_sec"],
                "runtime_sec": result["runtime_sec"],
                "rtf": result["rtf"],
            }
        }

        speakers_map = {spk: spk for spk in result["speakers"]}

        asyncio.run(_update_db_isolated(meeting_id, {
            "status": MeetingStatus.COMPLETED,
            "transcript_data": transcript_data,
            "speakers_map": speakers_map,
            "duration_sec": result["duration_sec"]
        }))

    except Exception as e:
        logger.error(f"[{meeting_id}] Pipeline error: {str(e)}")
        raise e

    finally:
        if local_path.exists():
            local_path.unlink()
            logger.info(f"Cleaned up local file: {local_path}")
