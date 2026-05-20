from celery import Celery
from src.config import get_settings

settings = get_settings()

celery_app = Celery(
    "verbatim_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["src.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Moscow",
    enable_utc=True,
    task_acks_late=True,
    broker_transport_options={"visibility_timeout": 7200},
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1,
    broker_connection_retry_on_startup=True
)
