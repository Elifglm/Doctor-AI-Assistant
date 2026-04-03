"""Pydantic schemas for ICD-10 endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ICD10Item(BaseModel):
    icd_kodu: str
    tani: str
    ust_kod: str | None = None
    seviye: int


class ICD10SearchResponse(BaseModel):
    results: list[ICD10Item]
    total: int


class ICD10SuggestRequest(BaseModel):
    transcript_text: str = Field(..., min_length=1)


class ICD10Suggestion(BaseModel):
    icd_kodu: str
    tani: str
    confidence: float
    reasoning: str = ""


class ICD10SuggestResponse(BaseModel):
    suggestions: list[ICD10Suggestion]


class ICD10ConfirmedCode(BaseModel):
    icd_kodu: str
    tani: str
    tani_tipi: str = "on_tani"  # "on_tani" | "kesin_tani"


class ICD10ConfirmRequest(BaseModel):
    report_id: int
    codes: list[ICD10ConfirmedCode]


class ICD10ConfirmResponse(BaseModel):
    confirmed: bool
    codes: list[ICD10ConfirmedCode]
