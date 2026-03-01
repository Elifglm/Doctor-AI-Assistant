"""Data management routes -- /api/v1/data."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.backend.src.db.database import get_db
from apps.backend.src.db.models import AuditLog, Report, Session, TranscriptionSegment
from apps.backend.src.dependencies import get_audit_service, get_current_user
from apps.backend.src.schemas.auth import UserInfo
from apps.backend.src.schemas.data import PurgeResponse
from apps.backend.src.services.audit_service import AuditService

router = APIRouter(prefix="/api/v1/data", tags=["data"])


@router.delete(
    "/purge",
    response_model=PurgeResponse,
    status_code=status.HTTP_200_OK,
)
async def purge_all_data(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserInfo = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
) -> PurgeResponse:
    """Delete ALL sessions, transcription segments, reports, and audit logs.

    This is a destructive, irreversible operation. Requires authentication.
    Returns the count of deleted records per table.
    """
    # Count records before deletion (for the response)
    sessions_count: int = (
        await db.execute(select(func.count()).select_from(Session))
    ).scalar_one()
    segments_count: int = (
        await db.execute(select(func.count()).select_from(TranscriptionSegment))
    ).scalar_one()
    reports_count: int = (
        await db.execute(select(func.count()).select_from(Report))
    ).scalar_one()
    audit_count: int = (
        await db.execute(select(func.count()).select_from(AuditLog))
    ).scalar_one()

    # Delete in dependency order (children first)
    await db.execute(delete(TranscriptionSegment))
    await db.execute(delete(Report))
    await db.execute(delete(AuditLog))
    await db.execute(delete(Session))

    # Log the purge itself (this creates a new audit entry after the wipe)
    await audit.log(
        action="PURGE",
        resource_type="all_data",
        user_id=user.username,
        details=(
            f"Purged {sessions_count} sessions, {segments_count} segments, "
            f"{reports_count} reports, {audit_count} audit_logs"
        ),
        ip_address=request.client.host if request.client else None,
    )

    total = sessions_count + segments_count + reports_count + audit_count

    return PurgeResponse(
        message="Tum veriler basariyla silindi",
        deleted_sessions=sessions_count,
        deleted_segments=segments_count,
        deleted_reports=reports_count,
        deleted_audit_logs=audit_count,
        total_deleted=total,
    )
