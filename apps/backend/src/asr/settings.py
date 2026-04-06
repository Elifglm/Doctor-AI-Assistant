"""Batch ASR pipeline yapilandirmasi (Pydantic v2 settings)."""

from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BatchTranscriptionSettings(BaseModel):
    """Batch transkripsiyon (faster-whisper sequential model.transcribe)."""

    model_name: str = "large-v3-turbo"
    compute_type: str = "float16"
    device: str = "cuda"
    language: str = "tr"
    beam_size: int = 5
    batch_size: int = 16  # sequential modda kullanilmaz ama saklanir
    temperature: float = 0.0
    word_timestamps: bool = True
    vad_filter: bool = True
    condition_on_previous_text: bool = False
    hallucination_silence_threshold: float = 2.0
    hotwords: str = (
        "kol kolunda kolumda kolunuzda bacak bacağında göğüs göğsünde "
        "baş başında bel belinde omuz omzunda diz dizinde kalça dirsek bilek "
        "ayak boyun karın karnında ağrı ağrısı ağrınız sızı şişlik "
        "tansiyon nabız ateş solunum bulantı kusma ishal kabızlık "
        "halsizlik yorgunluk nefes darlığı öksürük balgam "
        "diyabet hipertansiyon astım KOAH tiroid epilepsi "
        "hemogram biyokimya sedimentasyon CRP kreatinin üre "
        "ekokardiyografi elektrokardiyografi EKG ultrasonografi tomografi "
        "miyokard enfarktüsü pnömoni bronşit gastrit kolesistit "
        "parasetamol amoksisilin metformin atorvastatin ramipril "
        "muayene şikayet öykü anamnez inspeksiyon palpasyon perküsyon"
    )


class DiarizationSettings(BaseModel):
    """Konusmaci ayristirma (pyannote speaker-diarization-3.1)."""

    model_name: str = "pyannote/speaker-diarization-3.1"
    num_speakers: int = 2
    min_speakers: int = 2
    max_speakers: int = 2
    default_labels: dict[str, str] = Field(
        default_factory=lambda: {
            "SPEAKER_00": "Doktor",
            "SPEAKER_01": "Hasta",
        }
    )


class GPUSettings(BaseModel):
    """GPU bellek yonetimi."""

    target_gpu: str = "cuda:0"
    max_vram_gb: float = 16.0


class AudioSettings(BaseModel):
    """Ses isleme."""

    sample_rate: int = 16000
    max_recording_duration_s: float = 3600.0
    supported_formats: list[str] = Field(
        default_factory=lambda: [".wav", ".mp3", ".flac", ".m4a", ".ogg"]
    )


class ASRSettings(BaseSettings):
    """Ana ASR yapilandirmasi."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ASR_V2_",
        env_nested_delimiter="__",
        populate_by_name=True,
        extra="ignore",
    )

    transcription: BatchTranscriptionSettings = Field(
        default_factory=BatchTranscriptionSettings
    )
    diarization: DiarizationSettings = Field(default_factory=DiarizationSettings)
    gpu: GPUSettings = Field(default_factory=GPUSettings)
    audio: AudioSettings = Field(default_factory=AudioSettings)

    hf_token: str = Field(default="", alias="HF_TOKEN")

    # CPU fallback
    cpu_fallback: bool = True
    cpu_compute_type: str = "int8"
