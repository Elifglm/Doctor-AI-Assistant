"""JWT authentication service with database-backed user management."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.backend.src.db.database import async_session_maker
from apps.backend.src.db.models import User
from apps.backend.src.schemas.auth import UserInfo

logger = logging.getLogger(__name__)

SECRET_KEY = "doctor-ai-dev-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

# Default seed users — inserted on first startup if users table is empty
_SEED_USERS = [
    {
        "username": "admin",
        "password": "admin",
        "display_name": "Admin",
        "role": "admin",
        "brans": "",
    },
    {
        "username": "doktor1",
        "password": "doktor1",
        "display_name": "Dr. Ahmet Yılmaz",
        "role": "doctor",
        "brans": "dahiliye",
    },
    {
        "username": "doktor2",
        "password": "doktor2",
        "display_name": "Dr. Ayşe Demir",
        "role": "doctor",
        "brans": "ortopedi",
    },
]


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


async def seed_default_users() -> None:
    """Insert default users if the users table is empty."""
    async with async_session_maker() as session:
        result = await session.execute(select(User).limit(1))
        if result.scalar_one_or_none() is not None:
            return  # already seeded

        for u in _SEED_USERS:
            session.add(User(
                username=u["username"],
                hashed_password=hash_password(u["password"]),
                display_name=u["display_name"],
                role=u["role"],
                brans=u["brans"],
            ))
        await session.commit()
        logger.info("Varsayilan kullanicilar olusturuldu: %d adet", len(_SEED_USERS))


def create_access_token(data: dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> dict[str, Any] | None:
    """Decode and verify a JWT token.  Returns the payload or None."""
    try:
        payload: dict[str, Any] = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


async def authenticate_user(username: str, password: str) -> UserInfo | None:
    """Verify credentials against the database and return UserInfo."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.username == username, User.is_active == True)  # noqa: E712
        )
        user = result.scalar_one_or_none()

    if user is None:
        return None
    if not verify_password(password, user.hashed_password):
        return None

    return UserInfo(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        brans=user.brans,
    )
