"""LLM settings routes -- /api/v1/settings."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from apps.backend.src.dependencies import get_current_user
from apps.backend.src.schemas.auth import UserInfo
from apps.backend.src.services.llm_factory import create_llm_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class LLMSettingsResponse(BaseModel):
    mode: str  # "local" | "api"
    ollama_url: str
    ollama_model: str
    ollama_fallback_model: str
    ollama_fallback_enabled: bool
    gemini_model: str
    gemini_api_key_set: bool  # True if key is configured, never expose the key
    temperature: float
    top_p: float
    max_tokens: int


class LLMSettingsUpdate(BaseModel):
    mode: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str | None = None
    ollama_fallback_enabled: bool | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None


# ---------------------------------------------------------------------------
# GET /api/v1/settings/llm
# ---------------------------------------------------------------------------

@router.get("/llm", response_model=LLMSettingsResponse)
async def get_llm_settings(
    request: Request,
    user: UserInfo = Depends(get_current_user),
) -> LLMSettingsResponse:
    """Return current LLM configuration (API key is masked)."""
    app_settings = getattr(request.app.state, "app_settings", None)
    if app_settings is None:
        from config.settings import AppSettings
        app_settings = AppSettings()

    return LLMSettingsResponse(
        mode=app_settings.llm.mode,
        ollama_url=app_settings.llm.ollama_url,
        ollama_model=app_settings.llm.model_name,
        ollama_fallback_model=app_settings.llm.fallback_model,
        ollama_fallback_enabled=app_settings.llm.ollama_fallback_enabled,
        gemini_model=app_settings.llm.gemini_model,
        gemini_api_key_set=bool(app_settings.llm.gemini_api_key),
        temperature=app_settings.llm.temperature,
        top_p=app_settings.llm.top_p,
        max_tokens=app_settings.llm.max_tokens,
    )


# ---------------------------------------------------------------------------
# PUT /api/v1/settings/llm
# ---------------------------------------------------------------------------

@router.put("/llm", response_model=LLMSettingsResponse)
async def update_llm_settings(
    body: LLMSettingsUpdate,
    request: Request,
    user: UserInfo = Depends(get_current_user),
) -> LLMSettingsResponse:
    """Update LLM settings and hot-swap the provider if mode changes."""
    app_settings = getattr(request.app.state, "app_settings", None)
    if app_settings is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Uygulama ayarlari yuklenemedi.",
        )

    # Apply updates to settings
    if body.mode is not None:
        if body.mode not in ("local", "api"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Gecersiz mod. 'local' veya 'api' olmali.",
            )
        app_settings.llm.mode = body.mode

    if body.gemini_api_key is not None:
        app_settings.llm.gemini_api_key = body.gemini_api_key

    if body.gemini_model is not None:
        app_settings.llm.gemini_model = body.gemini_model

    if body.ollama_fallback_enabled is not None:
        app_settings.llm.ollama_fallback_enabled = body.ollama_fallback_enabled

    if body.temperature is not None:
        app_settings.llm.temperature = body.temperature

    if body.top_p is not None:
        app_settings.llm.top_p = body.top_p

    if body.max_tokens is not None:
        app_settings.llm.max_tokens = body.max_tokens

    # Hot-swap LLM service
    old_service = getattr(request.app.state, "llm_service", None)
    if old_service is not None:
        try:
            await old_service.shutdown()
        except Exception:
            logger.warning("Old LLM service shutdown failed")

    try:
        new_service = create_llm_service(app_settings)
        await new_service.initialize()
    except Exception:
        logger.exception("New LLM service initialization failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Yeni LLM servisi baslatilamadi. Ayarlari kontrol edin.",
        )

    request.app.state.llm_service = new_service
    request.app.state.report_generator.llm = new_service
    request.app.state.app_settings = app_settings

    logger.info(
        "LLM service hot-swapped (provider=%s, model=%s)",
        new_service.provider_name,
        new_service.model_name,
    )

    return LLMSettingsResponse(
        mode=app_settings.llm.mode,
        ollama_url=app_settings.llm.ollama_url,
        ollama_model=app_settings.llm.model_name,
        ollama_fallback_model=app_settings.llm.fallback_model,
        ollama_fallback_enabled=app_settings.llm.ollama_fallback_enabled,
        gemini_model=app_settings.llm.gemini_model,
        gemini_api_key_set=bool(app_settings.llm.gemini_api_key),
        temperature=app_settings.llm.temperature,
        top_p=app_settings.llm.top_p,
        max_tokens=app_settings.llm.max_tokens,
    )
