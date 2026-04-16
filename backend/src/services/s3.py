import aioboto3
from contextlib import asynccontextmanager
from src.config import get_settings

settings = get_settings()


class S3Service:
    """
    Asynchronous S3-compatible object storage client.

    Designed for MinIO/S3 environments.
    Handles upload and download operations using aioboto3.
    """

    def __init__(self):
        """
        Initialize S3 session and connection parameters.
        """
        self.session = aioboto3.Session()
        self.endpoint_url = f"http://{settings.MINIO_ENDPOINT}"
        self.access_key = settings.MINIO_ACCESS_KEY
        self.secret_key = settings.MINIO_SECRET_KEY
        self.bucket_name = settings.MINIO_BUCKET_NAME

    @asynccontextmanager
    async def get_client(self):
        """
        Provide an async S3 client instance using context management.

        Ensures proper connection lifecycle handling.
        """
        async with self.session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
        ) as client:
            yield client

    async def upload_streaming(self, file_obj, object_name: str) -> str:
        """
        Upload a file-like object to object storage.

        Parameters:
            file_obj: file-like stream
            object_name: target storage key

        Returns:
            object_name
        """
        async with self.get_client() as s3:
            await s3.upload_fileobj(
                file_obj,
                self.bucket_name,
                object_name
            )
            return object_name

    async def download_file(self, object_name: str) -> bytes:
        """
        Download object from storage and return its raw bytes.

        Parameters:
            object_name: storage key

        Returns:
            File content as bytes
        """
        async with self.get_client() as s3:
            response = await s3.get_object(
                Bucket=self.bucket_name,
                Key=object_name
            )
            async with response['Body'] as stream:
                return await stream.read()


s3_service = S3Service()