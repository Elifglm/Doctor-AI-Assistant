"""Wrapper around the existing ASR pipeline for async usage."""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Ensure project root is on path for src/config imports
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


class ASRService:
    """Async wrapper for the synchronous ASRPipeline."""

    def __init__(self):
        self._pipeline = None
        self._lock = asyncio.Lock()
        self._process_lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """Lazy-load the ASR pipeline (heavy GPU initialization)."""
        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            # Import here to avoid slow startup
            from src.pipeline import ASRPipeline
            from config.settings import AppSettings

            self._pipeline = ASRPipeline(AppSettings())
            self._initialized = True
            logger.info("ASR pipeline initialized successfully")

    async def process_audio(
        self,
        audio_path: str,
        progress_callback=None,
    ) -> dict[str, Any]:
        """
        Process audio through the full ASR pipeline in a separate thread.

        Only one processing job can run at a time (GPU resource protection).

        Args:
            audio_path: Path to the WAV file.
            progress_callback: async callable(stage: str, message: str).

        Returns:
            Pipeline result dict with segments, metadata etc.
        """
        await self.initialize()

        if self._process_lock.locked():
            raise RuntimeError(
                "ASR pipeline mesgul. Baska bir kayit isleniyor, lutfen bekleyin."
            )

        async with self._process_lock:
            loop = asyncio.get_event_loop()

            def sync_progress_cb(stage: str, message: str):
                if progress_callback:
                    asyncio.run_coroutine_threadsafe(
                        progress_callback(stage, message), loop
                    )

            result = await asyncio.to_thread(
                self._pipeline.process, audio_path, sync_progress_cb
            )
            return result

    @property
    def is_ready(self) -> bool:
        return self._initialized

    @property
    def is_busy(self) -> bool:
        return self._process_lock.locked()


# Singleton instance
asr_service = ASRService()
