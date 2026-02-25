"""Async database engine and session management using aiosqlite + SQLAlchemy."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.backend.src.db.models import Base

# DB path: data/asr.db relative to ASR1 project root
_PROJECT_ROOT = Path(__file__).resolve().parents[4]  # ASR1/
_DB_DIR = _PROJECT_ROOT / "data"
_DB_PATH = _DB_DIR / "asr.db"

DATABASE_URL = f"sqlite+aiosqlite:///{_DB_PATH.as_posix()}"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create all tables if they do not exist."""
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
