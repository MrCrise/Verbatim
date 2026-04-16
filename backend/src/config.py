from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # App
    PROJECT_NAME: str = "Verbatim API"
    VERSION: str = "1.0.0"
    ALLOWED_EXTENSIONS: list = [".wav", ".mp3", ".mp4", ".ogg", ".m4a", ".flac"]
    ANONYMOUS_USER_ID: str = "00000000-0000-0000-0000-000000000001"
    
    # Database
    POSTGRES_SERVER: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    # Redis
    REDIS_HOST: str
    REDIS_PORT: int = 6379
    
    @property
    def CELERY_BROKER_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"
    
    @property
    def CELERY_RESULT_BACKEND(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"
    
    # MinIO (S3)
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_BUCKET_NAME: str
    MINIO_USE_SSL: bool = False
    
    # ML
    HF_TOKEN: str
    UPLOAD_DIR: str = "temp_uploads"
    
    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()