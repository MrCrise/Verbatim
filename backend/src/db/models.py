import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import enum
from src.db.database import Base

 
class MeetingStatus(str, enum.Enum):
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    meetings = relationship("Meeting", back_populates="owner", cascade="all, delete-orphan")


class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    
    celery_task_id = Column(String(255), nullable=True) 
    
    status = Column(SQLEnum(MeetingStatus), default=MeetingStatus.UPLOADED)
    
    # Имя файла в хранилище (S3 / MinIO).
    storage_file_path = Column(String(255), nullable=False) 
    
    # Сырой массив: [{"start": 0, "end": 2, "speaker": "SPEAKER_00", "text": "Привет"}]
    transcript_data = Column(JSONB, nullable=True) 
    
    # Карта переименования: {"SPEAKER_00": "Иван", "SPEAKER_01": "Ольга"}
    speakers_map = Column(JSONB, nullable=True, default=dict)

    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    owner = relationship("User", back_populates="meetings")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
