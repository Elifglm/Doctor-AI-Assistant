"""Report-related Pydantic schemas (matches api-spec.json)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


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
    # Number of similar past anamneses to retrieve as few-shot examples (RAG).
    # Frontend Settings page can override 3..10. Backward compat: omit -> 5.
    top_k: Optional[int] = Field(default=None, ge=3, le=10)


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
    openemr_encounter_id: Optional[int] = None
    openemr_synced: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}
