"""SUT tetkik search, suggestion, confirmation, and OpenEMR integration routes."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select

from apps.backend.src.db.database import async_session_maker
from apps.backend.src.db.models import Session as SessionModel
from apps.backend.src.dependencies import get_audit_service, get_current_user
from apps.backend.src.schemas.auth import UserInfo
from apps.backend.src.schemas.sut_tetkik import (
    SUTConfirmRequest,
    SUTConfirmResponse,
    SUTItem,
    SUTOpenEMRSendRequest,
    SUTOpenEMRSendResponse,
    SUTSearchResponse,
    SUTSuggestRequest,
    SUTSuggestResponse,
)
from apps.backend.src.services.audit_service import AuditService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sut-tetkik", tags=["sut-tetkik"])


@router.get("/search", response_model=SUTSearchResponse)
async def search_sut(
    request: Request,
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
    brans: str | None = Query(default=None),
    user: UserInfo = Depends(get_current_user),
) -> SUTSearchResponse:
    """Search SUT tetkik codes by code or name text."""
    sut_service = getattr(request.app.state, "sut_service", None)
    if sut_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SUT tetkik servisi kullanilamaz",
        )

    results = await sut_service.search(q, limit, brans=brans)
    return SUTSearchResponse(
        results=[
            SUTItem(
                kodu=r.kodu, adi=r.adi, brans=r.brans,
                ana_kategori=r.ana_kategori, alt_kategori=r.alt_kategori,
                puan=r.puan,
            )
            for r in results
        ],
        total=len(results),
    )


@router.post("/suggest", response_model=SUTSuggestResponse)
async def suggest_sut(
    body: SUTSuggestRequest,
    request: Request,
    user: UserInfo = Depends(get_current_user),
) -> SUTSuggestResponse:
    """Get LLM-powered SUT tetkik suggestions from report sections or transcript text."""
    suggestion_service = getattr(request.app.state, "sut_suggestion_service", None)
    if suggestion_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SUT tetkik oneri servisi kullanilamaz",
        )

    if body.report_sections:
        suggestions = await suggestion_service.suggest_from_report(
            body.report_sections, brans=body.brans
        )
    elif body.transcript_text:
        suggestions = await suggestion_service.suggest(
            body.transcript_text, brans=body.brans
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="report_sections veya transcript_text alanlarindan biri gerekli",
        )

    return SUTSuggestResponse(suggestions=suggestions)


@router.post("/confirm", response_model=SUTConfirmResponse)
async def confirm_sut(
    body: SUTConfirmRequest,
    request: Request,
    user: UserInfo = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
) -> SUTConfirmResponse:
    """Confirm doctor-selected SUT tetkik codes for a report."""
    await audit.log(
        action="SUT_TETKIK_CONFIRM",
        resource_type="report",
        resource_id=str(body.report_id),
        user_id=user.username,
        details=json.dumps(
            [t.model_dump() for t in body.tetkikler], ensure_ascii=False
        ),
        ip_address=request.client.host if request.client else None,
    )

    return SUTConfirmResponse(confirmed=True, tetkikler=body.tetkikler)


@router.post("/send-to-openemr", response_model=SUTOpenEMRSendResponse)
async def send_to_openemr(
    body: SUTOpenEMRSendRequest,
    request: Request,
    user: UserInfo = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
) -> SUTOpenEMRSendResponse:
    """Send confirmed tetkik codes to OpenEMR as a procedure order."""
    openemr_service = getattr(request.app.state, "openemr_service", None)
    if openemr_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenEMR servisi kullanılamaz",
        )

    doctor_brans = user.brans
    if not doctor_brans:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kullanıcının branş bilgisi tanımlı değil",
        )

    # Get patient info from session
    async with async_session_maker() as db:
        result = await db.execute(
            select(SessionModel).where(SessionModel.id == body.session_id)
        )
        session_row = result.scalar_one_or_none()

    if session_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Oturum bulunamadı",
        )

    patient_id = session_row.patient_id or ""
    patient_name = session_row.patient_name or "Bilinmiyor"

    if not patient_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Oturumda hasta kimlik numarası tanımlı değil",
        )

    # Prepare tetkik list with brans info
    tetkik_list = [
        {"kodu": t.kodu, "adi": t.adi, "brans": t.brans}
        for t in body.tetkikler
    ]

    # Filter by doctor's specialty
    filtered = [
        t for t in tetkik_list
        if t["brans"] in (doctor_brans, "her ikisi", "")
    ]

    # Send to OpenEMR
    order_result = await openemr_service.send_tetkik_orders(
        patient_id=patient_id,
        patient_name=patient_name,
        tetkik_list=tetkik_list,
        doctor_brans=doctor_brans,
        notes=body.notes,
    )

    # Audit log
    await audit.log(
        action="SUT_TETKIK_OPENEMR_SEND",
        resource_type="openemr_order",
        resource_id=order_result.order_id or "failed",
        user_id=user.username,
        details=json.dumps(
            {
                "session_id": body.session_id,
                "doctor_brans": doctor_brans,
                "total_tetkik": len(tetkik_list),
                "filtered_tetkik": len(filtered),
                "success": order_result.success,
                "error": order_result.error,
            },
            ensure_ascii=False,
        ),
        ip_address=request.client.host if request.client else None,
    )

    return SUTOpenEMRSendResponse(
        success=order_result.success,
        order_id=order_result.order_id,
        patient_id=order_result.patient_id,
        sent_count=len(filtered),
        filtered_count=len(tetkik_list) - len(filtered),
        error=order_result.error,
        doctor_brans=doctor_brans,
    )
