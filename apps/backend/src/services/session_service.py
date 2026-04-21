"""Session CRUD service -- async operations on the sessions table."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.backend.src.db.models import Session
from apps.backend.src.schemas.session import CreateSessionRequest, UpdateSessionRequest


class SessionService:
    """Encapsulates all DB operations for the Session model."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, data: CreateSessionRequest) -> Session:
        """Insert a new session row and return the ORM object."""
        session = Session(
            patient_id=data.patient_id,
            patient_name=data.patient_name,
            doctor_name=data.doctor_name,
            visit_type=data.visit_type,
            pre_diagnosis=data.pre_diagnosis,
            location=data.location,
            kvkk_consent=data.kvkk_consent,
            status="NOT_STARTED",
        )
        self.db.add(session)
        await self.db.flush()
        await self.db.refresh(session)
        return session

    async def get_by_id(self, session_id: int) -> Session | None:
        """Return a single session with eager-loaded segments and reports."""
        stmt = (
            select(Session)
            .options(
                selectinload(Session.segments),
                selectinload(Session.reports),
            )
            .where(Session.id == session_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_sessions(
        self,
        status: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        search: Optional[str] = None,
        doctor_name: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
        sort: str = "created_at:desc",
    ) -> tuple[list[Session], int]:
        """Return a filtered, paginated list of sessions plus total count.

        ``sort`` must be ``"field:asc"`` or ``"field:desc"``.
        ``search`` matches against ``patient_id``, ``patient_name`` or ``doctor_name``.
        ``doctor_name`` filters by the exact doctor display name.
        """
        base = select(Session)

        # -- Filters --------------------------------------------------------
        if doctor_name:
            # Match both "Dr. Ahmet Yılmaz" and "Ahmet Yılmaz"
            name_without_prefix = doctor_name.replace("Dr. ", "").strip()
            base = base.where(
                or_(
                    Session.doctor_name == doctor_name,
                    Session.doctor_name == name_without_prefix,
                    Session.doctor_name == f"Dr. {name_without_prefix}",
                )
            )
        if status:
            base = base.where(Session.status == status)
        else:
            # Hide archived sessions by default
            base = base.where(Session.status != "ARCHIVED")
        if from_date:
            base = base.where(Session.created_at >= from_date)
        if to_date:
            base = base.where(Session.created_at <= to_date)
        if search:
            pattern = f"%{search}%"
            base = base.where(
                or_(
                    Session.patient_id.ilike(pattern),
                    Session.patient_name.ilike(pattern),
                    Session.doctor_name.ilike(pattern),
                )
            )

        # -- Total count (before pagination) --------------------------------
        count_stmt = select(func.count()).select_from(base.subquery())
        total: int = (await self.db.execute(count_stmt)).scalar_one()

        # -- Sorting --------------------------------------------------------
        parts = sort.split(":")
        field_name = parts[0] if parts else "created_at"
        direction = parts[1] if len(parts) > 1 else "desc"

        column = getattr(Session, field_name, Session.created_at)
        order = column.asc() if direction == "asc" else column.desc()
        base = base.order_by(order)

        # -- Pagination -----------------------------------------------------
        offset = (page - 1) * limit
        base = base.offset(offset).limit(limit)

        result = await self.db.execute(base)
        items: list[Session] = list(result.scalars().all())

        return items, total

    async def update(self, session_id: int, data: UpdateSessionRequest) -> Session | None:
        """Apply a partial update to an existing session."""
        stmt = select(Session).where(Session.id == session_id)
        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()
        if session is None:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(session, key, value)

        session.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(session)
        return session

    async def archive(self, session_id: int) -> bool:
        """Soft-delete a session by setting its status to ARCHIVED."""
        stmt = select(Session).where(Session.id == session_id)
        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()
        if session is None:
            return False

        session.status = "ARCHIVED"
        session.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return True
