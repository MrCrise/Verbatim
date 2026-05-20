import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.db.database import get_db
from src.db.models import Meeting, User
from src.schemas import MeetingSummary, MeetingDetail, SpeakerUpdateRequest, SegmentUpdateRequest
from src.services.s3 import s3_service
from src.dependencies import get_current_user
from src.logger import setup_logger


router = APIRouter()
logger = setup_logger(__name__)


async def get_meeting_for_owner(meeting_id: uuid.UUID, db: AsyncSession, user_id: uuid.UUID):
    """Вспомогательная функция для проверки прав доступа к записи."""

    query = select(Meeting).where(Meeting.id == meeting_id)
    result = await db.execute(query)
    meeting = result.scalar_one_or_none()

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if meeting.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    return meeting


@router.get("/{meeting_id}/stream")
async def stream_audio(
    meeting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Эндпоинт для проигрывания аудио в плеере (стриминг)."""

    meeting = await get_meeting_for_owner(meeting_id, db, current_user.id)

    if not meeting.storage_file_path:
        raise HTTPException(status_code=400, detail="Audio file is not ready")

    async def s3_stream_generator():
        async with s3_service.get_s3_object(meeting.storage_file_path) as s3_response:
            async for chunk in s3_response['Body'].iter_chunks(chunk_size=1024*1024):
                yield chunk

    return StreamingResponse(
        s3_stream_generator(),
        media_type="audio/wav"
    )


@router.get("/{meeting_id}/download")
async def download_audio(
    meeting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Эндпоинт для скачивания оригинального файла"""

    meeting = await get_meeting_for_owner(meeting_id, db, current_user.id)

    async def s3_stream_generator():
        async with s3_service.get_s3_object(meeting.storage_file_path) as s3_response:
            async for chunk in s3_response['Body'].iter_chunks(chunk_size=1024*1024):
                yield chunk

    headers = {
        "Content-Disposition": f"attachment; filename={meeting.title}"
    }

    return StreamingResponse(
        s3_stream_generator(),
        media_type="application/octet-stream",
        headers=headers
    )


@router.get("/", response_model=List[MeetingSummary])
async def list_meetings(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Получить список всех встреч текущего пользователя."""

    query = (
        select(Meeting)
        .where(Meeting.owner_id == current_user.id)
        .order_by(Meeting.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    meetings = result.scalars().all()

    return meetings


@router.get("/{meeting_id}", response_model=MeetingDetail)
async def get_meeting_details(
    meeting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Получить подробную информацию о конкретной встрече (включая текст протокола)."""

    meeting = await get_meeting_for_owner(meeting_id, db, current_user.id)
    return meeting


@router.patch("/{meeting_id}/speakers")
async def update_speaker_name(
    meeting_id: uuid.UUID,
    payload: SpeakerUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Обновить имя спикера в карте speakers_map.
    """

    meeting = await get_meeting_for_owner(meeting_id, db, current_user.id)

    current_map = dict(meeting.speakers_map or {})
    current_map[payload.speaker_id] = payload.real_name

    meeting.speakers_map = current_map
    await db.commit()

    return {"status": "success", "speakers_map": meeting.speakers_map}


@router.patch("/{meeting_id}/segments")
async def update_segment_text(
    meeting_id: uuid.UUID,
    payload: SegmentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Исправить опечатку нейросети в конкретном сегменте текста.
    """

    meeting = await get_meeting_for_owner(meeting_id, db, current_user.id)
    
    if not meeting.transcript_data or "segments" not in meeting.transcript_data:
        raise HTTPException(status_code=400, detail="Transcript data is empty")
        
    segments = meeting.transcript_data["segments"]

    if payload.segment_index < 0 or payload.segment_index >= len(segments):
        raise HTTPException(status_code=400, detail="Invalid segment index")

    import copy
    new_transcript_data = copy.deepcopy(meeting.transcript_data)

    new_transcript_data["segments"][payload.segment_index]["text"] = payload.new_text

    new_transcript_data["full_text"] = " ".join([s["text"] for s in new_transcript_data["segments"]])

    meeting.transcript_data = new_transcript_data
    await db.commit()

    return {"status": "success", "updated_segment": new_transcript_data["segments"][payload.segment_index]}
