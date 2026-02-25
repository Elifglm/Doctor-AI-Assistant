"""Pyannote 3.1 konusmaci ayristirma modulu."""

from __future__ import annotations

import logging

import whisperx
from whisperx.diarize import DiarizationPipeline

from config.settings import DiarizationSettings
from src.exceptions import ConfigurationError, DiarizationError
from src.gpu_manager import GPUManager

logger = logging.getLogger(__name__)


class Diarizer:
    """Pyannote 3.1 ile konusmaci ayristirma ve etiketleme."""

    def __init__(
        self,
        settings: DiarizationSettings,
        hf_token: str,
        gpu_manager: GPUManager,
    ):
        self.settings = settings
        self.hf_token = hf_token
        self.gpu = gpu_manager
        self.pipeline = None

    def load_model(self) -> None:
        """
        WhisperX DiarizationPipeline yukle.

        Gerekli HuggingFace model sozlesmeleri:
          - pyannote/speaker-diarization-3.1
          - pyannote/segmentation-3.0
        """
        if not self.hf_token:
            raise ConfigurationError(
                "HuggingFace token gerekli. .env dosyasina HF_TOKEN=hf_xxx ekleyin. "
                "Ayrica su model sozlesmelerini kabul edin:\n"
                "  - https://huggingface.co/pyannote/speaker-diarization-3.1\n"
                "  - https://huggingface.co/pyannote/segmentation-3.0"
            )

        try:
            self.pipeline = DiarizationPipeline(
                model_name="pyannote/speaker-diarization-3.1",
                token=self.hf_token,
                device="cuda",
            )
            self.gpu.register_model("pyannote", self.pipeline)
            logger.info("Pyannote diarization pipeline yuklendi")
        except Exception as e:
            raise DiarizationError(
                f"Diarization pipeline yuklenemedi: {e}"
            ) from e

    def diarize(self, audio_path: str) -> dict:
        """
        Ses dosyasini analiz et, konusmaci segmentlerini dondur.

        Args:
            audio_path: Ses dosyasi yolu.

        Returns:
            Konusmaci segmentleri.
        """
        if self.pipeline is None:
            raise DiarizationError(
                "Pipeline yuklenmemis, once load_model() cagirilmali"
            )

        try:
            logger.info("Konusmaci ayristirma basliyor: %s", audio_path)
            result = self.pipeline(
                audio_path,
                min_speakers=self.settings.min_speakers,
                max_speakers=self.settings.max_speakers,
            )
            logger.info("Konusmaci ayristirma tamamlandi")
            return result
        except Exception as e:
            raise DiarizationError(f"Diarization hatasi: {e}") from e

    def assign_speakers(self, diarize_segments, aligned_result: dict) -> dict:
        """
        Her kelimeyi konusmaciya ata ve etiketle.

        SPEAKER_00 -> "Doktor", SPEAKER_01 -> "Hasta" olarak etiketlenir.

        Args:
            diarize_segments: Diarization sonucu.
            aligned_result: Hizalanmis transkripsiyon sonucu.

        Returns:
            Konusmaci etiketli segmentler.
        """
        try:
            result = whisperx.assign_word_speakers(diarize_segments, aligned_result)

            for segment in result.get("segments", []):
                speaker_id = segment.get("speaker", "UNKNOWN")
                segment["speaker_label"] = self.settings.default_labels.get(
                    speaker_id, speaker_id
                )

            speakers = set(s.get("speaker") for s in result.get("segments", []))
            logger.info(
                "Konusmaci atama tamamlandi: %d farkli konusmaci", len(speakers)
            )
            return result
        except Exception as e:
            raise DiarizationError(f"Konusmaci atama hatasi: {e}") from e

    def unload_model(self) -> None:
        """Pipeline'i bosalt."""
        self.gpu.unload_model("pyannote")
        self.pipeline = None
        self.gpu.cleanup()
        logger.info("Pyannote pipeline bosaltildi")
