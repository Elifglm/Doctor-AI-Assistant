"""Pydantic tabanli merkezi konfigurasyon."""

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AudioSettings(BaseModel):
    sample_rate: int = 16000
    deepfilter_sample_rate: int = 48000
    supported_formats: list[str] = [".wav", ".mp3", ".flac", ".m4a", ".ogg"]


class WhisperSettings(BaseModel):
    model_name: str = "large-v3-turbo"
    device: str = "cuda"
    compute_type: str = "float16"
    language: str = "tr"
    batch_size: int = 16
    vad_method: str = "silero"  # Windows uyumlulugu icin kritik


class DiarizationSettings(BaseModel):
    min_speakers: int = 2
    max_speakers: int = 4
    default_labels: dict[str, str] = {
        "SPEAKER_00": "Doktor",
        "SPEAKER_01": "Hasta",
    }


class DeepFilterSettings(BaseModel):
    enabled: bool = True


class OutputSettings(BaseModel):
    output_dir: str = "output"
    save_json: bool = True
    save_txt: bool = True


class AppSettings(BaseSettings):
    audio: AudioSettings = AudioSettings()
    whisper: WhisperSettings = WhisperSettings()
    diarization: DiarizationSettings = DiarizationSettings()
    deepfilter: DeepFilterSettings = DeepFilterSettings()
    output: OutputSettings = OutputSettings()
    hf_token: str = Field(default="", alias="HF_TOKEN")
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ASR_",
        populate_by_name=True,
    )
