"""Ses yukleme, format donusumu ve dogrulama yardimci fonksiyonlari."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import torch
import torchaudio

from config.settings import AudioSettings
from src.exceptions import AudioLoadError

logger = logging.getLogger(__name__)

_DEFAULT_AUDIO = AudioSettings()


def load_and_validate(file_path: str) -> Path:
    """Ses dosyasinin varligini ve formatini dogrula."""
    path = Path(file_path)

    if not path.exists():
        raise AudioLoadError(f"Dosya bulunamadi: {file_path}")

    if not path.is_file():
        raise AudioLoadError(f"Gecerli bir dosya degil: {file_path}")

    if path.suffix.lower() not in _DEFAULT_AUDIO.supported_formats:
        raise AudioLoadError(
            f"Desteklenmeyen format: {path.suffix}. "
            f"Desteklenen: {_DEFAULT_AUDIO.supported_formats}"
        )

    logger.info("Ses dosyasi dogrulandi: %s", path.name)
    return path


def load_audio_for_whisperx(file_path: str) -> np.ndarray:
    """WhisperX icin ses yukle (16kHz mono)."""
    import whisperx

    audio = whisperx.load_audio(file_path)
    logger.info("Ses yuklendi: %s (%.1f saniye)", file_path, len(audio) / 16000)
    return audio


def save_enhanced_audio(
    audio_data: np.ndarray, sr: int, output_path: str
) -> str:
    """Islenmis sesi WAV dosyasina kaydet."""
    tensor = torch.from_numpy(audio_data)
    if tensor.dim() == 1:
        tensor = tensor.unsqueeze(0)
    torchaudio.save(output_path, tensor, sr)
    logger.info("Islenmis ses kaydedildi: %s", output_path)
    return output_path


def get_audio_duration(file_path: str) -> float:
    """Ses dosyasinin suresini saniye cinsinden dondur."""
    info = torchaudio.info(file_path)
    duration = info.num_frames / info.sample_rate
    logger.info("Ses suresi: %.1f saniye", duration)
    return duration
