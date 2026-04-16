import uuid
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_db
from src.db.models import Meeting, MeetingStatus, User
from src.services.s3 import s3_service
from src.config import Settings, get_settings
from src.tasks import process_audio_task

router = APIRouter()


@router.post("/upload", status_code=202)
async def upload_media(
    file: UploadFile = File(...),
    language: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    """
    Accept media file upload, store it in object storage,
    and enqueue background speech processing task.

    Returns:
        meeting_id and celery task_id.
    """

    file_ext = Path(file.filename).suffix.lower()

    if file_ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format. Allowed: {settings.ALLOWED_EXTENSIONS}"
        )

    # Create meeting record
    new_meeting = Meeting(
        title=file.filename,
        storage_file_path="",
        owner_id=uuid.UUID(settings.ANONYMOUS_USER_ID),
        status=MeetingStatus.UPLOADED
    )

    db.add(new_meeting)
    await db.commit()
    await db.refresh(new_meeting)

    storage_filename = f"{new_meeting.id}{file_ext}"

    try:
        # Upload media to object storage
        await s3_service.upload_streaming(file.file, storage_filename)

        # Update status and enqueue processing task
        new_meeting.storage_file_path = storage_filename
        new_meeting.status = MeetingStatus.PROCESSING

        task = process_audio_task.delay(
            meeting_id=str(new_meeting.id),
            storage_path=storage_filename,
            language=language
        )

        new_meeting.celery_task_id = task.id
        await db.commit()

        return {
            "meeting_id": new_meeting.id,
            "task_id": task.id
        }

    except Exception:
        await db.commit()
        raise HTTPException(
            status_code=500,
            detail="Internal processing error"
        )


@router.get("/meetings/{meeting_id}")
async def get_meeting(
    meeting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve processing status and transcript data for a meeting.
    """

    meeting = await db.get(Meeting, meeting_id)

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    return {
        "id": meeting.id,
        "status": meeting.status,
        "title": meeting.title,
        "transcript_data": meeting.transcript_data
    }


@router.post("/debug/create-test-user", tags=["debug"])
async def create_test_user(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    """
    Initialize database with a default system user
    for development and testing purposes.
    """

    user_id = uuid.UUID(settings.ANONYMOUS_USER_ID)

    from sqlalchemy import select
    existing = await db.execute(select(User).where(User.id == user_id))

    if existing.scalar_one_or_none():
        return {"status": "exists"}

    db.add(User(
        id=user_id,
        email="test@example.com",
        hashed_password="init",
        full_name="System User"
    ))

    await db.commit()

    return {"status": "created"}