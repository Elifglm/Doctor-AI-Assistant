"""WhisperX transkripsiyon ve Wav2Vec2 hizalama modulu."""

from __future__ import annotations

import logging

import numpy as np
import whisperx

from config.settings import WhisperSettings
from src.exceptions import TranscriptionError
from src.gpu_manager import GPUManager

logger = logging.getLogger(__name__)


class Transcriber:
    """WhisperX + faster-whisper + Wav2Vec2 hizalama."""

    def __init__(
        self,
        settings: WhisperSettings,
        medical_prompt: str,
        gpu_manager: GPUManager,
    ):
        self.settings = settings
        self.medical_prompt = medical_prompt
        self.gpu = gpu_manager
        self.whisper_model = None
        self.align_model = None
        self.align_metadata = None

    def load_whisper_model(self) -> None:
        """
        WhisperX modelini yukle.

        - model: large-v3-turbo
        - compute_type: float16
        - language: tr
        - vad_method: silero (Windows uyumlulugu icin kritik)
        - initial_prompt: Turkce tibbi terimler
        """
        try:
            self.whisper_model = whisperx.load_model(
                self.settings.model_name,
                device=self.settings.device,
                compute_type=self.settings.compute_type,
                language=self.settings.language,
                vad_options={"vad_onset": 0.500, "vad_offset": 0.363},
                asr_options={"initial_prompt": self.medical_prompt},
            )
            self.gpu.register_model("whisper", self.whisper_model)
            logger.info(
                "Whisper modeli yuklendi: %s (%s)",
                self.settings.model_name,
                self.settings.compute_type,
            )
        except Exception as e:
            raise TranscriptionError(f"Whisper yuklenemedi: {e}") from e

    def transcribe(self, audio: np.ndarray) -> dict:
        """
        Toplu transkripsiyon.

        Args:
            audio: 16kHz mono ses verisi (numpy array).

        Returns:
            {"segments": [...], "language": "tr"}
        """
        if self.whisper_model is None:
            raise TranscriptionError(
                "Whisper modeli yuklenmemis, once load_whisper_model() cagirilmali"
            )

        try:
            logger.info("Transkripsiyon basliyor (batch_size=%d)", self.settings.batch_size)
            result = self.whisper_model.transcribe(
                audio,
                batch_size=self.settings.batch_size,
                language=self.settings.language,
            )
            segment_count = len(result.get("segments", []))
            logger.info("Transkripsiyon tamamlandi: %d segment", segment_count)
            return result
        except Exception as e:
            raise TranscriptionError(f"Transkripsiyon hatasi: {e}") from e

    def load_align_model(self) -> None:
        """
        Wav2Vec2 hizalama modelini yukle.

        Turkce icin otomatik olarak mpoyraz/wav2vec2-xls-r-300m-cv7-turkish secilir.
        """
        try:
            self.align_model, self.align_metadata = whisperx.load_align_model(
                language_code="tr",
                device=self.settings.device,
            )
            self.gpu.register_model("wav2vec2_align", self.align_model)
            logger.info("Wav2Vec2 hizalama modeli yuklendi (tr)")
        except Exception as e:
            raise TranscriptionError(f"Hizalama modeli yuklenemedi: {e}") from e

    def align(self, segments: dict, audio: np.ndarray) -> dict:
        """
        Kelime bazli zaman damgalari icin zorunlu hizalama.

        Args:
            segments: Transkripsiyon sonucu (transcribe() ciktisi).
            audio: 16kHz mono ses verisi.

        Returns:
            Her kelime icin start, end, score degerlerini iceren sonuc.
        """
        if self.align_model is None:
            raise TranscriptionError(
                "Hizalama modeli yuklenmemis, once load_align_model() cagirilmali"
            )

        try:
            logger.info("Kelime hizalama basliyor")
            result = whisperx.align(
                segments["segments"],
                self.align_model,
                self.align_metadata,
                audio,
                device=self.settings.device,
                return_char_alignments=False,
            )
            logger.info("Kelime hizalama tamamlandi")
            return result
        except Exception as e:
            raise TranscriptionError(f"Hizalama hatasi: {e}") from e

    def unload_all(self) -> None:
        """Tum modelleri bosalt."""
        self.gpu.unload_model("whisper")
        self.gpu.unload_model("wav2vec2_align")
        self.whisper_model = None
        self.align_model = None
        self.align_metadata = None
        self.gpu.cleanup()
        logger.info("Transkripsiyon modelleri bosaltildi")
