"""Appointment routes — proxies OpenEMR calendar data with role-based filtering."""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from apps.backend.src.dependencies import get_current_user
from apps.backend.src.schemas.auth import UserInfo
from apps.backend.src.services.openemr_service import OPENEMR_DOCTORS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/appointments", tags=["appointments"])


class Appointment(BaseModel):
    id: int
    title: str
    date: str
    start_time: str
    end_time: str
    duration_seconds: int
    provider_id: int
    provider_name: str
    provider_username: str
    patient_id: str
    patient_name: str
    patient_ext_id: str
    status: str
    category_name: str
    category_color: str
    reason: str


class AppointmentListResponse(BaseModel):
    appointments: list[Appointment]
    total: int
    date: str
    filtered_by: str


@router.get("", response_model=AppointmentListResponse)
async def get_appointments(
    request: Request,
    appointment_date: str = Query(
        default="",
        description="Tarih (YYYY-MM-DD). Bos ise bugun.",
    ),
    user: UserInfo = Depends(get_current_user),
) -> AppointmentListResponse:
    """Get appointments for a date. Doctors see only theirs, admin sees all."""
    openemr_service = getattr(request.app.state, "openemr_service", None)
    if openemr_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenEMR servisi kullanılamaz",
        )

    # Determine date
    if not appointment_date:
        appointment_date = date.today().isoformat()

    # Determine provider filter based on role
    provider_id: int | None = None
    filtered_by = "tumu"

    if user.role != "admin" and user.brans:
        # Map KlinikAsistan brans → OpenEMR provider ID
        doctor_info = OPENEMR_DOCTORS.get(user.brans)
        if doctor_info:
            provider_id = doctor_info.get("openemr_user_id")
            filtered_by = user.brans

    # Fetch from OpenEMR
    raw = await openemr_service.list_appointments(
        date=appointment_date,
        provider_id=provider_id,
    )

    appointments = [
        Appointment(
            id=a["id"],
            title=a["title"],
            date=a["date"],
            start_time=a["start_time"],
            end_time=a["end_time"],
            duration_seconds=a["duration_seconds"],
            provider_id=a["provider_id"],
            provider_name=f"{a['provider_fname']} {a['provider_lname']}".strip(),
            provider_username=a["provider_username"],
            patient_id=a["patient_id"],
            patient_name=f"{a['patient_fname']} {a['patient_lname']}".strip(),
            patient_ext_id=a.get("patient_ext_id", ""),
            status=a["status"],
            category_name=a["category_name"],
            category_color=a["category_color"],
            reason=a.get("reason", ""),
        )
        for a in raw
    ]

    return AppointmentListResponse(
        appointments=appointments,
        total=len(appointments),
        date=appointment_date,
        filtered_by=filtered_by,
    )
