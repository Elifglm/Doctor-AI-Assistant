"""Google Gemini API client -- async interface for text generation."""

from __future__ import annotations

import logging
from typing import AsyncIterator

from config.settings import AppSettings

logger = logging.getLogger(__name__)

settings = AppSettings()


class GeminiLLMService:
    """Async client for the Google Gemini API using the new google.genai SDK."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._api_key = api_key or settings.llm.gemini_api_key
        self._model_name = model or settings.llm.gemini_model
        self._client = None

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model_name

    async def initialize(self) -> None:
        """Configure the Gemini API client."""
        if not self._api_key:
            raise ValueError(
                "Gemini API key tanimlanmamis. "
                ".env dosyasina ASR_LLM__GEMINI_API_KEY ekleyin."
            )

        from google import genai  # type: ignore[import-untyped]

        self._client = genai.Client(api_key=self._api_key)
        logger.info(
            "GeminiLLMService initialized (model=%s)", self._model_name
        )

    async def shutdown(self) -> None:
        """Cleanup (Gemini SDK doesn't require explicit shutdown)."""
        self._client = None

    async def check_health(self) -> bool:
        """Return True if Gemini API is reachable."""
        if self._client is None:
            return False
        try:
            # List models as a lightweight health check
            list(self._client.models.list())
            return True
        except Exception:
            return False

    async def generate(self, prompt: str, system: str = "") -> str:
        """Non-streaming generation -- returns the full response text."""
        if self._client is None:
            raise RuntimeError("GeminiLLMService not initialized. Call initialize() first.")

        full_prompt = f"{system}\n\n{prompt}" if system else prompt

        try:
            response = self._client.models.generate_content(
                model=self._model_name,
                contents=full_prompt,
                config={
                    "temperature": settings.llm.temperature,
                    "top_p": settings.llm.top_p,
                    "max_output_tokens": settings.llm.max_tokens,
                },
            )
            return response.text
        except Exception:
            logger.exception("Gemini generation failed")
            raise

    async def generate_stream(
        self, prompt: str, system: str = ""
    ) -> AsyncIterator[str]:
        """Streaming generation -- yields token strings as they arrive."""
        if self._client is None:
            raise RuntimeError("GeminiLLMService not initialized. Call initialize() first.")

        full_prompt = f"{system}\n\n{prompt}" if system else prompt

        try:
            response = self._client.models.generate_content_stream(
                model=self._model_name,
                contents=full_prompt,
                config={
                    "temperature": settings.llm.temperature,
                    "top_p": settings.llm.top_p,
                    "max_output_tokens": settings.llm.max_tokens,
                },
            )
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception:
            logger.exception("Gemini streaming failed")
            raise
