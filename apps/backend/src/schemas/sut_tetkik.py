"""Pydantic schemas for SUT tetkik endpoints."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class IntentLabel(str, Enum):
    """Intent classification for a tetkik mention in a doctor-patient transcript.

    Used to disambiguate doctor's verbal test ORDERS from past mentions /
    patient self-reports / hypothetical references. Only ``REQUEST`` items
    flow through to the doctor's confirmed test list.
    """
    REQUEST = "REQUEST"                  # doktorun simdi istedigi (capture)
    PAST_DONE = "PAST_DONE"              # gecmiste yapilmis (ignore)
    PATIENT_QUESTION = "PATIENT_QUESTION"  # hasta sormus / kendi anlatmis (ignore)
    RESULT_DISCUSS = "RESULT_DISCUSS"    # sonuc tartismasi (ignore)
    OTHER = "OTHER"                      # hipotetik / reddedilen / diger (ignore)
    NOT_REQUEST = "NOT_REQUEST"          # umbrella default (ignore)


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
    # Step 1 (intent sprint): debugging + intent disambiguation. Optional with
    # safe defaults — old clients that ignore them keep working.
    kaynak_cumle: str = ""                       # transkriptte tetik cumle (audit dis)
    intent_etiketi: IntentLabel = IntentLabel.REQUEST  # default REQUEST = legacy davranis


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
