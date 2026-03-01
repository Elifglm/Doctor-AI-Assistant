"""Data management Pydantic schemas."""

from __future__ import annotations

from apps.backend.src.schemas.common import BaseResponse


class PurgeResponse(BaseResponse):
    """Response returned after purging all application data."""

    deleted_sessions: int
    deleted_segments: int
    deleted_reports: int
    deleted_audit_logs: int
    total_deleted: int
