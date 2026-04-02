import uuid
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.dependencies import get_current_user
from src.db.database import get_db
from src.db.models import Meeting, MeetingStatus, User
from src.services.s3 import s3_service
from src.logger import setup_logger
from src.config import Settings, get_settings
from src.tasks import process_audio_task


router = APIRouter()
logger = setup_logger(__name__)


@router.post("/upload", status_code=202)
async def upload_media(
    file: UploadFile = File(...),
    language: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    current_user: User = Depends(get_current_user)
):
    """
    Основной эндпоинт для загрузки медиаконтента.
    """

    # Кринж валидация расширения файла, поменять на список расширений из конфига.
    file_extension = Path(file.filename).suffix.lower()
    if not file.filename.endswith((".mp3", ".wav", ".m4a", ".mp4", ".webm")):
        raise HTTPException(status_code=400, detail="Unsupported file format")
    
    # Создание записи в БД.
    new_meeting = Meeting(
        title=file.filename,
        storage_file_path="",
        owner_id=current_user.id,  # Временная заглушка, пока нет авторизации.
        status=MeetingStatus.UPLOADED
    )
    db.add(new_meeting)
    await db.commit()
    await db.refresh(new_meeting)
    
    # Запись в S3.
    storage_filename = f"{new_meeting.id}{file_extension}"
    
    try:
        await s3_service.upload_streaming(file.file, storage_filename)

        new_meeting.storage_file_path = storage_filename
        new_meeting.status = MeetingStatus.PROCESSING

        task = process_audio_task.delay(
            meeting_id=str(new_meeting.id),
            storage_path=storage_filename,
            language=language
        )

        new_meeting.celery_task_id = task.id
        await db.commit()

        return {"meeting_id": new_meeting.id,
                "task_id": task.id}
    
    except Exception as e:
        import traceback
        logger.error(f"Upload failed: {str(e)}")
        logger.error(traceback.format_exc())
        await db.commit()
        raise HTTPException(status_code=500, detail="S3 Upload Error")
