"""Report CRUD routes -- /api/v1/reports."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from apps.backend.src.db.database import get_db
from apps.backend.src.db.models import Report as ReportModel, Session as SessionModel, TranscriptionSegment
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_response(report: ReportModel) -> ReportResponse:
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

    if body.method == "ai_generated":
        # Fetch transcript segments for the session
        stmt = (
            select(TranscriptionSegment)
            .where(TranscriptionSegment.session_id == body.session_id)
            .order_by(TranscriptionSegment.segment_index.asc())
        )
        result = await db.execute(stmt)
        db_segments = list(result.scalars().all())

        if not db_segments:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bu oturum icin transkript bulunamadi. Once kayit yapilmalidir.",
            )

        segments_data = [
            {
                "text": seg.text,
                "speaker": seg.speaker,
                "speaker_label": seg.speaker_label,
                "start_time": seg.start_time,
                "end_time": seg.end_time,
            }
            for seg in db_segments
        ]

        # Run the AI pipeline
        report_generator = getattr(request.app.state, "report_generator", None)
        if report_generator is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="LLM pipeline hazir degil. Lutfen daha sonra tekrar deneyin.",
            )

        try:
            content = await report_generator.generate_report(
                segments_data, brans=user.brans
            )
        except Exception:
            logger.exception("AI report generation failed")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Rapor olusturma sirasinda hata olustu.",
            )

        report = await svc.generate_with_content(
            body.session_id, content, method="ai_generated"
        )
    else:
        report = await svc.generate(
            body.session_id, method=body.method, brans=user.brans
        )

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
# GET  /api/v1/reports/stream/{session_id}  -- SSE streaming AI generation
# ---------------------------------------------------------------------------
@router.get("/stream/{session_id}")
async def stream_report_generation(
    session_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserInfo = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
):
    """SSE endpoint for streaming AI report generation."""
    report_generator = getattr(request.app.state, "report_generator", None)
    if report_generator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM pipeline hazir degil.",
        )

    # Fetch transcript segments
    stmt = (
        select(TranscriptionSegment)
        .where(TranscriptionSegment.session_id == session_id)
        .order_by(TranscriptionSegment.segment_index.asc())
    )
    result = await db.execute(stmt)
    db_segments = list(result.scalars().all())

    if not db_segments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu oturum icin transkript bulunamadi.",
        )

    segments_data = [
        {
            "text": seg.text,
            "speaker": seg.speaker,
            "speaker_label": seg.speaker_label,
            "start_time": seg.start_time,
            "end_time": seg.end_time,
        }
        for seg in db_segments
    ]

    await audit.log(
        action="CREATE",
        resource_type="report_stream",
        resource_id=str(session_id),
        user_id=user.username,
        details="method=ai_generated_stream",
        ip_address=request.client.host if request.client else None,
    )

    async def event_generator():
        try:
            async for event in report_generator.generate_report_stream(
                segments_data, brans=user.brans
            ):
                event_type = event.get("event", "message")
                event_data = json.dumps(event.get("data", {}), ensure_ascii=False)
                yield {"event": event_type, "data": event_data}
        except Exception:
            logger.exception("SSE stream error for session %d", session_id)
            yield {
                "event": "error",
                "data": json.dumps({"message": "Rapor olusturma sirasinda hata olustu."}),
            }

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# GET  /api/v1/reports/{report_id}/pdf  -- Download PDF report
# ---------------------------------------------------------------------------
@router.get("/{report_id}/pdf")
async def download_report_pdf(
    report_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserInfo = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
) -> Response:
    """Generate and return a PDF version of the report."""
    from apps.backend.src.services.pdf_service import generate_report_pdf

    # Fetch report
    svc = ReportService(db)
    report = await svc.get_by_id(report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report {report_id} not found",
        )

    # Fetch session
    stmt = select(SessionModel).where(SessionModel.id == report.session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    # Build data dicts
    session_data = {
        "patient_id": session.patient_id or "",
        "patient_name": session.patient_name or "",
        "doctor_name": session.doctor_name or "",
        "visit_type": session.visit_type or "",
        "created_at": session.created_at,
    }

    content = report.content  # parsed JSON via @property
    report_data = {
        "report_id": report.id,
        "sections": content.get("sections", []),
        "approved_at": report.approved_at,
    }

    # Generate PDF
    pdf_bytes = generate_report_pdf(session_data, report_data)

    # Audit
    await audit.log(
        action="EXPORT_PDF",
        resource_type="report",
        resource_id=str(report.id),
        user_id=user.username,
        ip_address=request.client.host if request.client else None,
    )

    patient_name = (session.patient_name or "rapor").replace(" ", "_")
    filename = f"anamnez_{patient_name}_{report.id}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# POST  /api/v1/reports/{report_id}/push-to-openemr
# ---------------------------------------------------------------------------
@router.post("/{report_id}/push-to-openemr")
async def push_report_to_openemr(
    report_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserInfo = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
) -> dict:
    """Push an approved report to OpenEMR (encounter + vitals + SOAP + ICD-10)."""
    import re

    from apps.backend.src.services.openemr_service import OpenEMRService, OPENEMR_DOCTORS

    # Fetch report
    svc = ReportService(db)
    report = await svc.get_by_id(report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rapor bulunamadi",
        )

    if report.status != "APPROVED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rapor henuz onaylanmamis. Once tum bolumleri onaylayin.",
        )

    # Fetch session
    stmt = select(SessionModel).where(SessionModel.id == report.session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Oturum bulunamadi",
        )

    # Get patient PID from OpenEMR (pubpid = our patient_id)
    patient_id = session.patient_id or ""
    if not patient_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Oturumda hasta ID bilgisi yok",
        )

    # Find patient pid in OpenEMR
    try:
        raw = await OpenEMRService._mysql_exec(
            f"SELECT pid FROM patient_data WHERE pubpid = '{patient_id}' LIMIT 1;"
        )
        if not raw.strip():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"OpenEMR'de hasta bulunamadi (ID: {patient_id})",
            )
        patient_pid = int(raw.strip())
    except (ValueError, RuntimeError) as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenEMR baglanti hatasi: {e}",
        )

    # Determine provider ID
    doctor_info = OPENEMR_DOCTORS.get(user.brans, {})
    provider_id = doctor_info.get("openemr_user_id", 1)

    # Build sections dict
    content = report.content
    sections = content.get("sections", [])
    report_sections = {s["key"]: s.get("content", "") for s in sections}

    # Parse ICD-10 codes from icd10_list
    icd10_codes: list[dict[str, str]] = []
    icd_content = report_sections.get("icd10_list", "")
    if icd_content and icd_content.strip() not in ("BELIRTILMEDI", ""):
        for line in icd_content.split("\n"):
            match = re.match(r"\(([A-Z]\d[\dA-Z.]*)\)\s*-\s*(.+?)(?:\s*\(.*\))?\s*(?:\[.*\])?\s*$", line.strip())
            if match:
                icd10_codes.append({"code": match.group(1), "text": match.group(2).strip()})

    # Parse SUT tetkik codes from sut_tetkik_list
    sut_codes: list[dict[str, str]] = []
    sut_content = report_sections.get("sut_tetkik_list", "")
    if sut_content and sut_content.strip() not in ("BELIRTILMEDI", ""):
        for line in sut_content.split("\n"):
            sut_match = re.match(r"\(([A-Za-z0-9]+)\)\s*-\s*(.+?)(?:\s*\[.*\])?\s*$", line.strip())
            if sut_match:
                sut_codes.append({"code": sut_match.group(1), "name": sut_match.group(2).strip()})

    # Push to OpenEMR
    push_result = await OpenEMRService.push_report_to_openemr(
        patient_pid=patient_pid,
        provider_id=provider_id,
        report_sections=report_sections,
        icd10_codes=icd10_codes,
        sut_codes=sut_codes,
        facility_id=3,
    )

    # Audit
    await audit.log(
        action="PUSH_TO_OPENEMR",
        resource_type="report",
        resource_id=str(report.id),
        user_id=user.username,
        details=f"encounter={push_result.get('encounter_id')}, icd10={push_result.get('icd10_count')}",
        ip_address=request.client.host if request.client else None,
    )

    return push_result
