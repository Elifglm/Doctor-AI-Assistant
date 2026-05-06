"""Batch ASR servisi - async pipeline yonetimi."""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

from apps.backend.src.asr.pipeline import BatchASRPipeline
from apps.backend.src.asr.settings import ASRSettings

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


class ASRService:
    """Batch ASR pipeline async yonetici.

    Tek seferde bir islem (GPU kaynak korumasi).
    """

    def __init__(self) -> None:
        self._pipeline: BatchASRPipeline | None = None
        self._lock = asyncio.Lock()
        self._process_lock = asyncio.Lock()
        self._initialized = False
        self._using_gpu = False
        self._ner_service: Any = None

    def set_ner_service(self, ner_service: Any) -> None:
        """Inject NERService for speaker classification (Doktor vs Hasta).

        Optional — if provided, BatchASRPipeline will use it after diarization
        to relabel speakers based on entity distribution. Should be called
        before initialize() or before the first process_recording() call.
        """
        self._ner_service = ner_service
        if self._pipeline is not None:
            self._pipeline.set_ner_service(ner_service)

    async def initialize(self) -> None:
        """Pipeline olustur (modelleri yuklemez, lazy init)."""
        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return

            settings = ASRSettings()

            # GPU algilama
            gpu_available = False
            try:
                import torch
                gpu_available = torch.cuda.is_available()
            except ImportError:
                pass

            if not gpu_available and settings.cpu_fallback:
                logger.warning("CUDA yok, CPU moduna geciliyor (compute=%s)",
                               settings.cpu_compute_type)
                settings.transcription.device = "cpu"
                settings.transcription.compute_type = settings.cpu_compute_type
                settings.transcription.batch_size = 4

            self._using_gpu = gpu_available
            self._pipeline = BatchASRPipeline(settings, ner_service=self._ner_service)
            self._initialized = True

            logger.info("ASR servisi baslatildi (gpu=%s, ner=%s)",
                        gpu_available, self._ner_service is not None)

    async def process_recording(
        self,
        wav_path: str,
        progress_callback: Any = None,
    ) -> dict:
        """WAV dosyasini isle: transcribe + post-process + diarize.

        Args:
            wav_path: WAV dosya yolu
            progress_callback: async(stage, message, progress)

        Returns:
            {"segments": [...], "metadata": {...}}
        """
        await self.initialize()

        if self._pipeline is None:
            raise RuntimeError("Pipeline baslatilmamis")

        if self._process_lock.locked():
            logger.warning("Onceki islem hala calisiyor, bekleniyor...")

        async with self._process_lock:
            return await self._pipeline.process(wav_path, progress_callback)

    @property
    def is_ready(self) -> bool:
        return self._initialized

    @property
    def is_busy(self) -> bool:
        return self._process_lock.locked()

    @property
    def using_gpu(self) -> bool:
        return self._using_gpu


asr_service = ASRService()
