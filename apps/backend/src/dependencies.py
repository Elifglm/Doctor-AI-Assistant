"""FastAPI dependencies for auth and services."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from sqlalchemy.ext.asyncio import AsyncSession

from apps.backend.src.db.database import get_db
from apps.backend.src.schemas.auth import UserInfo
from apps.backend.src.services.auth_service import verify_token
from apps.backend.src.services.audit_service import AuditService

_bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> UserInfo:
    """Extract and validate the user from the JWT Bearer token."""
    payload = verify_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username: str | None = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return UserInfo(
        username=username,
        display_name=payload.get("display_name", username),
        role=payload.get("role", "doctor"),
        brans=payload.get("brans", ""),
    )


async def get_audit_service(
    db: AsyncSession = Depends(get_db),
) -> AuditService:
    """Return an AuditService instance wired to the current DB session."""
    return AuditService(db)
