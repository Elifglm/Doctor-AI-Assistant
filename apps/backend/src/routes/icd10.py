"""ICD-10 search, suggestion, and confirmation routes."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from apps.backend.src.dependencies import get_audit_service, get_current_user
from apps.backend.src.schemas.auth import UserInfo
from apps.backend.src.schemas.icd10 import (
    ICD10ConfirmRequest,
    ICD10ConfirmResponse,
    ICD10Item,
    ICD10SearchResponse,
    ICD10SuggestRequest,
    ICD10SuggestResponse,
)
from apps.backend.src.services.audit_service import AuditService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/icd10", tags=["icd10"])


@router.get("/search", response_model=ICD10SearchResponse)
async def search_icd10(
    request: Request,
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
    user: UserInfo = Depends(get_current_user),
) -> ICD10SearchResponse:
    """Search ICD-10 codes by code or diagnosis text."""
    icd10_service = getattr(request.app.state, "icd10_service", None)
    if icd10_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ICD-10 servisi kulanilamaz",
        )

    results = await icd10_service.search(q, limit)
    return ICD10SearchResponse(
        results=[
            ICD10Item(
                icd_kodu=r.icd_kodu,
                tani=r.tani,
                ust_kod=r.ust_kod,
                seviye=r.seviye,
            )
            for r in results
        ],
        total=len(results),
    )


@router.post("/suggest", response_model=ICD10SuggestResponse)
async def suggest_icd10(
    body: ICD10SuggestRequest,
    request: Request,
    user: UserInfo = Depends(get_current_user),
) -> ICD10SuggestResponse:
    """Get LLM-powered ICD-10 suggestions from transcript text."""
    suggestion_service = getattr(request.app.state, "icd10_suggestion_service", None)
    if suggestion_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ICD-10 oneri servisi kullanilamaz",
        )

    suggestions = await suggestion_service.suggest(body.transcript_text)
    return ICD10SuggestResponse(suggestions=suggestions)


@router.post("/confirm", response_model=ICD10ConfirmResponse)
async def confirm_icd10(
    body: ICD10ConfirmRequest,
    request: Request,
    user: UserInfo = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
) -> ICD10ConfirmResponse:
    """Confirm doctor-selected ICD-10 codes for a report."""
    await audit.log(
        action="ICD10_CONFIRM",
        resource_type="report",
        resource_id=str(body.report_id),
        user_id=user.username,
        details=json.dumps(
            [c.model_dump() for c in body.codes], ensure_ascii=False
        ),
        ip_address=request.client.host if request.client else None,
    )

    return ICD10ConfirmResponse(confirmed=True, codes=body.codes)
