"""WebSocket handler: ses kayit + batch ASR isleme."""

import json
import logging
import os
import re
import shutil
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.backend.src.asr.audio_utils import AudioAccumulator
from apps.backend.src.db.models import Session as SessionModel, TranscriptionSegment
from apps.backend.src.services.asr_service import asr_service

logger = logging.getLogger(__name__)

# Kayit dizini
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
RECORDINGS_DIR = _PROJECT_ROOT / "data" / "recordings"

# ---------------------------------------------------------------------------
# Active connection registry (one per session)
# ---------------------------------------------------------------------------
_active_connections: dict[int, WebSocket] = {}


def is_session_connected(session_id: int) -> bool:
    return session_id in _active_connections


def get_active_websocket(session_id: int) -> WebSocket | None:
    return _active_connections.get(session_id)


def register_connection(session_id: int, ws: WebSocket) -> None:
    _active_connections[session_id] = ws
    logger.info("WS registered for session %d", session_id)


def unregister_connection(session_id: int) -> None:
    removed = _active_connections.pop(session_id, None)
    if removed is not None:
        logger.info("WS unregistered for session %d", session_id)


class AudioHandler:
    """Batch ASR WebSocket handler.

    Akis:
    1. Binary chunk'lar gelir → sadece biriktirilir (ASR islemi YOK)
    2. {type: "stop"} gelir → WAV'a donustur → batch pipeline calistir
    3. Sonuc + rapor olusturulur → frontend'e gonderilir
    """

    def __init__(self, ws: WebSocket, session_id: int, db: AsyncSession) -> None:
        self.ws = ws
        self.session_id = session_id
        self.db = db
        self._accumulator = AudioAccumulator()

    async def handle(self) -> None:
        """Ana WebSocket dongusu."""
        try:
            await self._send_json({
                "type": "status",
                "message": "Baglanti kuruldu, kayit baslatilabilir",
            })

            while True:
                message = await self.ws.receive()

                if message.get("type") == "websocket.disconnect":
                    break

                if "bytes" in message and message["bytes"]:
                    # Sadece biriktir — ASR islemi yok
                    self._accumulator.add_raw(message["bytes"])

                elif "text" in message and message["text"]:
                    data = json.loads(message["text"])
                    msg_type = data.get("type")

                    if msg_type == "stop":
                        await self._process_recording()
                        break

                    if msg_type == "replay":
                        replay_path = data.get("path")
                        await self._process_replay(replay_path)
                        break

        except WebSocketDisconnect:
            logger.info("WS disconnected for session %d", self.session_id)
        except Exception as e:
            logger.error("WS error for session %d: %s", self.session_id, str(e))
            await self._send_error(str(e))

    # ── Batch Processing ────────────────────────────────────────────

    def _patient_dir(self, patient_id: str) -> Path:
        """Hasta-keyed klasör. patient_id güvenli karakterlere indirgenir."""
        safe_pid = re.sub(r"[^a-zA-Z0-9_-]", "_", patient_id or "")[:50] or "unknown"
        return RECORDINGS_DIR / f"patient_{safe_pid}"

    async def _process_recording(self) -> None:
        """Biriktirilmis sesi WAV'a donustur ve batch pipeline calistir."""
        if not self._accumulator.has_data:
            await self._send_error("Ses verisi alinamadi")
            await self._reset_session_status("NOT_STARTED")
            return

        await self._send_json({
            "type": "processing_start",
            "message": "Isleme basliyor...",
        })

        wav_path: str | None = None
        try:
            # Session'ı önce oku — WAV path'i hasta-keyed klasöre yazmak için
            # patient_id'ye ihtiyacımız var.
            session = await self._get_session()
            patient_id = (session.patient_id if session else "") or "unknown"
            patient_dir = self._patient_dir(patient_id)
            patient_dir.mkdir(parents=True, exist_ok=True)
            wav_path = str(
                patient_dir / f"session_{self.session_id}_{int(time.time())}.wav"
            )
            wav_path = await self._accumulator.save_wav(wav_path)

            await self._run_pipeline(wav_path)

        except Exception as e:
            tb = traceback.format_exc()
            logger.error(
                "Processing failed for session %d: %s\n%s",
                self.session_id, repr(e), tb,
            )
            error_detail = repr(e) if not str(e) else str(e)
            await self._send_error(f"Isleme hatasi: {error_detail[:500]}")
            await self._reset_session_status("NOT_STARTED")
        finally:
            if wav_path and os.path.exists(wav_path):
                try:
                    # Test modu açıksa hiç silme — admin'in/doktorun replay
                    # edebilmesi için tüm WAV'lar diskte kalır.
                    keep = bool(getattr(self.ws.app.state, "keep_recordings", False))
                    if not keep:
                        session = await self._get_session()
                        if session and session.status != "AWAITING_REVIEW":
                            os.unlink(wav_path)
                except Exception:
                    pass

    async def _process_replay(self, src_path: str | None) -> None:
        """Mevcut bir WAV'ı bu session için kopyala ve pipeline'ı çalıştır.

        Test modu açıkken kullanılır — eski bir kayıttan yeni session türetir.
        Kaynak path RECORDINGS_DIR içinde olmak zorunda (path traversal koruması).
        """
        if not src_path:
            await self._send_error("Kayıt yolu belirtilmedi")
            await self._reset_session_status("NOT_STARTED")
            return

        try:
            src = Path(src_path).resolve()
            recordings_root = RECORDINGS_DIR.resolve()
            src.relative_to(recordings_root)
        except (ValueError, OSError):
            await self._send_error("Kayıt yolu geçersiz")
            await self._reset_session_status("NOT_STARTED")
            return

        if not src.is_file():
            await self._send_error("Kaynak ses kaydı bulunamadı")
            await self._reset_session_status("NOT_STARTED")
            return

        await self._send_json({
            "type": "processing_start",
            "message": "Mevcut kayıt işleniyor...",
        })

        dst_path: str | None = None
        try:
            session = await self._get_session()
            patient_id = (session.patient_id if session else "") or "unknown"
            patient_dir = self._patient_dir(patient_id)
            patient_dir.mkdir(parents=True, exist_ok=True)
            dst_path = str(
                patient_dir / f"session_{self.session_id}_{int(time.time())}.wav"
            )
            # Yeni session için kendi kopyasını oluştur — kaynak WAV bozulmaz.
            shutil.copy2(src, dst_path)

            await self._run_pipeline(dst_path)

        except Exception as e:
            tb = traceback.format_exc()
            logger.error(
                "Replay failed for session %d: %s\n%s",
                self.session_id, repr(e), tb,
            )
            error_detail = repr(e) if not str(e) else str(e)
            await self._send_error(f"Isleme hatasi: {error_detail[:500]}")
            await self._reset_session_status("NOT_STARTED")
        finally:
            if dst_path and os.path.exists(dst_path):
                try:
                    keep = bool(getattr(self.ws.app.state, "keep_recordings", False))
                    if not keep:
                        session = await self._get_session()
                        if session and session.status != "AWAITING_REVIEW":
                            os.unlink(dst_path)
                except Exception:
                    pass

    async def _run_pipeline(self, wav_path: str) -> None:
        """Diskteki bir WAV üzerinde ASR + segment kaydet + raporu üret."""
        session = await self._get_session()
        if session:
            session.status = "PROCESSING"
            session.audio_file_path = wav_path
            session.ended_at = datetime.now(timezone.utc)
            await self.db.commit()

        async def progress_cb(stage: str, message: str, progress: float) -> None:
            await self._send_progress(stage, message, progress)

        result = await asr_service.process_recording(wav_path, progress_cb)
        segments = await self._save_segments(result)

        if session:
            await self.db.refresh(session)
            session.status = "AWAITING_REVIEW"
            duration = result.get("metadata", {}).get("audio_duration_seconds", 0)
            session.audio_duration_seconds = duration
            await self.db.commit()

        await self._send_result(segments, result)
        await self._auto_generate_report(segments)

    # ── DB Operations ───────────────────────────────────────────────

    async def _get_session(self) -> SessionModel | None:
        result = await self.db.execute(
            select(SessionModel).where(SessionModel.id == self.session_id)
        )
        return result.scalar_one_or_none()

    async def _save_segments(self, asr_result: dict[str, Any]) -> list[dict]:
        """Transkripsiyon segment'lerini DB'ye kaydet."""
        raw_segments = asr_result.get("segments", [])
        saved: list[dict] = []

        for i, seg in enumerate(raw_segments):
            speaker = seg.get("speaker", "SPEAKER_00")
            speaker_label = seg.get("speaker_label", speaker)
            words = seg.get("words", [])
            words_json = json.dumps(words, ensure_ascii=False) if words else None

            db_seg = TranscriptionSegment(
                session_id=self.session_id,
                segment_index=i,
                text=seg.get("text", "").strip(),
                speaker=speaker,
                speaker_label=speaker_label,
                start_time=seg.get("start_time", seg.get("start", 0.0)),
                end_time=seg.get("end_time", seg.get("end", 0.0)),
                confidence=None,
                words_json=words_json,
                is_edited=False,
            )
            self.db.add(db_seg)
            saved.append({
                "segment_index": i,
                "text": db_seg.text,
                "speaker": speaker,
                "speaker_label": speaker_label,
                "start_time": db_seg.start_time,
                "end_time": db_seg.end_time,
                "words": words,
            })

        await self.db.commit()
        return saved

    async def _lookup_doctor_brans(self) -> str:
        """Return the brans stored on the session (set at session-create time)."""
        try:
            session = await self._get_session()
            if session is None:
                return ""
            return getattr(session, "doctor_brans", "") or ""
        except Exception:
            logger.exception("Failed to read doctor brans for session %d", self.session_id)
            return ""

    async def _auto_generate_report(self, segments: list[dict]) -> None:
        """Otomatik anamnez raporu olustur."""
        try:
            await self._send_progress("Stage 4/4", "Anamnez raporu olusturuluyor...", 0.95)

            app = self.ws.app  # type: ignore[attr-defined]
            report_generator = getattr(app.state, "report_generator", None)
            if report_generator is None:
                logger.warning("report_generator not available")
                return

            brans = await self._lookup_doctor_brans()
            report_content = await report_generator.generate_report(segments, brans=brans)

            from apps.backend.src.services.report_service import ReportService
            svc = ReportService(self.db)
            report = await svc.generate_with_content(
                self.session_id, report_content, method="ai_generated"
            )
            await self.db.commit()

            await self._send_json({
                "type": "report_ready",
                "session_id": self.session_id,
                "report_id": report.id,
                "message": "Anamnez raporu olusturuldu",
            })
            logger.info("Auto-generated report for session %d", self.session_id)

        except Exception:
            logger.exception("Auto report failed for session %d", self.session_id)
            await self._send_json({
                "type": "report_warning",
                "message": "Otomatik rapor olusturulamadi, manuel olusturabilirsiniz",
            })

    async def _reset_session_status(self, status: str) -> None:
        try:
            session = await self._get_session()
            if session and session.status in ("RECORDING", "PROCESSING"):
                session.status = status
                await self.db.commit()
        except Exception as e:
            logger.error("Failed to reset session %d: %s", self.session_id, str(e))

    # ── WebSocket Messaging ─────────────────────────────────────────

    async def _send_result(self, segments: list[dict], asr_result: dict) -> None:
        full_text = " ".join(s["text"] for s in segments)
        metadata = asr_result.get("metadata", {})
        await self._send_json({
            "type": "result",
            "session_id": self.session_id,
            "segments": segments,
            "full_text": full_text,
            "metadata": metadata,
        })

    async def _send_progress(self, stage: str, message: str, progress: float) -> None:
        await self._send_json({
            "type": "progress",
            "stage": stage,
            "message": message,
            "progress": progress,
        })

    async def _send_error(self, message: str) -> None:
        await self._send_json({
            "type": "error",
            "message": message,
            "code": "PROCESSING_ERROR",
        })

    async def _send_json(self, data: dict) -> None:
        try:
            await self.ws.send_json(data)
        except Exception:
            pass
