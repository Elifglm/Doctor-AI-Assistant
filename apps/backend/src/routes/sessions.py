"""Session CRUD routes -- /api/v1/sessions."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.backend.src.db.database import get_db
from apps.backend.src.dependencies import get_audit_service, get_current_user
from apps.backend.src.schemas.auth import UserInfo
from apps.backend.src.schemas.session import (
    CreateSessionRequest,
    SessionDetailResponse,
    SessionListResponse,
    SessionResponse,
    UpdateSessionRequest,
)
from apps.backend.src.services.audit_service import AuditService
from apps.backend.src.services.session_service import SessionService

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


# ---------------------------------------------------------------------------
# POST  /api/v1/sessions
# ---------------------------------------------------------------------------
@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: CreateSessionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserInfo = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
) -> SessionResponse:
    """Create a new clinical session."""
    svc = SessionService(db)
    session = await svc.create(body)

    await audit.log(
        action="CREATE",
        resource_type="session",
        resource_id=str(session.id),
        user_id=user.username,
        ip_address=request.client.host if request.client else None,
    )

    return SessionResponse.model_validate(session)


# ---------------------------------------------------------------------------
# GET  /api/v1/sessions
# ---------------------------------------------------------------------------
@router.get("", response_model=SessionListResponse)
async def list_sessions(
    status_filter: Optional[str] = Query(None, alias="status"),
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    sort: str = Query("created_at:desc"),
    db: AsyncSession = Depends(get_db),
    user: UserInfo = Depends(get_current_user),
) -> SessionListResponse:
    """Return a filtered, paginated session list."""
    svc = SessionService(db)

    # Doktor sadece kendi oturumlarini gorsun, admin hepsini
    doctor_filter = None
    if user.role != "admin":
        doctor_filter = user.display_name

    items, total = await svc.list_sessions(
        status=status_filter,
        from_date=from_date,
        to_date=to_date,
        search=search,
        doctor_name=doctor_filter,
        page=page,
        limit=limit,
        sort=sort,
    )
    pages = math.ceil(total / limit) if total else 0
    return SessionListResponse(
        items=[SessionResponse.model_validate(s) for s in items],
        total=total,
        page=page,
        limit=limit,
        pages=pages,
    )


# ---------------------------------------------------------------------------
# GET  /api/v1/sessions/{id}
# ---------------------------------------------------------------------------
@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserInfo = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
) -> SessionDetailResponse:
    """Return a single session with its segments and reports."""
    svc = SessionService(db)
    session = await svc.get_by_id(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    # Doktor sadece kendi oturumunu gorebilir
    if user.role != "admin" and session.doctor_name != user.display_name:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu oturumu goruntuleme yetkiniz yok",
        )

    await audit.log(
        action="READ",
        resource_type="session",
        resource_id=str(session.id),
        user_id=user.username,
        ip_address=request.client.host if request.client else None,
    )

    return SessionDetailResponse.model_validate(session)


# ---------------------------------------------------------------------------
# PATCH  /api/v1/sessions/{id}
# ---------------------------------------------------------------------------
@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: int,
    body: UpdateSessionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserInfo = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
) -> SessionResponse:
    """Partially update an existing session."""
    svc = SessionService(db)
    session = await svc.update(session_id, body)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    await audit.log(
        action="UPDATE",
        resource_type="session",
        resource_id=str(session.id),
        user_id=user.username,
        ip_address=request.client.host if request.client else None,
    )

    return SessionResponse.model_validate(session)


# ---------------------------------------------------------------------------
# DELETE  /api/v1/sessions/{id}  (soft-delete / archive)
# ---------------------------------------------------------------------------
@router.delete("/{session_id}", response_model=SessionResponse)
async def archive_session(
    session_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserInfo = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
) -> SessionResponse:
    """Archive (soft-delete) a session."""
    svc = SessionService(db)

    # First fetch so we can return it
    session = await svc.get_by_id(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    await svc.archive(session_id)

    await audit.log(
        action="DELETE",
        resource_type="session",
        resource_id=str(session_id),
        user_id=user.username,
        ip_address=request.client.host if request.client else None,
    )

    # Refresh to pick up the ARCHIVED status
    await db.refresh(session)
    return SessionResponse.model_validate(session)
