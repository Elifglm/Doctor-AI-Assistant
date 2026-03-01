"""Ollama LLM client -- async HTTP interface for text generation."""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx

from config.settings import AppSettings

logger = logging.getLogger(__name__)

settings = AppSettings()


class LLMService:
    """Async client for the Ollama REST API."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.base_url = base_url or settings.llm.ollama_url
        self.model = model or settings.llm.model_name
        self._client: httpx.AsyncClient | None = None

    async def initialize(self) -> None:
        """Create the underlying HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(settings.llm.timeout_seconds, connect=10.0),
        )
        logger.info("LLMService initialized (url=%s, model=%s)", self.base_url, self.model)

    async def shutdown(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("LLMService not initialized. Call initialize() first.")
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
            return any(self.model in name for name in model_names)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    async def generate(self, prompt: str, system: str = "") -> str:
        """Non-streaming generation -- returns the full response text."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {
                "temperature": settings.llm.temperature,
                "top_p": settings.llm.top_p,
                "num_predict": settings.llm.max_tokens,
            },
        }
        resp = await self.client.post("/api/generate", json=payload)
        resp.raise_for_status()
        return resp.json().get("response", "")

    async def generate_stream(
        self, prompt: str, system: str = ""
    ) -> AsyncIterator[str]:
        """Streaming generation -- yields token strings as they arrive."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": True,
            "options": {
                "temperature": settings.llm.temperature,
                "top_p": settings.llm.top_p,
                "num_predict": settings.llm.max_tokens,
            },
        }
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
