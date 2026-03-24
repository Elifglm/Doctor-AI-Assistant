"""Factory for creating the appropriate LLM service based on configuration."""

from __future__ import annotations

import logging

from config.settings import AppSettings
from apps.backend.src.services.llm_service import OllamaLLMService
from apps.backend.src.services.gemini_service import GeminiLLMService
from apps.backend.src.services.groq_service import GroqLLMService
from apps.backend.src.services.cerebras_service import CerebrasLLMService
from apps.backend.src.services.anthropic_service import AnthropicLLMService

logger = logging.getLogger(__name__)


def create_llm_service(
    settings: AppSettings | None = None,
) -> OllamaLLMService | GeminiLLMService | GroqLLMService | CerebrasLLMService | AnthropicLLMService:
    """Create the LLM service based on settings.llm.mode.

    Returns OllamaLLMService for 'local', GeminiLLMService for 'api',
    or GroqLLMService for 'groq' mode.
    """
    if settings is None:
        settings = AppSettings()

    mode = settings.llm.mode

    if mode == "anthropic":
        if not settings.llm.anthropic_api_key:
            logger.warning("Anthropic modu secili ama API key tanimlanmamis, local moda donuluyor")
            return OllamaLLMService()
        logger.info("LLM modu: Anthropic (%s)", settings.llm.anthropic_model)
        return AnthropicLLMService(
            api_key=settings.llm.anthropic_api_key,
            model=settings.llm.anthropic_model,
        )

    if mode == "cerebras":
        if not settings.llm.cerebras_api_key:
            logger.warning("Cerebras modu secili ama API key tanimlanmamis, local moda donuluyor")
            return OllamaLLMService()
        logger.info("LLM modu: Cerebras (%s)", settings.llm.cerebras_model)
        return CerebrasLLMService(
            api_key=settings.llm.cerebras_api_key,
            model=settings.llm.cerebras_model,
        )

    if mode == "groq":
        if not settings.llm.groq_api_key:
            logger.warning(
                "Groq modu secili ama API key tanimlanmamis, local moda donuluyor"
            )
            return OllamaLLMService()

        logger.info("LLM modu: Groq (%s)", settings.llm.groq_model)
        return GroqLLMService(
            api_key=settings.llm.groq_api_key,
            model=settings.llm.groq_model,
        )

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
