"""Report-related Pydantic schemas (matches api-spec.json)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ReportSection(BaseModel):
    key: str
    title: str
    content: str
    status: str  # "draft" | "approved" | "edited"
    confidence: Optional[str] = None  # "high" | "medium" | "low"


class ReportContent(BaseModel):
    sections: list[ReportSection]
    approved_sections: int
    total_sections: int


class GenerateReportRequest(BaseModel):
    session_id: int
    method: str = "manual"  # "manual" | "ai_generated"


class UpdateReportRequest(BaseModel):
    content: Optional[ReportContent] = None
    status: Optional[str] = None  # "DRAFT" | "REVIEWED" | "APPROVED" | "FINALIZED"


class ReportResponse(BaseModel):
    id: int
    session_id: int
    version: int
    status: str
    content: ReportContent
    generation_method: Optional[str] = None
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
