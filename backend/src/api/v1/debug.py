import uuid
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.dependencies import get_current_user
from src.schemas import UserResponse
from src.db.database import get_db
from src.db.models import Meeting, MeetingStatus, User
from src.services.s3 import s3_service
from src.logger import setup_logger
from src.config import Settings, get_settings
from src.tasks import process_audio_task


router = APIRouter()
logger = setup_logger(__name__)


@router.post("/create-test-user", tags=["debug"])
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

@router.get("/me", response_model=UserResponse)
async def get_user_me(current_user: User = Depends(get_current_user)):
    """Возвращает информацию о текущем авторизованном пользователе."""
    return current_user
