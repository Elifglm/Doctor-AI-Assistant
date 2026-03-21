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
    fallback_device: str = "cpu"
    fallback_compute_type: str = "int8"
    auto_fallback: bool = True


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


class LLMSettings(BaseModel):
    mode: str = "local"  # "local" (Ollama) | "api" (Gemini)
    ollama_url: str = "http://localhost:11434"
    model_name: str = "qwen3:14b"
    fallback_model: str = "qwen3:8b"
    ollama_fallback_enabled: bool = True
    temperature: float = 0.3
    top_p: float = 0.9
    max_tokens: int = 2048
    timeout_seconds: int = 300
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"


class NERSettings(BaseModel):
    model_name: str = "urchade/gliner_multi-v2.1"
    threshold: float = 0.5
    device: str = "cpu"


class RAGSettings(BaseModel):
    persist_dir: str = "data/rag/chroma_db"
    collection_name: str = "medical_knowledge"
    n_results: int = 50


class AppSettings(BaseSettings):
    audio: AudioSettings = AudioSettings()
    whisper: WhisperSettings = WhisperSettings()
    diarization: DiarizationSettings = DiarizationSettings()
    deepfilter: DeepFilterSettings = DeepFilterSettings()
    output: OutputSettings = OutputSettings()
    llm: LLMSettings = LLMSettings()
    ner: NERSettings = NERSettings()
    rag: RAGSettings = RAGSettings()
    hf_token: str = Field(default="", alias="HF_TOKEN")
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ASR_",
        env_nested_delimiter="__",
        populate_by_name=True,
    )
