"""Session-related Pydantic schemas (matches api-spec.json)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from apps.backend.src.schemas.transcription import TranscriptionSegment
from apps.backend.src.schemas.report import ReportResponse


class CreateSessionRequest(BaseModel):
    patient_id: str = ""
    patient_name: str = ""
    doctor_name: str
    visit_type: str = "ilk_muayene"
    pre_diagnosis: str = ""
    location: str = ""
    kvkk_consent: bool


class UpdateSessionRequest(BaseModel):
    status: Optional[str] = None
    patient_id: Optional[str] = None
    patient_name: Optional[str] = None
    pre_diagnosis: Optional[str] = None
    location: Optional[str] = None
    audio_file_path: Optional[str] = None
    audio_duration_seconds: Optional[float] = None


class SessionResponse(BaseModel):
    id: int
    patient_id: Optional[str] = None
    patient_name: Optional[str] = None
    doctor_name: str
    visit_type: str
    status: str
    pre_diagnosis: Optional[str] = None
    location: Optional[str] = None
    audio_file_path: Optional[str] = None
    kvkk_consent: Optional[bool] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    audio_duration_seconds: Optional[float] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SessionListResponse(BaseModel):
    items: list[SessionResponse]
    total: int
    page: int
    limit: int
    pages: int


class SessionDetailResponse(SessionResponse):
    segments: list[TranscriptionSegment] = []
    reports: list[ReportResponse] = []
