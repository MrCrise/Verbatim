import aiofiles
import os
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from src.logger import setup_logger
from src.config import Settings, get_settings
from src.tasks import process_audio_task


router = APIRouter()
logger = setup_logger(__name__)


@router.post("/upload", status_code=202)
async def upload_media(
    file: UploadFile = File(...),
    language: Optional[str] = None,
    settings: Settings = Depends(get_settings)
):
    """
    Основной эндпоинт для загрузки медиаконтента.
    """

    # Кринж валидация, поменять на список расширений из конфига.
    if not file.filename.endswith((".mp3", ".wav", ".m4a", ".mp4")):
        raise HTTPException(status_code=400, detail="Unsupported file format")
    
    # Временное сохранение файлов на диск для обработки.
    # В будущем заменить на MinIO.
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(settings.UPLOAD_DIR, file.filename)

    try:
        async with aiofiles.open(file_path, "wb") as out_file:
            while content := await file.read(1024 * 1024):
                await out_file.write(content)
    except Exception as e:
        logger.error(f"Failed to save file: {e}")
        raise HTTPException(status_code=500, detail="File save error")
    
    logger.info(f"File saved: {file_path}. Creating task.")

    task = process_audio_task.delay(filename=file_path, language=language)

    return {
        "task_id": task.id,
        "status": "QUEUED",
        "message": "File enqueued for processing"
    }