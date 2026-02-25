"""Transcription-related Pydantic schemas (matches api-spec.json)."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel


class TranscriptionSegment(BaseModel):
    id: int
    session_id: int
    segment_index: int
    text: str
    speaker: str
    speaker_label: str
    start_time: float
    end_time: float
    confidence: Optional[float] = None
    words: Optional[list[dict[str, Any]]] = None
    is_edited: Optional[bool] = None

    model_config = {"from_attributes": True}


class TranscriptionResponse(BaseModel):
    session_id: int
    segments: list[TranscriptionSegment]
    full_text: Optional[str] = None
    duration_seconds: Optional[float] = None
    num_speakers: Optional[int] = None


class WSProgress(BaseModel):
    type: Literal["progress"] = "progress"
    stage: str
    message: str
    progress: Optional[float] = None


class WSResult(BaseModel):
    type: Literal["result"] = "result"
    session_id: int
    segments: list[TranscriptionSegment]
    full_text: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class WSError(BaseModel):
    type: Literal["error"] = "error"
    message: str
    code: Optional[str] = None
