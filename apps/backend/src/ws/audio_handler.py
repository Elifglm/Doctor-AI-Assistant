"""WebSocket handler for audio streaming and ASR processing."""

import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.backend.src.db.models import Session as SessionModel, TranscriptionSegment
from apps.backend.src.services.asr_service import asr_service

logger = logging.getLogger(__name__)

# FFmpeg path
FFMPEG_DIR = (
    r"C:\Users\Huckleberry\AppData\Local\Microsoft\WinGet\Packages"
    r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-8.0.1-full_build\bin"
)
FFMPEG_PATH = os.path.join(FFMPEG_DIR, "ffmpeg.exe")

# Project data directory for recordings
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
RECORDINGS_DIR = _PROJECT_ROOT / "data" / "recordings"


class AudioHandler:
    """Handles a single WebSocket audio streaming session."""

    def __init__(self, ws: WebSocket, session_id: int, db: AsyncSession):
        self.ws = ws
        self.session_id = session_id
        self.db = db
        self._chunks: list[bytes] = []
        self._temp_webm: str | None = None

    async def handle(self) -> None:
        """Main loop: receive chunks until stop, then process."""
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
                    # Binary audio chunk
                    self._chunks.append(message["bytes"])
                elif "text" in message and message["text"]:
                    data = json.loads(message["text"])
                    if data.get("type") == "stop":
                        await self._process_recording()
                        break

        except WebSocketDisconnect:
            logger.info("WebSocket disconnected for session %d", self.session_id)
        except Exception as e:
            logger.error("WebSocket error for session %d: %s", self.session_id, str(e))
            await self._send_error(str(e))

    async def _process_recording(self) -> None:
        """Convert accumulated audio and run ASR pipeline."""
        if not self._chunks:
            await self._send_error("Ses verisi alinamadi")
            # Reset session status since no audio was recorded
            await self._reset_session_status("NOT_STARTED")
            return

        await self._send_progress("Stage 0/4", "Ses dosyasi hazirlaniyor...", 0.0)

        # Write chunks to temp webm file
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

        temp_webm = tempfile.NamedTemporaryFile(
            suffix=".webm", dir=str(RECORDINGS_DIR), delete=False
        )
        wav_path: str | None = None
        try:
            for chunk in self._chunks:
                temp_webm.write(chunk)
            temp_webm.close()
            self._temp_webm = temp_webm.name

            # Convert webm to wav using FFmpeg
            wav_path = temp_webm.name.replace(".webm", ".wav")
            await self._convert_to_wav(temp_webm.name, wav_path)

            # Update session status to PROCESSING
            result = await self.db.execute(
                select(SessionModel).where(SessionModel.id == self.session_id)
            )
            session = result.scalar_one_or_none()
            if session:
                session.status = "PROCESSING"
                session.audio_file_path = wav_path
                session.ended_at = datetime.now(timezone.utc)
                await self.db.commit()

            # Run ASR pipeline
            async def progress_cb(stage: str, message: str):
                progress_map = {
                    "Stage 0/4": 0.0,
                    "Stage 1/4": 0.25,
                    "Stage 2/4": 0.50,
                    "Stage 3/4": 0.75,
                    "Stage 4/4": 1.0,
                }
                progress = progress_map.get(stage, 0.0)
                await self._send_progress(stage, message, progress)

            asr_result = await asr_service.process_audio(wav_path, progress_cb)

            # Save segments to DB
            segments = await self._save_segments(asr_result)

            # Update session status
            if session:
                await self.db.refresh(session)
                session.status = "AWAITING_REVIEW"
                duration = asr_result.get("metadata", {}).get(
                    "audio_duration_seconds", 0
                )
                session.audio_duration_seconds = duration
                await self.db.commit()

            # Send result
            await self._send_result(segments, asr_result)

        except Exception as e:
            logger.error("Processing failed for session %d: %s", self.session_id, str(e))
            await self._send_error(f"Isleme hatasi: {str(e)[:200]}")
            await self._reset_session_status("NOT_STARTED")
            raise
        finally:
            # Clean up temp files
            if self._temp_webm and os.path.exists(self._temp_webm):
                try:
                    os.unlink(self._temp_webm)
                except OSError:
                    pass
            # Clean up WAV if processing failed (keep on success for records)
            if wav_path and os.path.exists(wav_path):
                # Only delete if session didn't reach AWAITING_REVIEW
                try:
                    result = await self.db.execute(
                        select(SessionModel).where(SessionModel.id == self.session_id)
                    )
                    session = result.scalar_one_or_none()
                    if session and session.status != "AWAITING_REVIEW":
                        os.unlink(wav_path)
                except Exception:
                    pass

    async def _reset_session_status(self, status: str) -> None:
        """Reset session status (used on error/disconnect cleanup)."""
        try:
            result = await self.db.execute(
                select(SessionModel).where(SessionModel.id == self.session_id)
            )
            session = result.scalar_one_or_none()
            if session and session.status in ("RECORDING", "PROCESSING"):
                session.status = status
                await self.db.commit()
        except Exception as e:
            logger.error("Failed to reset session %d status: %s", self.session_id, str(e))

    async def _convert_to_wav(self, input_path: str, output_path: str) -> None:
        """Convert webm/opus to 16kHz mono WAV using FFmpeg."""
        cmd = [
            FFMPEG_PATH,
            "-y",
            "-i", input_path,
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            output_path,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"FFmpeg donusumu basarisiz: {error_msg[:200]}")

    async def _save_segments(self, asr_result: dict[str, Any]) -> list[dict]:
        """Save transcription segments to DB."""
        from config.settings import DiarizationSettings

        default_labels = DiarizationSettings().default_labels

        raw_segments = asr_result.get("segments", [])
        saved = []

        for i, seg in enumerate(raw_segments):
            speaker = seg.get("speaker", "SPEAKER_00")
            speaker_label = default_labels.get(speaker, speaker)

            words = seg.get("words", [])
            words_json = json.dumps(words, ensure_ascii=False) if words else None

            db_seg = TranscriptionSegment(
                session_id=self.session_id,
                segment_index=i,
                text=seg.get("text", "").strip(),
                speaker=speaker,
                speaker_label=speaker_label,
                start_time=seg.get("start", 0.0),
                end_time=seg.get("end", 0.0),
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

    async def _send_result(self, segments: list[dict], asr_result: dict) -> None:
        """Send the transcription result to the client."""
        full_text = " ".join(s["text"] for s in segments)
        metadata = asr_result.get("metadata", {})

        await self._send_json({
            "type": "result",
            "session_id": self.session_id,
            "segments": segments,
            "full_text": full_text,
            "metadata": metadata,
        })

    async def _send_progress(
        self, stage: str, message: str, progress: float
    ) -> None:
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
            pass  # Connection may already be closed
