"""Audio recording management routes -- /api/v1/recordings.

Test/dev mode allows admins to keep WAV files on disk after processing so
recordings can be replayed against a fresh session. Off by default (PHI cleanup).
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.backend.src.db.database import get_db
from apps.backend.src.db.models import Session as SessionModel
from apps.backend.src.dependencies import get_audit_service, get_current_user
from apps.backend.src.schemas.auth import UserInfo
from apps.backend.src.services.audit_service import AuditService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/recordings", tags=["recordings"])

# Recordings root — must match audio_handler.RECORDINGS_DIR
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
RECORDINGS_DIR = (_PROJECT_ROOT / "data" / "recordings").resolve()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TestModeResponse(BaseModel):
    keep_recordings: bool


class TestModeUpdate(BaseModel):
    keep_recordings: bool


class RecordingItem(BaseModel):
    path: str  # absolute path; opaque token for the client
    filename: str
    session_id: int | None
    timestamp: int | None
    size_bytes: int


class RecordingListResponse(BaseModel):
    patient_id: str
    items: list[RecordingItem]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_patient_dir(patient_id: str) -> Path:
    safe_pid = re.sub(r"[^a-zA-Z0-9_-]", "_", patient_id)[:50] or "unknown"
    return RECORDINGS_DIR / f"patient_{safe_pid}"


def _validate_path_in_recordings(raw_path: str) -> Path:
    """Resolve and ensure the path stays inside RECORDINGS_DIR (no traversal)."""
    try:
        p = Path(raw_path).resolve()
    except (OSError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz yol."
        )
    try:
        p.relative_to(RECORDINGS_DIR)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Yol kayıt dizininin dışında.",
        )
    return p


_FILENAME_RE = re.compile(r"^session_(\d+)_(\d+)\.wav$")


def _parse_filename(name: str) -> tuple[int | None, int | None]:
    m = _FILENAME_RE.match(name)
    if not m:
        return (None, None)
    return (int(m.group(1)), int(m.group(2)))


# ---------------------------------------------------------------------------
# GET /api/v1/recordings/test-mode
# ---------------------------------------------------------------------------


@router.get("/test-mode", response_model=TestModeResponse)
async def get_test_mode(
    request: Request,
    user: UserInfo = Depends(get_current_user),
) -> TestModeResponse:
    """Return whether keep-recordings mode is on. All authenticated users may read."""
    keep = bool(getattr(request.app.state, "keep_recordings", False))
    return TestModeResponse(keep_recordings=keep)


# ---------------------------------------------------------------------------
# PUT /api/v1/recordings/test-mode  (admin only)
# ---------------------------------------------------------------------------


@router.put("/test-mode", response_model=TestModeResponse)
async def set_test_mode(
    body: TestModeUpdate,
    request: Request,
    user: UserInfo = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
) -> TestModeResponse:
    """Toggle keep-recordings mode. Admin only."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem için yönetici yetkisi gerekir.",
        )
    request.app.state.keep_recordings = bool(body.keep_recordings)
    await audit.log(
        action="UPDATE",
        resource_type="recordings_test_mode",
        resource_id=None,
        user_id=user.username,
        details=f"keep_recordings={body.keep_recordings}",
        ip_address=request.client.host if request.client else None,
    )
    logger.info(
        "Recordings test-mode set to %s by %s", body.keep_recordings, user.username
    )
    return TestModeResponse(keep_recordings=request.app.state.keep_recordings)


# ---------------------------------------------------------------------------
# GET /api/v1/recordings/by-patient/{patient_id}
# ---------------------------------------------------------------------------


@router.get("/by-patient/{patient_id}", response_model=RecordingListResponse)
async def list_recordings_by_patient(
    patient_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserInfo = Depends(get_current_user),
) -> RecordingListResponse:
    """List on-disk WAV files for a patient.

    Only returned when test mode is on — outside test mode, no recordings should
    be lingering on disk and the UI should not surface a selector.
    """
    keep = bool(getattr(request.app.state, "keep_recordings", False))
    if not keep:
        return RecordingListResponse(patient_id=patient_id, items=[])

    patient_dir = _safe_patient_dir(patient_id)
    if not patient_dir.exists():
        return RecordingListResponse(patient_id=patient_id, items=[])

    items: list[RecordingItem] = []
    for entry in patient_dir.iterdir():
        if not entry.is_file() or entry.suffix.lower() != ".wav":
            continue
        sid, ts = _parse_filename(entry.name)

        # Doctors may only see recordings for sessions they own. Admins see all.
        if user.role != "admin" and sid is not None:
            sess_q = await db.execute(
                select(SessionModel).where(SessionModel.id == sid)
            )
            sess = sess_q.scalar_one_or_none()
            if sess is None or (sess.doctor_username or "") != user.username:
                continue

        try:
            size = entry.stat().st_size
        except OSError:
            continue
        items.append(
            RecordingItem(
                path=str(entry.resolve()),
                filename=entry.name,
                session_id=sid,
                timestamp=ts,
                size_bytes=size,
            )
        )

    items.sort(key=lambda it: it.timestamp or 0, reverse=True)
    return RecordingListResponse(patient_id=patient_id, items=items)


# ---------------------------------------------------------------------------
# DELETE /api/v1/recordings?path=...
# ---------------------------------------------------------------------------


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recording(
    request: Request,
    path: str = Query(...),
    db: AsyncSession = Depends(get_db),
    user: UserInfo = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
) -> None:
    """Delete a WAV file. Admins may delete any; doctors only their own session's."""
    target = _validate_path_in_recordings(path)
    if not target.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Kayıt bulunamadı."
        )

    sid, _ = _parse_filename(target.name)
    if user.role != "admin":
        if sid is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu kaydı silmeye yetkiniz yok.",
            )
        sess_q = await db.execute(select(SessionModel).where(SessionModel.id == sid))
        sess = sess_q.scalar_one_or_none()
        if sess is None or (sess.doctor_username or "") != user.username:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu kaydı silmeye yetkiniz yok.",
            )

    try:
        os.unlink(target)
    except OSError as e:
        logger.warning("Failed to delete recording: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kayıt silinemedi.",
        )

    await audit.log(
        action="DELETE",
        resource_type="recording",
        resource_id=str(sid) if sid is not None else None,
        user_id=user.username,
        details=f"filename={target.name}",
        ip_address=request.client.host if request.client else None,
    )
    return None
