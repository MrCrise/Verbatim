import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Все настройки приложения.
    Имена переменных в классе должны совпадать с именами в .env файле.
    """

    # --- APP CONFIG ---
    PROJECT_NAME: str = "Verbatim ASR"
    VERSION: str = "1.0.0"
    API_STR: str = "/api"
    DEBUG: bool = True

    # --- POSTGRESQL ---
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_DB: str = "verbatim_db"
    POSTGRES_PORT: int = 5432

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # --- REDIS & CELERY ---
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    @property
    def CELERY_BROKER_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    @property
    def CELERY_RESULT_BACKEND(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    # --- MINIO (S3) ---
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "admin"
    MINIO_SECRET_KEY: str = "password123"
    MINIO_BUCKET_AUDIO: str = "raw-audio"
    MINIO_SECURE: bool = True  # False - http, True - https.

    # --- FILES ---
    UPLOAD_DIR: str = "temp_uploads"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


# --- Dependency Injection ---
@lru_cache()
def get_settings() -> Settings:
    """
    Создает настройки и кэширует их.
    Используется с Depends(get_settings).
    """

    return Settings()
