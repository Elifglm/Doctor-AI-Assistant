"""Anthropic Claude API client -- async interface for text generation."""

from __future__ import annotations

import logging
from typing import AsyncIterator

import httpx

from config.settings import AppSettings

logger = logging.getLogger(__name__)

settings = AppSettings()


class AnthropicLLMService:
    """Async client for the Anthropic Claude API."""

    ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._api_key = api_key or settings.llm.anthropic_api_key
        self._model_name = model or settings.llm.anthropic_model
        self._client: httpx.AsyncClient | None = None

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str:
        return self._model_name

    async def initialize(self) -> None:
        if not self._api_key:
            raise ValueError(
                "Anthropic API key tanimlanmamis. "
                ".env dosyasina ASR_LLM__ANTHROPIC_API_KEY ekleyin."
            )
        self._client = httpx.AsyncClient(
            base_url=self.ANTHROPIC_BASE_URL,
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            timeout=httpx.Timeout(120.0),
        )
        logger.info("AnthropicLLMService initialized (model=%s)", self._model_name)

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def check_health(self) -> bool:
        if self._client is None:
            return False
        try:
            resp = await self._client.post(
                "/messages",
                json={
                    "model": self._model_name,
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "Hi"}],
                },
            )
            return resp.status_code == 200
        except Exception:
            return False

    async def generate(self, prompt: str, system: str = "") -> str:
        if self._client is None:
            raise RuntimeError("AnthropicLLMService not initialized.")

        body: dict = {
            "model": self._model_name,
            "max_tokens": settings.llm.max_tokens,
            "temperature": settings.llm.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system

        try:
            resp = await self._client.post("/messages", json=body)
            resp.raise_for_status()
            data = resp.json()
            # Extract text from content blocks
            content_blocks = data.get("content", [])
            return "".join(
                block.get("text", "") for block in content_blocks if block.get("type") == "text"
            )
        except Exception:
            logger.exception("Anthropic generation failed")
            raise

    async def generate_stream(
        self, prompt: str, system: str = ""
    ) -> AsyncIterator[str]:
        if self._client is None:
            raise RuntimeError("AnthropicLLMService not initialized.")

        import json

        body: dict = {
            "model": self._model_name,
            "max_tokens": settings.llm.max_tokens,
            "temperature": settings.llm.temperature,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }
        if system:
            body["system"] = system

        try:
            async with self._client.stream("POST", "/messages", json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload == "[DONE]":
                        break
                    chunk = json.loads(payload)
                    if chunk.get("type") == "content_block_delta":
                        text = chunk.get("delta", {}).get("text", "")
                        if text:
                            yield text
        except Exception:
            logger.exception("Anthropic streaming failed")
            raise
