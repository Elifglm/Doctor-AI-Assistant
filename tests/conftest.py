"""Pytest yapilandirmasi ve ortak fixture'lar."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

# Proje kokunu path'e ekle
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import AppSettings
from src.gpu_manager import GPUManager


@pytest.fixture
def app_settings() -> AppSettings:
    """Test icin varsayilan ayarlar."""
    settings = AppSettings()
    settings.output.output_dir = tempfile.mkdtemp(prefix="asr_test_")
    return settings


@pytest.fixture
def gpu_manager() -> GPUManager:
    """Test icin GPU yoneticisi."""
    return GPUManager()


@pytest.fixture
def sample_audio_array() -> np.ndarray:
    """16kHz mono test ses verisi (1 saniye sinuzoid)."""
    sr = 16000
    duration = 1.0
    t = np.linspace(0, duration, int(sr * duration), dtype=np.float32)
    audio = 0.5 * np.sin(2 * np.pi * 440 * t)  # 440Hz A notu
    return audio


@pytest.fixture
def sample_audio_path(tmp_path: Path, sample_audio_array: np.ndarray) -> str:
    """Gecici WAV dosyasi yolu."""
    import torch
    import torchaudio

    audio_path = tmp_path / "test_audio.wav"
    tensor = torch.from_numpy(sample_audio_array).unsqueeze(0)
    torchaudio.save(str(audio_path), tensor, 16000)
    return str(audio_path)


@pytest.fixture
def sample_segments() -> list[dict]:
    """Test icin ornek segment verisi."""
    return [
        {
            "start": 0.0,
            "end": 3.5,
            "text": "Hosgeldiniz, nasilsiniz bugun?",
            "speaker": "SPEAKER_00",
            "speaker_label": "Doktor",
            "words": [
                {"word": "Hosgeldiniz,", "start": 0.0, "end": 0.8, "score": 0.95},
                {"word": "nasilsiniz", "start": 0.9, "end": 1.5, "score": 0.92},
                {"word": "bugun?", "start": 1.6, "end": 2.0, "score": 0.98},
            ],
        },
        {
            "start": 4.0,
            "end": 8.5,
            "text": "Son bir haftadir basim cok agriyor.",
            "speaker": "SPEAKER_01",
            "speaker_label": "Hasta",
            "words": [
                {"word": "Son", "start": 4.0, "end": 4.3, "score": 0.91},
                {"word": "bir", "start": 4.3, "end": 4.5, "score": 0.89},
                {"word": "haftadir", "start": 4.5, "end": 5.0, "score": 0.93},
                {"word": "basim", "start": 5.1, "end": 5.5, "score": 0.90},
                {"word": "cok", "start": 5.6, "end": 5.8, "score": 0.95},
                {"word": "agriyor.", "start": 5.9, "end": 6.5, "score": 0.88},
            ],
        },
    ]


@pytest.fixture
def sample_metadata() -> dict:
    """Test icin ornek metadata."""
    return {
        "audio_file": "test_audio.wav",
        "audio_duration_seconds": 10.0,
        "language": "tr",
        "num_speakers": 2,
        "models": {
            "whisper": "large-v3-turbo",
            "compute_type": "float16",
            "alignment": "wav2vec2-xls-r-300m-cv7-turkish",
            "diarization": "pyannote/speaker-diarization-3.1",
            "noise_suppression": "DeepFilterNet3",
        },
        "processing": {
            "noise_suppression": 2.5,
            "transcription": 5.0,
            "diarization": 3.0,
            "total": 10.5,
        },
    }
