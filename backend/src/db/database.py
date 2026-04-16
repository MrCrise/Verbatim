from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from src.config import get_settings

settings = get_settings()
engine = create_async_engine(
    settings.DATABASE_URL,
    poolclass=NullPool
)

async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)


class Base(DeclarativeBase):
    """
    Declarative base class for all SQLAlchemy ORM models.
    """
    pass


async def get_db():
    """
    FastAPI dependency that provides an asynchronous database session.

    Ensures proper session lifecycle management per request.
    """
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()