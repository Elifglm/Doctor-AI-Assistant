"""Report CRUD routes -- /api/v1/reports."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.backend.src.db.database import get_db
from apps.backend.src.dependencies import get_audit_service, get_current_user
from apps.backend.src.schemas.auth import UserInfo
from apps.backend.src.schemas.report import (
    GenerateReportRequest,
    ReportContent,
    ReportResponse,
    UpdateReportRequest,
)
from apps.backend.src.services.audit_service import AuditService
from apps.backend.src.services.report_service import ReportService

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_response(report) -> ReportResponse:
    """Convert an ORM Report to a ReportResponse, parsing content_json."""
    content = ReportContent.model_validate(
        json.loads(report.content_json) if report.content_json else {
            "sections": [], "approved_sections": 0, "total_sections": 0,
        }
    )
    return ReportResponse(
        id=report.id,
        session_id=report.session_id,
        version=report.version,
        status=report.status,
        content=content,
        generation_method=report.generation_method,
        approved_at=report.approved_at,
        approved_by=report.approved_by,
        created_at=report.created_at,
    )


# ---------------------------------------------------------------------------
# POST  /api/v1/reports
# ---------------------------------------------------------------------------
@router.post("", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def generate_report(
    body: GenerateReportRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserInfo = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
) -> ReportResponse:
    """Generate a new report for a clinical session."""
    svc = ReportService(db)
    report = await svc.generate(body.session_id, method=body.method)

    await audit.log(
        action="CREATE",
        resource_type="report",
        resource_id=str(report.id),
        user_id=user.username,
        details=f"method={body.method}",
        ip_address=request.client.host if request.client else None,
    )

    return _to_response(report)


# ---------------------------------------------------------------------------
# GET  /api/v1/reports/{report_id}
# ---------------------------------------------------------------------------
@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserInfo = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
) -> ReportResponse:
    """Return a single report by ID."""
    svc = ReportService(db)
    report = await svc.get_by_id(report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report {report_id} not found",
        )

    await audit.log(
        action="READ",
        resource_type="report",
        resource_id=str(report.id),
        user_id=user.username,
        ip_address=request.client.host if request.client else None,
    )

    return _to_response(report)


# ---------------------------------------------------------------------------
# PUT  /api/v1/reports/{report_id}
# ---------------------------------------------------------------------------
@router.put("/{report_id}", response_model=ReportResponse)
async def update_report(
    report_id: int,
    body: UpdateReportRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserInfo = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
) -> ReportResponse:
    """Update report content and/or status."""
    svc = ReportService(db)
    report = await svc.update(report_id, body)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report {report_id} not found",
        )

    await audit.log(
        action="UPDATE",
        resource_type="report",
        resource_id=str(report.id),
        user_id=user.username,
        details=f"status={body.status}" if body.status else None,
        ip_address=request.client.host if request.client else None,
    )

    return _to_response(report)


# ---------------------------------------------------------------------------
# GET  /api/v1/reports/{report_id}/versions
# ---------------------------------------------------------------------------
@router.get("/{report_id}/versions", response_model=list[ReportResponse])
async def get_report_versions(
    report_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserInfo = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
) -> list[ReportResponse]:
    """Return all version history for a report's session."""
    svc = ReportService(db)
    versions = await svc.get_versions(report_id)
    if not versions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report {report_id} not found",
        )

    await audit.log(
        action="READ",
        resource_type="report_versions",
        resource_id=str(report_id),
        user_id=user.username,
        ip_address=request.client.host if request.client else None,
    )

    return [_to_response(r) for r in versions]


# ---------------------------------------------------------------------------
# GET  /api/v1/reports/stream/{report_id}  -- SSE placeholder
# ---------------------------------------------------------------------------
@router.get("/stream/{report_id}")
async def stream_report(report_id: int):
    """SSE placeholder for future LLM report generation streaming."""

    async def event_generator():
        yield f"data: {json.dumps({'type': 'info', 'message': 'LLM entegrasyonu henuz aktif degil'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
