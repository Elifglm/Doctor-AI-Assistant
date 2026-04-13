"""SUT tetkik search, suggestion, and confirmation routes."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from apps.backend.src.dependencies import get_audit_service, get_current_user
from apps.backend.src.schemas.auth import UserInfo
from apps.backend.src.schemas.sut_tetkik import (
    SUTConfirmRequest,
    SUTConfirmResponse,
    SUTItem,
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
