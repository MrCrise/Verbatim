import uuid
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

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
    settings: Settings = Depends(get_settings)
):
    """
    Основной эндпоинт для загрузки медиаконтента.
    """

    # Валидация.
    file_extension = Path(file.filename).suffix.lower()

    # Кринж валидация, поменять на список расширений из конфига.
    if not file.filename.endswith((".mp3", ".wav", ".m4a", ".mp4")):
        raise HTTPException(status_code=400, detail="Unsupported file format")
    
    # Создание записи в БД.
    new_meeting = Meeting(
        title=file.filename,
        storage_file_path="",
        owner_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),  # Временная заглушка, пока нет авторизации.
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


@router.post("/debug/create-test-user", tags=["debug"])
async def create_test_user(db: AsyncSession = Depends(get_db)):
    """Создает тестового пользователя с нулевым UUID."""
    zero_uuid = uuid.UUID("00000000-0000-0000-0000-000000000000")
    
    result = await db.execute(select(User).where(User.id == zero_uuid))
    if result.scalar_one_or_none():
        return {"message": "User already exists"}
        
    test_user = User(
        id=zero_uuid,
        email="test@company.com",
        hashed_password="fake_hash",
        full_name="Тестовый Инженер",
        is_admin=True
    )
    db.add(test_user)
    await db.commit()
    return {"message": "Test user created", "id": zero_uuid}
