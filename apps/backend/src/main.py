"""FastAPI application entry-point for Doctor AI Assistant API."""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

# Add FFmpeg to PATH so whisperx and other subprocess calls can find it
_FFMPEG_DIR = (
    r"C:\Users\Huckleberry\AppData\Local\Microsoft\WinGet\Packages"
    r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-8.0.1-full_build\bin"
)
if _FFMPEG_DIR not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure the ASR1 project root is on sys.path so that the existing
# `src/` and `config/` packages can be imported by downstream code.
_PROJECT_ROOT = str(Path(__file__).resolve().parents[4])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from apps.backend.src.db.database import init_db
from apps.backend.src.routes import auth as auth_routes
from apps.backend.src.routes import data as data_routes
from apps.backend.src.routes import health as health_routes
from apps.backend.src.routes import reports as reports_routes
from apps.backend.src.routes import sessions as sessions_routes
from apps.backend.src.routes import transcription as transcription_routes


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle events."""
    import logging

    logger = logging.getLogger(__name__)
    await init_db()

    # ---- LLM pipeline services (lazy init, non-blocking) ----
    from apps.backend.src.services.llm_service import LLMService
    from apps.backend.src.services.ner_service import NERService
    from apps.backend.src.services.rag_service import RAGService
    from apps.backend.src.services.report_generator import ReportGenerator

    llm_service = LLMService()
    ner_service = NERService()
    rag_service = RAGService()

    try:
        await llm_service.initialize()
    except Exception:
        logger.warning("LLM service initialization failed (Ollama may not be running)")

    try:
        await rag_service.initialize()
    except Exception:
        logger.warning("RAG service initialization failed")

    # NER is lazy-loaded on first use (heavy model ~500MB)

    report_generator = ReportGenerator(ner_service, rag_service, llm_service)

    app.state.llm_service = llm_service
    app.state.ner_service = ner_service
    app.state.rag_service = rag_service
    app.state.report_generator = report_generator

    yield

    # Shutdown
    await llm_service.shutdown()


app = FastAPI(
    title="Doctor AI Assistant API",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS -- allow local dev origins
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:8080",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers (sessions, transcription, reports will be added later)
# ---------------------------------------------------------------------------
app.include_router(health_routes.router)
app.include_router(auth_routes.router)
app.include_router(sessions_routes.router)
app.include_router(transcription_routes.router)
app.include_router(reports_routes.router)
app.include_router(data_routes.router)
