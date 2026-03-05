from typing import Optional
from celery import Task
from src.celery_app import celery_app
from src.logger import setup_logger
import time


logger = setup_logger("worker")


class BaseTask(Task):
    """Базовый класс для автоматического логирования ошибок."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(f"Task {task_id} failed: {exc}", exc_info=True)
        return super().on_failure(exc, task_id, args, kwargs, einfo)


@celery_app.task(bind=True, base=BaseTask, name="process_audio_task")
def process_audio_task(self, filename: str, language: Optional[str] = None):
    """
    Основной таск для транскрибации.
    
    Args:
        filename: путь к файлу (потом заменить на id в S3)
        language: код языка, либо None
    """
    logger.info(f"Start processing task: {self.request.id}")
    logger.info(f"File: {filename} | Language: {language or 'Auto'}")

    try:
        time.sleep(5)

        # Тутава будет ML код.

        result = {
            "file": filename,
            "status": "completed",
            "duration": 123,
            "segments": [
                {"start": 0.0, "end": 2.0, "text": "Тестовый вывод."},
                {"start": 2.0, "end": 5.0, "text": "Celery работает корректно."},
            ]
        }

        logger.info(f"Task {self.request.id} completed successfully.")

        return result
    
    except Exception as e:
        logger.error(f"Error during ML inference: {e}")
        raise e
