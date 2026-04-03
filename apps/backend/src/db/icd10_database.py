"""Async database engine for the read-only ICD-10 reference database."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DB_DIR = _PROJECT_ROOT / "data"
_ICD10_DB_PATH = _DB_DIR / "icd10.db"

ICD10_DATABASE_URL = f"sqlite+aiosqlite:///{_ICD10_DB_PATH.as_posix()}"

icd10_engine = create_async_engine(
    ICD10_DATABASE_URL,
    echo=False,
    future=True,
)

icd10_session_maker = async_sessionmaker(
    icd10_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
