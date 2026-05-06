"""Ollama LLM client -- async HTTP interface for text generation with fallback."""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx

from config.settings import AppSettings

logger = logging.getLogger(__name__)

settings = AppSettings()


class OllamaLLMService:
    """Async client for the Ollama REST API with model fallback support."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.base_url = base_url or settings.llm.ollama_url
        self._primary_model = model or settings.llm.model_name
        self._fallback_model = settings.llm.fallback_model
        self._fallback_enabled = settings.llm.ollama_fallback_enabled
        self._active_model = self._primary_model
        self._client: httpx.AsyncClient | None = None

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._active_model

    async def initialize(self) -> None:
        """Create the underlying HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(settings.llm.timeout_seconds, connect=10.0),
        )
        logger.info(
            "OllamaLLMService initialized (url=%s, model=%s, fallback=%s)",
            self.base_url,
            self._primary_model,
            self._fallback_model if self._fallback_enabled else "disabled",
        )

    async def shutdown(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("OllamaLLMService not initialized. Call initialize() first.")
        return self._client

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def check_health(self) -> bool:
        """Return True if Ollama is reachable."""
        try:
            resp = await self.client.get("/api/tags")
            return resp.status_code == 200
        except Exception:
            return False

    async def is_model_loaded(self) -> bool:
        """Return True if the configured model is available in Ollama."""
        try:
            resp = await self.client.get("/api/tags")
            if resp.status_code != 200:
                return False
            data = resp.json()
            model_names = [m.get("name", "") for m in data.get("models", [])]
            return any(self._active_model in name for name in model_names)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def _build_payload(
        self,
        model: str,
        prompt: str,
        system: str,
        stream: bool,
        format: dict | str | None = None,
    ) -> dict:
        payload: dict = {
            "model": model,
            "prompt": prompt,
            "system": system,
            "stream": stream,
            "options": {
                "temperature": settings.llm.temperature,
                "top_p": settings.llm.top_p,
                "num_predict": settings.llm.max_tokens,
            },
        }
        # Ollama 0.5+ structured output — schema'yi enforce eder. Local model
        # (Gemma 4 vs.) instruction-following Claude'tan zayifsa schema sapmasini
        # bu engeller. dict (JSON Schema) veya "json" string olabilir.
        if format is not None:
            payload["format"] = format
        return payload

    async def _generate_with_model(
        self,
        model: str,
        prompt: str,
        system: str,
        format: dict | str | None = None,
    ) -> str:
        """Generate with a specific model (no fallback)."""
        payload = self._build_payload(model, prompt, system, stream=False, format=format)
        resp = await self.client.post("/api/generate", json=payload)
        resp.raise_for_status()
        return resp.json().get("response", "")

    async def generate(
        self,
        prompt: str,
        system: str = "",
        format: dict | str | None = None,
    ) -> str:
        """Non-streaming generation with automatic fallback to secondary model."""
        try:
            result = await self._generate_with_model(self._primary_model, prompt, system, format)
            self._active_model = self._primary_model
            return result
        except Exception as primary_err:
            if not self._fallback_enabled or self._fallback_model == self._primary_model:
                raise

            logger.warning(
                "Primary model %s failed (%s), falling back to %s",
                self._primary_model,
                primary_err,
                self._fallback_model,
            )
            try:
                result = await self._generate_with_model(self._fallback_model, prompt, system, format)
                self._active_model = self._fallback_model
                return result
            except Exception:
                logger.exception(
                    "Fallback model %s also failed", self._fallback_model
                )
                raise

    async def generate_stream(
        self, prompt: str, system: str = ""
    ) -> AsyncIterator[str]:
        """Streaming generation -- yields token strings as they arrive."""
        payload = self._build_payload(self._active_model, prompt, system, stream=True)
        async with self.client.stream("POST", "/api/generate", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if data.get("done"):
                    break
                token = data.get("response", "")
                if token:
                    yield token
