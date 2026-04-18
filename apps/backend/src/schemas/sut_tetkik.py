"""Pydantic schemas for SUT tetkik endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SUTItem(BaseModel):
    kodu: str
    adi: str
    brans: str
    ana_kategori: str = ""
    alt_kategori: str = ""
    puan: float = 0.0


class SUTSearchResponse(BaseModel):
    results: list[SUTItem]
    total: int


class SUTSuggestRequest(BaseModel):
    transcript_text: str | None = Field(default=None, min_length=1)
    report_sections: dict[str, str] | None = None
    brans: str | None = None


class SUTSuggestion(BaseModel):
    kodu: str
    adi: str
    brans: str = ""
    confidence: float
    reasoning: str = ""


class SUTSuggestResponse(BaseModel):
    suggestions: list[SUTSuggestion]


class SUTConfirmedTetkik(BaseModel):
    kodu: str
    adi: str
    brans: str = ""


class SUTConfirmRequest(BaseModel):
    report_id: int
    tetkikler: list[SUTConfirmedTetkik]


class SUTConfirmResponse(BaseModel):
    confirmed: bool
    tetkikler: list[SUTConfirmedTetkik]


class SUTOpenEMRSendRequest(BaseModel):
    session_id: int
    tetkikler: list[SUTConfirmedTetkik]
    notes: str = ""


class SUTOpenEMRSendResponse(BaseModel):
    success: bool
    order_id: str = ""
    patient_id: str = ""
    sent_count: int = 0
    filtered_count: int = 0
    error: str = ""
    doctor_brans: str = ""
