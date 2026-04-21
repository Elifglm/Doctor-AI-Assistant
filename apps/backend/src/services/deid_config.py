"""De-identification configuration settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class DeIDSettings(BaseSettings):
    enabled: bool = True
    fuzzy_threshold: float = 0.85
    use_ner_layer: bool = True
    ner_model_name: str = "knowledgator/gliner-pii-base-v1.0"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="DEID_",
        populate_by_name=True,
        extra="ignore",
    )
