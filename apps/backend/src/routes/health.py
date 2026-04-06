"""Health-check route."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1", tags=["health"])


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded" | "error"
    gpu_available: bool
    gpu_name: Optional[str] = None
    gpu_memory_used_mb: Optional[float] = None
    gpu_memory_total_mb: Optional[float] = None
    db_connected: bool
    asr_pipeline_ready: bool
    ollama_status: str  # "connected" | "disconnected" | "unknown"
    ollama_model_loaded: bool
    rag_doc_count: int
    version: str
    llm_mode: str = "local"  # "local" | "api"
    llm_provider: str = "ollama"  # "ollama" | "gemini"
    llm_model_name: str = ""


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    """Return system health: GPU, DB, pipeline, Ollama status."""

    # --- GPU ---
    gpu_available = False
    gpu_name: str | None = None
    gpu_memory_used_mb: float | None = None
    gpu_memory_total_mb: float | None = None
    try:
        import torch  # type: ignore[import-untyped]

        if torch.cuda.is_available():
            gpu_available = True
            gpu_name = torch.cuda.get_device_name(0)
            mem = torch.cuda.mem_get_info(0)
            gpu_memory_total_mb = round(mem[1] / (1024 * 1024), 1)
            gpu_memory_used_mb = round((mem[1] - mem[0]) / (1024 * 1024), 1)
    except Exception:
        pass

    # --- DB ---
    db_connected = False
    try:
        from apps.backend.src.db.database import engine

        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        db_connected = True
    except Exception:
        pass

    # --- Pipeline ---
    asr_pipeline_ready = False
    try:
        from apps.backend.src.services.asr_service import asr_service
        asr_pipeline_ready = asr_service.is_ready
    except Exception:
        pass

    # --- LLM provider ---
    ollama_status = "unknown"
    ollama_model_loaded = False
    llm_mode = "local"
    llm_provider = "ollama"
    llm_model_name = ""
    try:
        llm_service = getattr(request.app.state, "llm_service", None)
        if llm_service is not None:
            llm_provider = getattr(llm_service, "provider_name", "ollama")
            llm_model_name = getattr(llm_service, "model_name", "")
            app_settings = getattr(request.app.state, "app_settings", None)
            if app_settings is not None:
                llm_mode = app_settings.llm.mode
            healthy = await llm_service.check_health()
            ollama_status = "connected" if healthy else "disconnected"
            if healthy and hasattr(llm_service, "is_model_loaded"):
                ollama_model_loaded = await llm_service.is_model_loaded()
    except Exception:
        ollama_status = "disconnected"

    # --- RAG ---
    rag_doc_count = 0
    try:
        rag_service = getattr(request.app.state, "rag_service", None)
        if rag_service is not None:
            rag_doc_count = rag_service.doc_count
    except Exception:
        pass

    # --- Overall status ---
    if db_connected and gpu_available:
        overall = "ok"
    elif db_connected:
        overall = "degraded"
    else:
        overall = "error"

    return HealthResponse(
        status=overall,
        gpu_available=gpu_available,
        gpu_name=gpu_name,
        gpu_memory_used_mb=gpu_memory_used_mb,
        gpu_memory_total_mb=gpu_memory_total_mb,
        db_connected=db_connected,
        asr_pipeline_ready=asr_pipeline_ready,
        ollama_status=ollama_status,
        ollama_model_loaded=ollama_model_loaded,
        rag_doc_count=rag_doc_count,
        version="2.0.0",
        llm_mode=llm_mode,
        llm_provider=llm_provider,
        llm_model_name=llm_model_name,
    )
