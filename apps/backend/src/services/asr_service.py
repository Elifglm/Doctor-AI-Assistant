"""Wrapper around the existing ASR pipeline for async usage with GPU->CPU fallback."""

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
    """Async wrapper for the synchronous ASRPipeline with GPU->CPU fallback."""

    def __init__(self):
        self._pipeline = None
        self._lock = asyncio.Lock()
        self._process_lock = asyncio.Lock()
        self._initialized = False
        self._using_gpu = False

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

            settings = AppSettings()

            # GPU availability check and fallback
            gpu_available = False
            try:
                import torch  # type: ignore[import-untyped]
                gpu_available = torch.cuda.is_available()
            except ImportError:
                pass

            if not gpu_available and settings.whisper.auto_fallback:
                logger.warning(
                    "CUDA mevcut degil, CPU moduna geciliyor "
                    "(device=%s, compute_type=%s, batch_size=4)",
                    settings.whisper.fallback_device,
                    settings.whisper.fallback_compute_type,
                )
                settings.whisper.device = settings.whisper.fallback_device
                settings.whisper.compute_type = settings.whisper.fallback_compute_type
                settings.whisper.batch_size = 4

            self._using_gpu = gpu_available
            self._pipeline = ASRPipeline(settings)

            # Monkey-patch diarizer.load_model for CPU mode
            # src/diarizer.py has device="cuda" hardcoded -- we can't modify src/
            if not gpu_available and settings.whisper.auto_fallback:
                self._patch_diarizer_for_cpu(settings)

            self._initialized = True
            logger.info(
                "ASR pipeline initialized (device=%s, gpu=%s)",
                settings.whisper.device,
                gpu_available,
            )

    def _patch_diarizer_for_cpu(self, settings: Any) -> None:
        """Override diarizer for CPU mode.

        If HF token is available, use CPU device for diarization.
        If HF token is missing, skip diarization entirely and assign
        all segments to a default speaker.
        """
        if self._pipeline is None:
            return

        diarizer = self._pipeline.diarizer

        if diarizer.hf_token:
            # HF token exists — use CPU device instead of hardcoded CUDA
            def patched_load_model() -> None:
                from whisperx.diarize import DiarizationPipeline
                try:
                    diarizer.pipeline = DiarizationPipeline(
                        model_name="pyannote/speaker-diarization-3.1",
                        token=diarizer.hf_token,
                        device="cpu",
                    )
                    diarizer.gpu.register_model("pyannote", diarizer.pipeline)
                    logger.info("Pyannote diarization pipeline yuklendi (CPU modu)")
                except Exception as e:
                    from src.exceptions import DiarizationError
                    raise DiarizationError(
                        f"Diarization pipeline yuklenemedi (CPU): {e}"
                    ) from e

            diarizer.load_model = patched_load_model
        else:
            # No HF token — skip diarization, assign default speaker
            logger.warning(
                "HF_TOKEN tanimli degil, konusmaci ayristirma atlanacak. "
                "Tum segmentler 'Doktor' olarak isaretlenecek."
            )
            diarizer.load_model = lambda: None
            diarizer.unload_model = lambda: None

            def skip_diarize(audio_path: str) -> dict:
                return {}

            def skip_assign(diarize_segments: dict, aligned_result: dict) -> dict:
                # Return aligned_result with default speaker assigned
                segments = aligned_result.get("segments", [])
                for seg in segments:
                    seg["speaker"] = "SPEAKER_00"
                return aligned_result

            diarizer.diarize = skip_diarize
            diarizer.assign_speakers = skip_assign

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

    @property
    def using_gpu(self) -> bool:
        return self._using_gpu


# Singleton instance
asr_service = ASRService()
