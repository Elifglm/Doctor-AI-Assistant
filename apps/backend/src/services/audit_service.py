"""Audit logging service -- writes to the audit_log table."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from apps.backend.src.db.models import AuditLog


class AuditService:
    """Thin wrapper for writing audit log entries."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def log(
        self,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        user_id: Optional[str] = None,
        details: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        """Persist a single audit event.  Never logs PHI."""
        entry = AuditLog(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            details=details,
            ip_address=ip_address,
        )
        self._db.add(entry)
        await self._db.flush()
