# =============================================
# KlinikAsistan Backend - Multi-variant Docker Image
# TORCH_VARIANT=cpu (default) | gpu
# =============================================

# Stage 1: Dependencies (cached unless requirements change)
FROM python:3.11-slim AS deps

ARG TORCH_VARIANT=cpu

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) Once PyTorch'u dogru wheel'la kur (ONCE — sonra gelen base paketler
#    pip dependency resolution'da torch'u tatmin edici gorur, yeniden cekmez).
#    Aksi halde whisperx/pyannote/transformers PyPI'den default CUDA torch ceker.
COPY requirements-docker-torch-cpu.txt requirements-docker-torch-gpu.txt ./
RUN pip install --no-cache-dir -r "requirements-docker-torch-${TORCH_VARIANT}.txt"

# 2) Geri kalan bagimliliklari yukle (torch zaten kurulu, atlanir)
COPY requirements-docker-base.txt .
RUN pip install --no-cache-dir -r requirements-docker-base.txt

# 3) Runtime fix'leri: pyannote.audio 4.0+ ve ctranslate2 4.5+'a force-upgrade.
#    Bunlari requirements-docker-base.txt'te pin'lemek pip resolver backtracking'e
#    sebep oluyor (saatlerce). Tek tek -U ile guncelleyince sadece 2 paket etkilenir.
#    - pyannote.audio 4.0: torchaudio 2.5+ AudioMetaData API uyumu icin gerekli
#    - ctranslate2 4.5+: 4.4'teki "executable stack" Linux kernel hatasi icin
RUN pip install --no-cache-dir -U \
    "pyannote.audio>=4.0,<5.0" \
    "ctranslate2>=4.5.0,<5.0"

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

# ctranslate2 (faster-whisper backend) cuDNN/cuBLAS'i sistemde arar.
# PyTorch CUDA wheel bunlari nvidia/* paketleri olarak getirir; loader'a path'i goster.
# CPU varyantinda bu path'ler bos olur, sorun cikarmaz.
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.11/site-packages/nvidia/cudnn/lib:/usr/local/lib/python3.11/site-packages/nvidia/cublas/lib:${LD_LIBRARY_PATH}

EXPOSE 8700

CMD ["uvicorn", "apps.backend.src.main:app", "--host", "0.0.0.0", "--port", "8700"]
