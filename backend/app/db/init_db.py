"""Initialize database tables / 데이터베이스 테이블 초기화."""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.base import Base
from app.db.session import engine
from app.models.db_models import (
    BalanceSnapshot,
    ExchangeCredential,
    ExecutionLog,
    Fill,
    OpportunityHistory,
    Order,
    RiskLimit,
    User,
)

logger = logging.getLogger(__name__)


async def init_db(engine_override: AsyncEngine | None = None) -> None:
    """Create all tables in database / 데이터베이스에 모든 테이블 생성."""
    target_engine = engine_override or engine
    async with target_engine.begin() as conn:
        logger.info("Creating database tables... / 데이터베이스 테이블 생성 중...")
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully. / 데이터베이스 테이블 생성 완료.")


async def drop_db(engine_override: AsyncEngine | None = None) -> None:
    """Drop all tables from database / 데이터베이스의 모든 테이블 삭제."""
    target_engine = engine_override or engine
    async with target_engine.begin() as conn:
        logger.warning("Dropping all database tables... / 모든 데이터베이스 테이블 삭제 중...")
        await conn.run_sync(Base.metadata.drop_all)
        logger.info("Database tables dropped. / 데이터베이스 테이블 삭제 완료.")
