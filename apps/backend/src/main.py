"""FastAPI application entry-point for Doctor AI Assistant API."""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

# Add FFmpeg to PATH so whisperx and other subprocess calls can find it
import glob as _glob

_FFMPEG_PATTERNS = [
    os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"
        r"\Gyan.FFmpeg_Microsoft.Winget.Source_*"
        r"\ffmpeg-*-full_build\bin"
    ),
    # Legacy path (original dev machine)
    (
        r"C:\Users\Huckleberry\AppData\Local\Microsoft\WinGet\Packages"
        r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
        r"\ffmpeg-8.0.1-full_build\bin"
    ),
]
for _pattern in _FFMPEG_PATTERNS:
    _matches = _glob.glob(_pattern)
    if _matches:
        _ffmpeg_dir = _matches[0]
        if _ffmpeg_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = _ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
        break

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure the ASR1 project root is on sys.path so that the existing
# `src/` and `config/` packages can be imported by downstream code.
_PROJECT_ROOT = str(Path(__file__).resolve().parents[4])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from apps.backend.src.db.database import init_db
from apps.backend.src.routes import admin as admin_routes
from apps.backend.src.routes import appointments as appointment_routes
from apps.backend.src.routes import auth as auth_routes
from apps.backend.src.routes import data as data_routes
from apps.backend.src.routes import health as health_routes
from apps.backend.src.routes import icd10 as icd10_routes
from apps.backend.src.routes import sut_tetkik as sut_tetkik_routes
from apps.backend.src.routes import reports as reports_routes
from apps.backend.src.routes import sessions as sessions_routes
from apps.backend.src.routes import settings as settings_routes
from apps.backend.src.routes import transcription as transcription_routes


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle events."""
    import logging

    logger = logging.getLogger(__name__)
    await init_db()

    # ---- Seed default users ----
    from apps.backend.src.services.auth_service import seed_default_users
    await seed_default_users()

    # ---- LLM pipeline services (lazy init, non-blocking) ----
    from config.settings import AppSettings
    from apps.backend.src.services.llm_factory import create_llm_service
    from apps.backend.src.services.ner_service import NERService
    from apps.backend.src.services.rag_service import RAGService
    from apps.backend.src.services.report_generator import ReportGenerator

    app_settings = AppSettings()
    llm_service = create_llm_service(app_settings)
    ner_service = NERService()

    # Legacy synthetic RAG (medical_knowledge collection). Off by default;
    # set ASR_RAG__USE_SYNTHETIC=true to revive for archival comparison.
    rag_service: RAGService | None = None
    if app_settings.rag.use_synthetic:
        rag_service = RAGService()
        try:
            await rag_service.initialize()
        except Exception:
            logger.warning("Synthetic RAG service initialization failed")
            rag_service = None
    else:
        logger.info("Synthetic RAG disabled (set ASR_RAG__USE_SYNTHETIC=true to revive)")

    try:
        await llm_service.initialize()
    except Exception:
        logger.warning(
            "LLM service initialization failed (provider=%s)",
            llm_service.provider_name,
        )

    # NER is lazy-loaded on first use (heavy model ~500MB)

    # ---- ICD-10 services ----
    from apps.backend.src.services.icd10_service import ICD10Service
    from apps.backend.src.services.icd10_vector_service import ICD10VectorService
    from apps.backend.src.services.icd10_suggestion_service import ICD10SuggestionService

    icd10_service = ICD10Service()
    icd10_vector_service = ICD10VectorService()
    try:
        await icd10_vector_service.initialize()
    except Exception:
        logger.warning("ICD-10 vector service initialization failed")

    icd10_suggestion_service = ICD10SuggestionService(
        llm=llm_service,
        icd10_service=icd10_service,
        vector_service=icd10_vector_service,
        ner_service=ner_service,
    )

    # ---- SUT tetkik services ----
    from apps.backend.src.services.sut_service import SUTService
    from apps.backend.src.services.sut_vector_service import SUTVectorService
    from apps.backend.src.services.sut_suggestion_service import SUTSuggestionService

    sut_service = SUTService()
    sut_vector_service = SUTVectorService()
    try:
        await sut_vector_service.initialize()
    except Exception:
        logger.warning("SUT tetkik vector service initialization failed")

    sut_suggestion_service = SUTSuggestionService(
        llm=llm_service,
        sut_service=sut_service,
        vector_service=sut_vector_service,
        ner_service=ner_service,
    )

    # ---- Anamnez RAG (real hospital corpus, BGE-M3 × metadata) ----
    from apps.backend.src.services.anamnez_rag_service import AnamnezRAGService

    anamnez_rag_service = AnamnezRAGService(
        profile=app_settings.rag.anamnez_profile,
        fmt=app_settings.rag.anamnez_fmt,
    )
    try:
        await anamnez_rag_service.initialize()
        if app_settings.rag.anamnez_warmup:
            # 2 dummy encodes prime CUDA kernels / first-query latency cliff
            await anamnez_rag_service.query_similar_cases("warmup", top_k=1)
            await anamnez_rag_service.query_similar_cases("warmup", top_k=1)
            logger.info("AnamnezRAG warmup done")
    except FileNotFoundError as e:
        logger.critical(
            "AnamnezRAG initialization FAILED: %s. "
            "Run: python -m apps.backend.src.scripts.build_anamnez_vectors "
            "--profile %s --format %s",
            e, app_settings.rag.anamnez_profile, app_settings.rag.anamnez_fmt,
        )
        raise
    except Exception:
        logger.critical(
            "AnamnezRAG initialization FAILED. Check ChromaDB dir + model cache.",
            exc_info=True,
        )
        raise

    report_generator = ReportGenerator(
        ner_service,
        rag_service,
        llm_service,
        icd10_suggestion_service,
        sut_suggestion_service,
        anamnez_rag=anamnez_rag_service,
        default_top_k=app_settings.rag.anamnez_top_k,
        use_synthetic_rag=app_settings.rag.use_synthetic,
    )

    # ---- OpenEMR integration ----
    from apps.backend.src.services.openemr_service import OpenEMRService

    openemr_service = OpenEMRService()
    try:
        await openemr_service.initialize()
    except Exception:
        logger.warning("OpenEMR service initialization failed")

    app.state.llm_service = llm_service
    app.state.ner_service = ner_service
    app.state.rag_service = rag_service
    app.state.anamnez_rag_service = anamnez_rag_service
    app.state.report_generator = report_generator
    app.state.icd10_service = icd10_service
    app.state.icd10_suggestion_service = icd10_suggestion_service
    app.state.sut_service = sut_service
    app.state.sut_suggestion_service = sut_suggestion_service
    app.state.openemr_service = openemr_service
    app.state.app_settings = app_settings

    yield

    # Shutdown
    await openemr_service.shutdown()
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
app.include_router(admin_routes.router)
app.include_router(appointment_routes.router)
app.include_router(sessions_routes.router)
app.include_router(transcription_routes.router)
app.include_router(reports_routes.router)
app.include_router(settings_routes.router)
app.include_router(icd10_routes.router)
app.include_router(sut_tetkik_routes.router)
app.include_router(data_routes.router)
