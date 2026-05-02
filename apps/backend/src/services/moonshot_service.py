"""Moonshot (Kimi) API client -- async interface for direct Moonshot API.

OpenAI-compatible API at https://api.moonshot.ai/v1.
Default model: kimi-k2-0905-preview (Kimi K2, Turkish-friendly).
"""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx

from config.settings import AppSettings

logger = logging.getLogger(__name__)

settings = AppSettings()


class MoonshotLLMService:
    """Async client for the Moonshot API (OpenAI-compatible)."""

    MOONSHOT_BASE_URL = "https://api.moonshot.ai/v1"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._api_key = api_key or settings.llm.moonshot_api_key
        self._model_name = model or settings.llm.moonshot_model
        self._client: httpx.AsyncClient | None = None

    @property
    def provider_name(self) -> str:
        return "moonshot"

    @property
    def model_name(self) -> str:
        return self._model_name

    async def initialize(self) -> None:
        if not self._api_key:
            raise ValueError(
                "Moonshot API key tanimlanmamis. "
                ".env dosyasina ASR_LLM__MOONSHOT_API_KEY ekleyin."
            )
        self._client = httpx.AsyncClient(
            base_url=self.MOONSHOT_BASE_URL,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(180.0),
        )
        logger.info("MoonshotLLMService initialized (model=%s)", self._model_name)

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def check_health(self) -> bool:
        if self._client is None:
            return False
        try:
            resp = await self._client.get("/models")
            return resp.status_code == 200
        except Exception:
            return False

    async def generate(self, prompt: str, system: str = "") -> str:
        if self._client is None:
            raise RuntimeError("MoonshotLLMService not initialized.")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            resp = await self._client.post(
                "/chat/completions",
                json={
                    "model": self._model_name,
                    "messages": messages,
                    "temperature": settings.llm.temperature,
                    "top_p": settings.llm.top_p,
                    "max_tokens": settings.llm.max_tokens,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception:
            logger.exception("Moonshot generation failed")
            raise

    async def generate_stream(
        self, prompt: str, system: str = ""
    ) -> AsyncIterator[str]:
        if self._client is None:
            raise RuntimeError("MoonshotLLMService not initialized.")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            async with self._client.stream(
                "POST",
                "/chat/completions",
                json={
                    "model": self._model_name,
                    "messages": messages,
                    "temperature": settings.llm.temperature,
                    "top_p": settings.llm.top_p,
                    "max_tokens": settings.llm.max_tokens,
                    "stream": True,
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload == "[DONE]":
                        break
                    chunk = json.loads(payload)
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
        except Exception:
            logger.exception("Moonshot streaming failed")
            raise
