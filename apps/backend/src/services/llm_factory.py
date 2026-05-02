"""Factory for creating the appropriate LLM service based on configuration."""

from __future__ import annotations

import logging

from config.settings import AppSettings
from apps.backend.src.services.llm_service import OllamaLLMService
from apps.backend.src.services.gemini_service import GeminiLLMService
from apps.backend.src.services.groq_service import GroqLLMService
from apps.backend.src.services.cerebras_service import CerebrasLLMService
from apps.backend.src.services.anthropic_service import AnthropicLLMService
from apps.backend.src.services.moonshot_service import MoonshotLLMService
from apps.backend.src.services.openrouter_service import OpenRouterLLMService

logger = logging.getLogger(__name__)


def create_llm_service(
    settings: AppSettings | None = None,
) -> OllamaLLMService | GeminiLLMService | GroqLLMService | CerebrasLLMService | AnthropicLLMService | MoonshotLLMService | OpenRouterLLMService:
    """Create the LLM service based on settings.llm.mode.

    Modes: 'local' (Ollama), 'api' (Gemini), 'groq', 'cerebras',
    'anthropic' (Haiku), 'moonshot' (Kimi K2 direct), 'openrouter' (Kimi K2 via OpenRouter).
    """
    if settings is None:
        settings = AppSettings()

    mode = settings.llm.mode

    if mode == "openrouter":
        if not settings.llm.openrouter_api_key:
            logger.warning("OpenRouter modu secili ama API key tanimlanmamis, local moda donuluyor")
            return OllamaLLMService()
        logger.info("LLM modu: OpenRouter (%s)", settings.llm.openrouter_model)
        return OpenRouterLLMService(
            api_key=settings.llm.openrouter_api_key,
            model=settings.llm.openrouter_model,
        )

    if mode == "moonshot":
        if not settings.llm.moonshot_api_key:
            logger.warning("Moonshot modu secili ama API key tanimlanmamis, local moda donuluyor")
            return OllamaLLMService()
        logger.info("LLM modu: Moonshot (%s)", settings.llm.moonshot_model)
        return MoonshotLLMService(
            api_key=settings.llm.moonshot_api_key,
            model=settings.llm.moonshot_model,
        )

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
