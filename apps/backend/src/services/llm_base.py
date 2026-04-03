"""Abstract LLM provider interface using Python Protocol."""

from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """All LLM services (Ollama, Gemini, etc.) must implement this interface."""

    async def initialize(self) -> None: ...

    async def shutdown(self) -> None: ...

    async def check_health(self) -> bool: ...

    async def generate(self, prompt: str, system: str = "") -> str: ...

    async def generate_stream(
        self, prompt: str, system: str = ""
    ) -> AsyncIterator[str]: ...

    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...
