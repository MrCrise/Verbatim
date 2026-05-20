from fastapi import APIRouter, Depends

from src.dependencies import get_current_user
from src.schemas import UserResponse
from src.db.database import get_db
from src.db.models import User
from src.logger import setup_logger


router = APIRouter()
logger = setup_logger(__name__)


@router.get("/me", response_model=UserResponse)
async def get_user_me(current_user: User = Depends(get_current_user)):
    """Возвращает информацию о текущем авторизованном пользователе."""
    return current_user
