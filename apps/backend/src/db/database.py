"""Async database engine and session management.

Supports two backends, selected via the ``DATABASE_URL`` environment variable:
  * SQLite (default, file-based, single-machine) — ``sqlite+aiosqlite:///...``
  * MariaDB / MySQL (shared, multi-user) — ``mysql+asyncmy://user:pass@host/db``

When ``DATABASE_URL`` is unset, the historical SQLite location
(``<project_root>/data/asr.db``) is used to preserve backward compatibility.
"""

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

# Load DATABASE_URL from .env if present (pydantic-settings does not export it
# to os.environ, so we read the file directly).
try:
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:  # python-dotenv optional
    pass

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{_DB_PATH.as_posix()}",
)
_IS_SQLITE = DATABASE_URL.startswith("sqlite")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=not _IS_SQLITE,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create all tables if they do not exist."""
    if _IS_SQLITE:
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
