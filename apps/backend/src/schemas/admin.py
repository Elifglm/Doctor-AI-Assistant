"""Pydantic schemas for admin user management endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=3, max_length=100)
    display_name: str = Field(min_length=1, max_length=200)
    role: str = Field(default="doctor", pattern=r"^(admin|doctor)$")
    brans: str = Field(default="", pattern=r"^(dahiliye|ortopedi|)$")


class UserUpdateRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    role: Optional[str] = Field(default=None, pattern=r"^(admin|doctor)$")
    brans: Optional[str] = Field(default=None, pattern=r"^(dahiliye|ortopedi|)$")
    is_active: Optional[bool] = None


class UserPasswordChangeRequest(BaseModel):
    new_password: str = Field(min_length=3, max_length=100)


class UserResponse(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    brans: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int


class OpenEMRDoctor(BaseModel):
    openemr_id: str
    username: str
    fname: str
    lname: str
    specialty: str
    already_in_system: bool = False


class OpenEMRSyncResponse(BaseModel):
    doctors: list[OpenEMRDoctor]
    new_count: int
    total_count: int
