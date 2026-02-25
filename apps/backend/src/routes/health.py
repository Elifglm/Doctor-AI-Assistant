"""Health-check route."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
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
    version: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return system health: GPU, DB, pipeline status."""

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
        # Just check the module is importable -- don't instantiate
        import importlib

        importlib.import_module("src.pipeline")
        asr_pipeline_ready = True
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
        version="1.0.0",
    )
