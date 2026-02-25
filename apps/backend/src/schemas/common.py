"""Common / shared Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel


class BaseResponse(BaseModel):
    """Base response model with an optional message field."""
    message: str = ""
