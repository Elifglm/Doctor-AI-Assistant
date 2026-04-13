"""Async database engine for the read-only SUT tetkik reference database."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DB_DIR = _PROJECT_ROOT / "data"
_SUT_DB_PATH = _DB_DIR / "sut_tetkik.db"

SUT_DATABASE_URL = f"sqlite+aiosqlite:///{_SUT_DB_PATH.as_posix()}"

sut_engine = create_async_engine(
    SUT_DATABASE_URL,
    echo=False,
    future=True,
)

sut_session_maker = async_sessionmaker(
    sut_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
