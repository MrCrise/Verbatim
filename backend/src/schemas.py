from pydantic import BaseModel, EmailStr, UUID4, Field, ConfigDict
from datetime import datetime
from typing import Optional, List, Dict, Any
from src.db.models import MeetingStatus


# --- Токены ---
class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    email: Optional[str] = None

# --- Пользователи ---


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72,
                          description="Password (8-72 characters)")
    full_name: str


class UserResponse(BaseModel):
    id: UUID4
    email: EmailStr
    full_name: str
    is_admin: bool

    class Config:
        from_attributes = True

# --- Записи встреч ---


class MeetingBase(BaseModel):
    id: UUID4
    title: str
    status: MeetingStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# Схема для списка записей.


class MeetingSummary(MeetingBase):
    pass

# Полная схема для страницы конкретной записи.


class MeetingDetail(MeetingBase):
    transcript_data: Optional[List[Dict[str, Any]]] = None
    speakers_map: Dict[str, str]
    celery_task_id: Optional[str] = None
