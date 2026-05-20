import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List

from src.db.database import get_db
from src.db.models import User, Meeting
from src.dependencies import get_current_user

router = APIRouter()


async def get_admin_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    return current_user


@router.get("/stats")
async def get_system_stats(db: AsyncSession = Depends(get_db), admin: User = Depends(get_admin_user)):
    users_count = await db.scalar(select(func.count(User.id)))
    meetings_stats = await db.execute(
        select(
            func.count(Meeting.id),
            func.coalesce(func.sum(Meeting.duration_sec), 0.0),
            func.coalesce(func.sum(Meeting.file_size_bytes), 0)
        )
    )
    m_count, m_duration, m_size = meetings_stats.first()
    return {
        "total_users": users_count or 0,
        "total_meetings": m_count or 0,
        "total_duration_sec": m_duration,
        "total_storage_bytes": m_size
    }


@router.get("/users")
async def get_users_stats(db: AsyncSession = Depends(get_db), admin: User = Depends(get_admin_user)):
    query = (
        select(
            User,
            func.count(Meeting.id).label("meetings_count"),
            func.coalesce(func.sum(Meeting.duration_sec), 0.0).label("total_duration")
        )
        .outerjoin(Meeting, User.id == Meeting.owner_id)
        .group_by(User.id)
        .order_by(User.created_at.desc())
    )
    result = await db.execute(query)
    return [{
        "id": str(user.id),
        "full_name": user.full_name or "Без имени",
        "email": user.email,
        "is_admin": user.is_admin,
        "created_at": user.created_at,
        "last_login": user.last_login,
        "meetings_count": m_count,
        "total_duration_sec": m_duration
    } for user, m_count, m_duration in result.all()]


@router.patch("/users/{user_id}/role")
async def update_user_role(
        user_id: uuid.UUID,
        is_admin: bool,
        db: AsyncSession = Depends(get_db),
        current_admin: User = Depends(get_admin_user)
):
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="Нельзя менять роль самому себе")

    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    target_user.is_admin = is_admin
    await db.commit()
    return {"status": "success", "is_admin": target_user.is_admin}