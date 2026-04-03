# =============================================
# KlinikAsistan Backend - CPU Docker Image
# =============================================

# Stage 1: Dependencies (cached unless requirements change)
FROM python:3.11-slim AS deps

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

# Stage 2: Application
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from deps stage
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Copy application code
COPY config/ ./config/
COPY src/ ./src/
COPY apps/backend/ ./apps/backend/
COPY shared/ ./shared/

# Create data directory (will be overridden by volume mount)
RUN mkdir -p data/recordings data/rag/chroma_db data/icd10_chroma

# Force CPU mode for WhisperX
ENV ASR_WHISPER__DEVICE=cpu
ENV ASR_WHISPER__COMPUTE_TYPE=int8

EXPOSE 8700

CMD ["uvicorn", "apps.backend.src.main:app", "--host", "0.0.0.0", "--port", "8700"]
