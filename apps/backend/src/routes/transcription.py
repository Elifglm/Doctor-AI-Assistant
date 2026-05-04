"""Transcription routes -- /api/v1/sessions/{id}/transcription + WebSocket."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.backend.src.db.database import async_session_maker, get_db
from apps.backend.src.db.models import Session, TranscriptionSegment
from apps.backend.src.dependencies import get_audit_service, get_current_user
from apps.backend.src.schemas.auth import UserInfo
from apps.backend.src.schemas.transcription import (
    TranscriptionResponse,
    TranscriptionSegment as TranscriptionSegmentSchema,
)
from apps.backend.src.services.audit_service import AuditService
from apps.backend.src.ws.audio_handler import (
    AudioHandler,
    get_active_websocket,
    is_session_connected,
    register_connection,
    unregister_connection,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sessions", tags=["transcription"])


@router.get("/{session_id}/transcription", response_model=TranscriptionResponse)
async def get_transcription(
    session_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserInfo = Depends(get_current_user),
    audit: AuditService = Depends(get_audit_service),
) -> TranscriptionResponse:
    """Return all transcription segments for a session."""
    # Verify session exists and load segments
    stmt = (
        select(Session)
        .options(selectinload(Session.segments))
        .where(Session.id == session_id)
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    await audit.log(
        action="READ",
        resource_type="transcription",
        resource_id=str(session_id),
        user_id=user.username,
        ip_address=request.client.host if request.client else None,
    )

    # Build segment list ordered by segment_index
    sorted_segments = sorted(session.segments, key=lambda s: s.segment_index)
    segments = [
        TranscriptionSegmentSchema.model_validate(seg) for seg in sorted_segments
    ]

    # Assemble full text from segments
    full_text = " ".join(seg.text for seg in sorted_segments) if sorted_segments else None

    # Count unique speakers
    speakers = {seg.speaker for seg in sorted_segments}
    num_speakers = len(speakers) if speakers else None

    return TranscriptionResponse(
        session_id=session_id,
        segments=segments,
        full_text=full_text,
        duration_seconds=session.audio_duration_seconds,
        num_speakers=num_speakers,
    )


@router.websocket("/ws/{session_id}")
async def audio_websocket(websocket: WebSocket, session_id: int):
    """WebSocket endpoint for audio streaming and ASR processing.

    Full URL: ws://127.0.0.1:8700/api/v1/sessions/ws/{session_id}

    Protocol:
        1. Client sends binary audio chunks (webm/opus, ~250ms intervals).
        2. Client sends JSON ``{"type": "stop"}`` when recording finishes.
        3. Server converts audio, runs ASR pipeline, streams progress, and
           returns the transcription result as JSON.
    """
    await websocket.accept()

    # ---- Concurrent-connection guard (in-memory) ----
    # If a stale connection exists (e.g. from React StrictMode re-mount),
    # force-close it and let the new connection proceed ("last writer wins").
    if is_session_connected(session_id):
        old_ws = get_active_websocket(session_id)
        if old_ws is not None:
            logger.info(
                "Stale WS connection for session %d, replacing with new one",
                session_id,
            )
            try:
                await old_ws.send_json({
                    "type": "error",
                    "message": "Yeni baglanti geldi, eski baglanti kapatiliyor",
                    "code": "SUPERSEDED",
                })
                await old_ws.close()
            except Exception:
                pass  # Already dead
        unregister_connection(session_id)

    # Register this connection *before* any async DB work so that a second
    # connect attempt arriving in the meantime is rejected immediately.
    register_connection(session_id, websocket)

    async with async_session_maker() as db:
        try:
            # Verify session exists
            result = await db.execute(
                select(Session).where(Session.id == session_id)
            )
            session = result.scalar_one_or_none()
            if not session:
                await websocket.send_json({
                    "type": "error",
                    "message": "Gorusme bulunamadi",
                    "code": "NOT_FOUND",
                })
                await websocket.close()
                return

            # KVKK consent guard. The frontend already blocks the start button
            # without consent, but a direct WebSocket connection could bypass
            # that check — enforce it server-side as a defense-in-depth.
            if not session.kvkk_consent:
                await websocket.send_json({
                    "type": "error",
                    "message": "KVKK onayi alinmadan kayit baslatilamaz.",
                    "code": "KVKK_CONSENT_REQUIRED",
                })
                await websocket.close()
                return

            # Note: "RECORDING" status check removed. The in-memory connection
            # registry above already prevents true concurrent access. The DB
            # status check caused false rejections when the old WS's finally
            # block hadn't reset the status yet (race condition).

            # Update session status to RECORDING
            session.status = "RECORDING"
            session.started_at = datetime.now(timezone.utc)
            await db.commit()

            handler = AudioHandler(websocket, session_id, db)
            await handler.handle()
        except Exception as e:
            logger.error(
                "WebSocket endpoint error for session %d: %s",
                session_id,
                str(e),
            )
            try:
                await websocket.send_json({
                    "type": "error",
                    "message": str(e),
                    "code": "INTERNAL_ERROR",
                })
                await websocket.close()
            except Exception:
                pass
        finally:
            # Always unregister the connection so the session can be used again
            unregister_connection(session_id)

            # Reset session status if still RECORDING (disconnected without stop)
            try:
                result = await db.execute(
                    select(Session).where(Session.id == session_id)
                )
                session = result.scalar_one_or_none()
                if session and session.status == "RECORDING":
                    session.status = "NOT_STARTED"
                    session.started_at = None
                    await db.commit()
                    logger.info(
                        "Reset session %d status from RECORDING to NOT_STARTED (disconnect cleanup)",
                        session_id,
                    )
            except Exception as cleanup_err:
                logger.error(
                    "Failed to reset session %d status: %s",
                    session_id,
                    str(cleanup_err),
                )
