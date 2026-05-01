"""SQLAlchemy ORM models for the Doctor AI Assistant database."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


class Session(Base):
    __tablename__ = "sessions"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    patient_id: str = Column(String(50), nullable=True, default="")
    patient_name: str = Column(String(200), nullable=True, default="")
    doctor_name: str = Column(String(200), nullable=False)
    # Canonical owner identifier — the username of the user who created the
    # session. Used for ownership / permission checks. doctor_name is a
    # free-text display field (often pre-filled from external systems like
    # OpenEMR) and is NOT reliable for authorization.
    doctor_username: str = Column(String(100), nullable=True, default="")
    # Doctor's specialty captured at session-create time. Used by the report
    # pipeline to choose the anamnesis template (dahiliye / ortopedi / ...).
    doctor_brans: str = Column(String(50), nullable=True, default="")
    visit_type: str = Column(String(50), nullable=False, default="ilk_muayene")
    status: str = Column(String(50), nullable=False, default="NOT_STARTED")
    pre_diagnosis: str = Column(Text, nullable=True, default="")
    location: str = Column(String(200), nullable=True, default="")
    audio_file_path: str = Column(String(500), nullable=True)
    kvkk_consent: bool = Column(Boolean, nullable=False, default=False)
    started_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    ended_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    audio_duration_seconds: float | None = Column(Float, nullable=True)
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    segments = relationship(
        "TranscriptionSegment", back_populates="session", cascade="all, delete-orphan"
    )
    reports = relationship(
        "Report", back_populates="session", cascade="all, delete-orphan"
    )


class TranscriptionSegment(Base):
    __tablename__ = "transcription_segments"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    session_id: int = Column(
        Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    segment_index: int = Column(Integer, nullable=False)
    text: str = Column(Text, nullable=False)
    speaker: str = Column(String(50), nullable=False)
    speaker_label: str = Column(String(100), nullable=False)
    start_time: float = Column(Float, nullable=False)
    end_time: float = Column(Float, nullable=False)
    confidence: float | None = Column(Float, nullable=True)
    words_json: str | None = Column(Text, nullable=True)
    is_edited: bool = Column(Boolean, nullable=False, default=False)
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    session = relationship("Session", back_populates="segments")

    @property
    def words(self) -> list | None:
        """Parse words_json for Pydantic serialization."""
        if self.words_json:
            return json.loads(self.words_json)
        return None


class Report(Base):
    __tablename__ = "reports"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    session_id: int = Column(
        Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    version: int = Column(Integer, nullable=False, default=1)
    status: str = Column(String(50), nullable=False, default="DRAFT")
    content_json: str | None = Column(Text, nullable=True)
    generation_method: str = Column(String(50), nullable=False, default="manual")
    approved_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    approved_by: str | None = Column(String(200), nullable=True)
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    session = relationship("Session", back_populates="reports")

    @property
    def content(self) -> dict:
        """Parse content_json for Pydantic serialization."""
        if self.content_json:
            return json.loads(self.content_json)
        return {"sections": [], "approved_sections": 0, "total_sections": 12}


class User(Base):
    __tablename__ = "users"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    username: str = Column(String(100), unique=True, nullable=False)
    hashed_password: str = Column(String(255), nullable=False)
    display_name: str = Column(String(200), nullable=False)
    role: str = Column(String(50), nullable=False, default="doctor")
    brans: str = Column(String(50), nullable=False, default="")
    is_active: bool = Column(Boolean, nullable=False, default=True)
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    timestamp: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    user_id: str | None = Column(String(100), nullable=True)
    action: str = Column(String(100), nullable=False)
    resource_type: str = Column(String(100), nullable=True)
    resource_id: str | None = Column(String(100), nullable=True)
    details: str | None = Column(Text, nullable=True)
    ip_address: str | None = Column(String(45), nullable=True)
