"""ASR Pipeline birim ve entegrasyon testleri."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Proje kokunu path'e ekle
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import AppSettings, DiarizationSettings
from src.audio_utils import get_audio_duration, load_and_validate
from src.exceptions import (
    ASRPipelineError,
    AudioLoadError,
    ConfigurationError,
    DiarizationError,
    NoiseSuppressionError,
    TranscriptionError,
)
from src.gpu_manager import GPUManager
from src.output_formatter import OutputFormatter


class TestAudioUtils:
    """Ses yardimci fonksiyonlari testleri."""

    def test_load_and_validate_valid_file(self, sample_audio_path: str):
        """Gecerli dosya basariyla dogrulanir."""
        path = load_and_validate(sample_audio_path)
        assert path.exists()
        assert path.suffix == ".wav"

    def test_load_and_validate_missing_file(self):
        """Olmayan dosya AudioLoadError firlatir."""
        with pytest.raises(AudioLoadError, match="bulunamadi"):
            load_and_validate("olmayan_dosya.wav")

    def test_load_and_validate_invalid_format(self, tmp_path: Path):
        """Desteklenmeyen format AudioLoadError firlatir."""
        invalid_file = tmp_path / "test.xyz"
        invalid_file.write_text("dummy")
        with pytest.raises(AudioLoadError, match="Desteklenmeyen format"):
            load_and_validate(str(invalid_file))

    def test_get_audio_duration(self, sample_audio_path: str):
        """Ses suresi dogru hesaplanir."""
        duration = get_audio_duration(sample_audio_path)
        assert 0.9 <= duration <= 1.1  # ~1 saniye


class TestGPUManager:
    """GPU yoneticisi testleri."""

    def test_log_vram(self, gpu_manager: GPUManager):
        """VRAM bilgisi basariyla dondurulur."""
        info = gpu_manager.log_vram("test")
        assert "allocated_gb" in info
        assert "reserved_gb" in info
        assert "total_gb" in info

    def test_register_and_unload(self, gpu_manager: GPUManager):
        """Model kayit ve silme basarili."""
        mock_model = MagicMock()
        gpu_manager.register_model("test_model", mock_model)
        assert "test_model" in gpu_manager._registry

        gpu_manager.unload_model("test_model")
        assert "test_model" not in gpu_manager._registry

    def test_unload_nonexistent_model(self, gpu_manager: GPUManager):
        """Olmayan model silme hataya yol acmaz."""
        gpu_manager.unload_model("nonexistent")

    def test_unload_all(self, gpu_manager: GPUManager):
        """Tum modeller bosaltilir."""
        gpu_manager.register_model("model1", MagicMock())
        gpu_manager.register_model("model2", MagicMock())
        gpu_manager.unload_all()
        assert len(gpu_manager._registry) == 0

    def test_stage_context(self, gpu_manager: GPUManager):
        """stage_context basarili sekilde calisir."""
        with gpu_manager.stage_context("test_stage"):
            pass  # Hata olmadan tamamlanmali

    def test_stage_context_error_cleanup(self, gpu_manager: GPUManager):
        """stage_context hata durumunda temizlik yapar."""
        gpu_manager.register_model("temp_model", MagicMock())

        with pytest.raises(ValueError):
            with gpu_manager.stage_context("error_stage"):
                raise ValueError("Test hatasi")

        # Hata durumunda tum modeller temizlenir
        assert len(gpu_manager._registry) == 0


class TestNoiseSuppressor:
    """Gurultu bastirma testleri."""

    def test_process_without_load_raises_error(self):
        """Model yuklemeden islem yapma hatasi."""
        from config.settings import DeepFilterSettings
        from src.noise_suppression import NoiseSuppressor

        suppressor = NoiseSuppressor(DeepFilterSettings(), GPUManager())
        with pytest.raises(NoiseSuppressionError, match="yuklenmemis"):
            suppressor.process("dummy.wav")

    def test_unload_cleans_state(self):
        """Model bosaltma durumu temizler."""
        from config.settings import DeepFilterSettings
        from src.noise_suppression import NoiseSuppressor

        suppressor = NoiseSuppressor(DeepFilterSettings(), GPUManager())
        suppressor.model = MagicMock()
        suppressor.df_state = MagicMock()

        suppressor.unload_model()
        assert suppressor.model is None
        assert suppressor.df_state is None


class TestTranscriber:
    """Transkripsiyon testleri."""

    def test_transcribe_without_load_raises_error(self):
        """Model yuklemeden transkripsiyon hatasi."""
        from config.settings import WhisperSettings
        from src.transcriber import Transcriber

        transcriber = Transcriber(WhisperSettings(), "", GPUManager())
        with pytest.raises(TranscriptionError, match="yuklenmemis"):
            transcriber.transcribe(np.zeros(16000, dtype=np.float32))

    def test_align_without_load_raises_error(self):
        """Hizalama modeli yuklemeden hizalama hatasi."""
        from config.settings import WhisperSettings
        from src.transcriber import Transcriber

        transcriber = Transcriber(WhisperSettings(), "", GPUManager())
        with pytest.raises(TranscriptionError, match="yuklenmemis"):
            transcriber.align({"segments": []}, np.zeros(16000, dtype=np.float32))

    def test_unload_all_cleans_state(self):
        """Tum modelleri bosaltma durumu temizler."""
        from config.settings import WhisperSettings
        from src.transcriber import Transcriber

        transcriber = Transcriber(WhisperSettings(), "", GPUManager())
        transcriber.whisper_model = MagicMock()
        transcriber.align_model = MagicMock()
        transcriber.align_metadata = MagicMock()

        transcriber.unload_all()
        assert transcriber.whisper_model is None
        assert transcriber.align_model is None
        assert transcriber.align_metadata is None


class TestDiarizer:
    """Konusmaci ayristirma testleri."""

    def test_missing_token_raises_error(self):
        """Eksik HF token ConfigurationError firlatir."""
        from src.diarizer import Diarizer

        diarizer = Diarizer(DiarizationSettings(), "", GPUManager())
        with pytest.raises(ConfigurationError, match="HuggingFace token"):
            diarizer.load_model()

    def test_diarize_without_load_raises_error(self):
        """Pipeline yuklenmeden diarize hatasi."""
        from src.diarizer import Diarizer

        diarizer = Diarizer(DiarizationSettings(), "fake_token", GPUManager())
        with pytest.raises(DiarizationError, match="yuklenmemis"):
            diarizer.diarize("dummy.wav")

    def test_speaker_label_assignment(self):
        """Konusmaci etiketleri dogru atanir."""
        from src.diarizer import Diarizer

        diarizer = Diarizer(DiarizationSettings(), "fake_token", GPUManager())

        mock_diarize = MagicMock()
        mock_aligned = {
            "segments": [
                {"speaker": "SPEAKER_00", "text": "Merhaba"},
                {"speaker": "SPEAKER_01", "text": "Merhaba doktor"},
            ]
        }

        with patch("whisperx.assign_word_speakers", return_value=mock_aligned):
            result = diarizer.assign_speakers(mock_diarize, mock_aligned)

        assert result["segments"][0]["speaker_label"] == "Doktor"
        assert result["segments"][1]["speaker_label"] == "Hasta"

    def test_unload_cleans_state(self):
        """Pipeline bosaltma durumu temizler."""
        from src.diarizer import Diarizer

        diarizer = Diarizer(DiarizationSettings(), "fake_token", GPUManager())
        diarizer.pipeline = MagicMock()

        diarizer.unload_model()
        assert diarizer.pipeline is None


class TestOutputFormatter:
    """Cikti formatlama testleri."""

    def test_format_result_structure(
        self, sample_segments: list[dict], sample_metadata: dict
    ):
        """JSON cikti yapisi dogru."""
        from config.settings import OutputSettings

        formatter = OutputFormatter(OutputSettings())
        result = formatter.format_result(sample_segments, sample_metadata)

        assert result["version"] == "1.0.0"
        assert "metadata" in result
        assert "segments" in result
        assert "full_text" in result
        assert len(result["segments"]) == 2

    def test_segment_fields(
        self, sample_segments: list[dict], sample_metadata: dict
    ):
        """Her segment gerekli alanlara sahip."""
        from config.settings import OutputSettings

        formatter = OutputFormatter(OutputSettings())
        result = formatter.format_result(sample_segments, sample_metadata)

        seg = result["segments"][0]
        assert "id" in seg
        assert "start" in seg
        assert "end" in seg
        assert "text" in seg
        assert "speaker" in seg
        assert "speaker_label" in seg
        assert "words" in seg

    def test_word_fields(
        self, sample_segments: list[dict], sample_metadata: dict
    ):
        """Her kelime gerekli alanlara sahip."""
        from config.settings import OutputSettings

        formatter = OutputFormatter(OutputSettings())
        result = formatter.format_result(sample_segments, sample_metadata)

        word = result["segments"][0]["words"][0]
        assert "word" in word
        assert "start" in word
        assert "end" in word
        assert "score" in word

    def test_full_text_contains_speakers(
        self, sample_segments: list[dict], sample_metadata: dict
    ):
        """Tam metin konusmaci etiketleri icerir."""
        from config.settings import OutputSettings

        formatter = OutputFormatter(OutputSettings())
        result = formatter.format_result(sample_segments, sample_metadata)

        assert "Doktor:" in result["full_text"]
        assert "Hasta:" in result["full_text"]

    def test_save_json(
        self, tmp_path: Path, sample_segments: list[dict], sample_metadata: dict
    ):
        """JSON dosyasi basariyla kaydedilir."""
        from config.settings import OutputSettings

        formatter = OutputFormatter(OutputSettings())
        result = formatter.format_result(sample_segments, sample_metadata)

        json_path = str(tmp_path / "test_output.json")
        formatter.save_json(result, json_path)

        assert Path(json_path).exists()
        with open(json_path, encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["version"] == "1.0.0"

    def test_save_txt(
        self, tmp_path: Path, sample_segments: list[dict], sample_metadata: dict
    ):
        """TXT dosyasi basariyla kaydedilir."""
        from config.settings import OutputSettings

        formatter = OutputFormatter(OutputSettings())
        result = formatter.format_result(sample_segments, sample_metadata)

        txt_path = str(tmp_path / "test_output.txt")
        formatter.save_txt(result, txt_path)

        assert Path(txt_path).exists()
        content = Path(txt_path).read_text(encoding="utf-8")
        assert "Doktor:" in content
        assert "Hasta:" in content

    def test_format_timestamp(self):
        """Zaman damgasi formatlama dogru."""
        from config.settings import OutputSettings

        formatter = OutputFormatter(OutputSettings())
        assert formatter._format_timestamp(0.0) == "00:00:00"
        assert formatter._format_timestamp(61.0) == "00:01:01"
        assert formatter._format_timestamp(3661.0) == "01:01:01"


class TestPipeline:
    """Pipeline entegrasyon testleri (mock'lu)."""

    def test_pipeline_initialization(self, app_settings: AppSettings):
        """Pipeline basariyla baslatilir."""
        from src.pipeline import ASRPipeline

        pipeline = ASRPipeline(app_settings)
        assert pipeline.settings is not None
        assert pipeline.gpu is not None
        assert pipeline.noise_suppressor is not None
        assert pipeline.transcriber is not None
        assert pipeline.diarizer is not None
        assert pipeline.formatter is not None

    def test_pipeline_default_settings(self):
        """Varsayilan ayarlarla pipeline olusturulabilir."""
        from src.pipeline import ASRPipeline

        pipeline = ASRPipeline()
        assert pipeline.settings.whisper.model_name == "large-v3-turbo"
        assert pipeline.settings.whisper.language == "tr"
        assert pipeline.settings.whisper.compute_type == "float16"


class TestSettings:
    """Konfigurasyon testleri."""

    def test_settings_loads_hf_token(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """HF_TOKEN .env'den dogru okunur (ASR_ prefix'siz)."""
        env_file = tmp_path / ".env"
        env_file.write_text("HF_TOKEN=hf_test_token_123\n")
        monkeypatch.chdir(tmp_path)
        settings = AppSettings(_env_file=str(env_file))
        assert settings.hf_token == "hf_test_token_123"

    def test_settings_loads_asr_hf_token(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """ASR_HF_TOKEN .env'den de okunabilir."""
        env_file = tmp_path / ".env"
        env_file.write_text("ASR_HF_TOKEN=hf_prefixed_token\n")
        monkeypatch.chdir(tmp_path)
        settings = AppSettings(_env_file=str(env_file))
        assert settings.hf_token == "hf_prefixed_token"


class TestExceptions:
    """Ozel hata siniflari testleri."""

    def test_exception_hierarchy(self):
        """Tum hatalar ASRPipelineError'dan turetilmis."""
        assert issubclass(AudioLoadError, ASRPipelineError)
        assert issubclass(NoiseSuppressionError, ASRPipelineError)
        assert issubclass(TranscriptionError, ASRPipelineError)
        assert issubclass(DiarizationError, ASRPipelineError)
        assert issubclass(ConfigurationError, ASRPipelineError)

    def test_exception_messages(self):
        """Hata mesajlari dogru iletilir."""
        error = AudioLoadError("Test mesaji")
        assert str(error) == "Test mesaji"

        error = ConfigurationError("Eksik token")
        assert "Eksik token" in str(error)
