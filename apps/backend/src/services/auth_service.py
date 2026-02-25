"""Simple JWT authentication service for the prototype."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
from jose import JWTError, jwt

from apps.backend.src.schemas.auth import UserInfo

SECRET_KEY = "doctor-ai-dev-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24


def _hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# Hardcoded prototype user
_USERS: dict[str, dict[str, Any]] = {
    "admin": {
        "username": "admin",
        "hashed_password": _hash_password("admin"),
        "display_name": "Dr. Admin",
        "role": "doctor",
    },
}


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


def authenticate_user(username: str, password: str) -> UserInfo | None:
    """Verify credentials and return UserInfo on success, None on failure."""
    user = _USERS.get(username)
    if user is None:
        return None
    if not _verify_password(password, user["hashed_password"]):
        return None
    return UserInfo(
        username=user["username"],
        display_name=user["display_name"],
        role=user["role"],
    )
