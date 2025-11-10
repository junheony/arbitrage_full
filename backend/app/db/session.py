"""Database session management / 데이터베이스 세션 관리."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

settings = get_settings()


# Async engine for production / 프로덕션용 비동기 엔진
if settings.database_url:
    engine = create_async_engine(
        settings.database_url,
        echo=settings.environment == "local",
        future=True,
    )
    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
else:
    # Fallback to SQLite for MVP / MVP용 SQLite fallback
    engine = create_async_engine(
        "sqlite+aiosqlite:///./arbitrage.db",
        echo=settings.environment == "local",
        future=True,
    )
    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )


async def get_db() -> AsyncSession:
    """Dependency for getting async database session / 비동기 DB 세션 의존성."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
