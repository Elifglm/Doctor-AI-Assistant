"""Factory for creating the appropriate LLM service based on configuration."""

from __future__ import annotations

import logging

from config.settings import AppSettings
from apps.backend.src.services.llm_service import OllamaLLMService
from apps.backend.src.services.gemini_service import GeminiLLMService

logger = logging.getLogger(__name__)


def create_llm_service(
    settings: AppSettings | None = None,
) -> OllamaLLMService | GeminiLLMService:
    """Create the LLM service based on settings.llm.mode.

    Returns an OllamaLLMService for 'local' mode or
    GeminiLLMService for 'api' mode.
    """
    if settings is None:
        settings = AppSettings()

    mode = settings.llm.mode

    if mode == "api":
        if not settings.llm.gemini_api_key:
            logger.warning(
                "Gemini API modu secili ama API key tanimlanmamis, local moda donuluyor"
            )
            return OllamaLLMService()

        logger.info("LLM modu: API (Gemini %s)", settings.llm.gemini_model)
        return GeminiLLMService(
            api_key=settings.llm.gemini_api_key,
            model=settings.llm.gemini_model,
        )

    logger.info("LLM modu: Local (Ollama %s)", settings.llm.model_name)
    return OllamaLLMService(
        base_url=settings.llm.ollama_url,
        model=settings.llm.model_name,
    )
