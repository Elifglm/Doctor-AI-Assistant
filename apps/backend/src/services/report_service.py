"""Report CRUD service -- async operations on the reports table."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.backend.src.db.models import Report
from apps.backend.src.schemas.report import UpdateReportRequest

# 12-section Turkish anamnesis template
_ANAMNESIS_SECTIONS = [
    {"key": "chief_complaint", "title": "Basvuru Sikayeti", "content": "", "status": "draft", "confidence": "low"},
    {"key": "history_present", "title": "Simdiki Hastalik Hikayesi", "content": "", "status": "draft", "confidence": "low"},
    {"key": "past_medical", "title": "Gecmis Tibbi Ozgecmis", "content": "", "status": "draft", "confidence": "low"},
    {"key": "medications", "title": "Kullanilan Ilaclar", "content": "", "status": "draft", "confidence": "low"},
    {"key": "allergies", "title": "Alerjiler", "content": "", "status": "draft", "confidence": "low"},
    {"key": "family_history", "title": "Aile Oykusu", "content": "", "status": "draft", "confidence": "low"},
    {"key": "social_history", "title": "Sosyal Oyku", "content": "", "status": "draft", "confidence": "low"},
    {"key": "review_systems", "title": "Sistemlerin Gozden Gecirilmesi", "content": "", "status": "draft", "confidence": "low"},
    {"key": "physical_exam", "title": "Fizik Muayene", "content": "", "status": "draft", "confidence": "low"},
    {"key": "assessment", "title": "Degerlendirme", "content": "", "status": "draft", "confidence": "low"},
    {"key": "plan", "title": "Tedavi Plani", "content": "", "status": "draft", "confidence": "low"},
    {"key": "notes", "title": "Ek Notlar", "content": "", "status": "draft", "confidence": "low"},
]


class ReportService:
    """Encapsulates all DB operations for the Report model."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def generate(self, session_id: int, method: str = "manual") -> Report:
        """Generate a new report for a session.

        For 'manual' method: creates an empty 12-section anamnesis template.
        For 'ai_generated': placeholder (returns the same template; future LLM
        integration will populate sections from the transcript).
        """
        content = {
            "sections": list(_ANAMNESIS_SECTIONS),  # shallow copy
            "approved_sections": 0,
            "total_sections": 12,
        }

        # Determine the next version number for this session
        latest_version = await self._latest_version(session_id)
        next_version = latest_version + 1

        report = Report(
            session_id=session_id,
            version=next_version,
            status="DRAFT",
            content_json=json.dumps(content, ensure_ascii=False),
            generation_method=method,
        )
        self.db.add(report)
        await self.db.flush()
        await self.db.refresh(report)
        return report

    async def get_by_id(self, report_id: int) -> Report | None:
        """Return a single report by its primary key."""
        stmt = select(Report).where(Report.id == report_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, report_id: int, data: UpdateReportRequest) -> Report | None:
        """Update report content and/or status.

        When the status is changed to APPROVED the ``approved_at`` timestamp
        is set automatically.  A new version row is created so the previous
        state is preserved in the history.
        """
        stmt = select(Report).where(Report.id == report_id)
        result = await self.db.execute(stmt)
        report = result.scalar_one_or_none()
        if report is None:
            return None

        # Apply content update
        if data.content is not None:
            report.content_json = json.dumps(
                data.content.model_dump(), ensure_ascii=False,
            )

        # Apply status update
        if data.status is not None:
            report.status = data.status
            if data.status == "APPROVED":
                report.approved_at = datetime.now(timezone.utc)

        await self.db.flush()
        await self.db.refresh(report)
        return report

    async def get_versions(self, report_id: int) -> list[Report]:
        """Return all version rows that share the same session as *report_id*,
        ordered by version ascending."""
        # First find the session_id for the given report
        report = await self.get_by_id(report_id)
        if report is None:
            return []

        return await self.get_by_session(report.session_id)

    async def get_by_session(self, session_id: int) -> list[Report]:
        """Return every report version for *session_id* ordered by version."""
        stmt = (
            select(Report)
            .where(Report.session_id == session_id)
            .order_by(Report.version.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _latest_version(self, session_id: int) -> int:
        """Return the highest version number for a session, or 0."""
        from sqlalchemy import func

        stmt = (
            select(func.coalesce(func.max(Report.version), 0))
            .where(Report.session_id == session_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one()
