"""Anthropic Claude API client -- async interface for text generation.

Supports prompt caching: when a `system` prompt is supplied, it's wrapped as a
structured block with `cache_control: ephemeral` so the static instructional
prefix can be served from cache on repeat calls. Haiku 4.5 minimum cacheable
prefix is 4096 tokens; below that the API silently won't cache.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

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

    @staticmethod
    def _wrap_system_for_cache(system: str) -> list[dict[str, Any]]:
        return [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    @staticmethod
    def _log_cache_usage(usage: dict[str, Any]) -> None:
        cc = usage.get("cache_creation_input_tokens", 0) or 0
        cr = usage.get("cache_read_input_tokens", 0) or 0
        if cc or cr:
            logger.info(
                "anthropic cache usage: creation=%d read=%d input=%d",
                cc, cr, usage.get("input_tokens", 0) or 0,
            )

    async def generate(self, prompt: str, system: str = "", format: dict | str | None = None) -> str:
        # `format` accepted for cross-provider parity; Anthropic enforces schema via
        # the system prompt itself (no native structured-output param yet).
        del format
        if self._client is None:
            raise RuntimeError("AnthropicLLMService not initialized.")

        body: dict = {
            "model": self._model_name,
            "max_tokens": settings.llm.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        # `temperature` is deprecated/rejected by Opus 4.7+; pass it only for
        # older Claude families that still accept it (Haiku 4.5, Sonnet 4.x,
        # Opus 4.6 and earlier).
        if self._supports_temperature():
            body["temperature"] = settings.llm.temperature
        if system:
            body["system"] = self._wrap_system_for_cache(system)

        # Retry on transient API issues. 529 = Anthropic overloaded, 502/503/504 =
        # gateway/server errors, 429 = rate limit. Exponential backoff.
        import asyncio as _asyncio
        max_retries = 5
        for attempt in range(max_retries):
            try:
                resp = await self._client.post("/messages", json=body)
                if resp.status_code in (429, 502, 503, 504, 529) and attempt < max_retries - 1:
                    wait = min(2 ** attempt, 30)
                    logger.warning(
                        "Anthropic %d on attempt %d/%d; retrying in %ds",
                        resp.status_code, attempt + 1, max_retries, wait,
                    )
                    await _asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                self._log_cache_usage(data.get("usage", {}))
                content_blocks = data.get("content", [])
                return "".join(
                    block.get("text", "") for block in content_blocks if block.get("type") == "text"
                )
            except httpx.RequestError as e:
                # Network-level errors — also worth retrying
                if attempt < max_retries - 1:
                    wait = min(2 ** attempt, 30)
                    logger.warning("Anthropic network error: %s; retrying in %ds", e, wait)
                    await _asyncio.sleep(wait)
                    continue
                logger.exception("Anthropic generation failed (network exhausted)")
                raise
            except Exception:
                logger.exception("Anthropic generation failed")
                raise
        raise RuntimeError("Anthropic generate exhausted retries")

    def _supports_temperature(self) -> bool:
        """Whether the current model accepts the `temperature` parameter.

        Opus 4.7+ deprecated it (API returns 400 if sent). Default to True
        for backwards compatibility with Haiku / Sonnet / older Opus.
        """
        name = (self._model_name or "").lower()
        if name.startswith("claude-opus-4-7"):
            return False
        return True

    async def generate_stream(
        self, prompt: str, system: str = ""
    ) -> AsyncIterator[str]:
        if self._client is None:
            raise RuntimeError("AnthropicLLMService not initialized.")

        import json

        body: dict = {
            "model": self._model_name,
            "max_tokens": settings.llm.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }
        if self._supports_temperature():
            body["temperature"] = settings.llm.temperature
        if system:
            body["system"] = self._wrap_system_for_cache(system)

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
                    chunk_type = chunk.get("type")
                    if chunk_type == "content_block_delta":
                        text = chunk.get("delta", {}).get("text", "")
                        if text:
                            yield text
                    elif chunk_type == "message_delta":
                        usage = chunk.get("usage")
                        if usage:
                            self._log_cache_usage(usage)
        except Exception:
            logger.exception("Anthropic streaming failed")
            raise
