import aioboto3
from contextlib import asynccontextmanager
from src.config import get_settings


settings = get_settings()


class S3Service:
    def __init__(self):
        self.session = aioboto3.Session()
        self.endpoint_url = f"http://{settings.MINIO_ENDPOINT}"
        self.access_key = settings.MINIO_ACCESS_KEY
        self.secret_key = settings.MINIO_SECRET_KEY
        self.bucket_name = settings.MINIO_BUCKET_AUDIO

    @asynccontextmanager
    async def get_client(self):
        async with self.session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
        ) as client:
            yield client

    async def upload_streaming(self, file_obj, object_name: str):
        """Потоковая загрузка файла в бакет с шифрованием AES-256."""

        async with self.get_client() as s3:
            await s3.upload_fileobj(
                file_obj,
                self.bucket_name,
                object_name,
                ExtraArgs={
                    "ServerSideEncryption": "AES256",
                    # "ContentType": "audio/mpeg"
                }
            )
            return object_name

    async def download_file(self, object_name: str, local_path: str):
        """Скачивание файла для воркера."""

        async with self.get_client() as s3:
            await s3.download_file(self.bucket_name, object_name, local_path)

    @asynccontextmanager
    async def get_s3_object(self, object_name: str):
        """Контекст-менеджер для получения объекта S3."""

        async with self.get_client() as s3:
            response = await s3.get_object(Bucket=self.bucket_name, Key=object_name)
            try:
                yield response
            finally:
                response['Body'].close()


s3_service = S3Service()
