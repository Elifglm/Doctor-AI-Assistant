"""FastAPI application entry-point for Doctor AI Assistant API."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure the ASR1 project root is on sys.path so that the existing
# `src/` and `config/` packages can be imported by downstream code.
_PROJECT_ROOT = str(Path(__file__).resolve().parents[4])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from apps.backend.src.db.database import init_db
from apps.backend.src.routes import auth as auth_routes
from apps.backend.src.routes import health as health_routes
from apps.backend.src.routes import reports as reports_routes
from apps.backend.src.routes import sessions as sessions_routes
from apps.backend.src.routes import transcription as transcription_routes


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle events."""
    await init_db()
    yield


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
