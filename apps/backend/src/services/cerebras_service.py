"""Cerebras API client -- OpenAI-compatible async interface for text generation."""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx

from config.settings import AppSettings

logger = logging.getLogger(__name__)

settings = AppSettings()


class CerebrasLLMService:
    """Async client for the Cerebras API (OpenAI-compatible)."""

    CEREBRAS_BASE_URL = "https://api.cerebras.ai/v1"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._api_key = api_key or settings.llm.cerebras_api_key
        self._model_name = model or settings.llm.cerebras_model
        self._client: httpx.AsyncClient | None = None

    @property
    def provider_name(self) -> str:
        return "cerebras"

    @property
    def model_name(self) -> str:
        return self._model_name

    async def initialize(self) -> None:
        if not self._api_key:
            raise ValueError(
                "Cerebras API key tanimlanmamis. "
                ".env dosyasina ASR_LLM__CEREBRAS_API_KEY ekleyin."
            )
        self._client = httpx.AsyncClient(
            base_url=self.CEREBRAS_BASE_URL,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(120.0),
        )
        logger.info("CerebrasLLMService initialized (model=%s)", self._model_name)

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

    async def generate(self, prompt: str, system: str = "", format: dict | str | None = None) -> str:
        del format  # accepted for parity; not used
        if self._client is None:
            raise RuntimeError("CerebrasLLMService not initialized.")

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
            logger.exception("Cerebras generation failed")
            raise

    async def generate_stream(
        self, prompt: str, system: str = ""
    ) -> AsyncIterator[str]:
        if self._client is None:
            raise RuntimeError("CerebrasLLMService not initialized.")

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
            logger.exception("Cerebras streaming failed")
            raise
