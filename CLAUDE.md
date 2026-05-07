# Doctor AI Assistant
Electron desktop app + Python FastAPI backend for AI-assisted medical
documentation in Turkish polyclinics.

## Architecture
- Frontend: Electron + React 18 + TypeScript (apps/frontend/)
- Backend: Python 3.11 + FastAPI + Uvicorn (apps/backend/)
- Existing ASR: src/ and config/ directories (DO NOT MODIFY)
- Communication: WebSocket (audio/transcription), SSE (LLM streaming), REST (CRUD)
- API Contract: shared/api-spec.json (source of truth for BOTH layers)
- Database: SQLite in data/asr.db
- ICD-10 Database: SQLite in data/icd10.db (11,332 Turkish ICD-10 codes)
- ICD-10 Vector DB: ChromaDB in data/icd10_chroma/ (sentence embeddings for semantic search)

## LLM Configuration
- **Production LLM: Anthropic Claude Haiku 4.5** (`claude-haiku-4-5-20251001`)
- Set in .env: `ASR_LLM__MODE=anthropic` and `ASR_LLM__ANTHROPIC_API_KEY=<key>`
- max_tokens must be >= 8192 for batch anamnesis generation (25 fields JSON)
- Alternative providers available: Gemini, Groq, Cerebras, Ollama (local)
- Batch prompt generates all anamnesis fields in a single LLM call
- ICD-10 pipeline: NER → Vector DB semantic search → LLM selection (not generation)

## ICD-10 Setup (required after fresh clone)
1. Import ICD-10 codes: `python -m apps.backend.src.scripts.import_icd10 <icd10.sql>`
2. Build vector DB: `python -m apps.backend.src.scripts.build_icd10_vectors`

## Anamnez RAG Setup
Real-anamnesis RAG (BGE-M3 + metadata) uses a corpus of de-identified hospital
reports. **Everything is committed** — clone-and-run works out of the box:
- `data/Anemnez_tetkik/` (raw Excel, 10 MB)
- `data/anamnez.db` (SQLite, 32 MB)
- `data/anamnez_chroma_bge-m3_metadata/` (production ChromaDB, 153 MB)

Smoke verify after clone: `python -m apps.backend.src.rag.test_rag_live`

If you want to **rebuild** the ChromaDB (e.g. swap embedding model), redirect to
a separate folder so the committed one stays untouched:
```bash
python -m apps.backend.src.scripts.build_anamnez_vectors --profile bge-m3 --output-dir data/anamnez_chroma_experimental
```

To disable RAG entirely (e.g. evaluating without it), set `ANAMNEZ_RAG_ENABLED=false` in `.env`.

## OpenEMR Setup
Backend talks to OpenEMR over (a) OAuth2 REST API and (b) direct MariaDB queries
via `aiomysql`. Configuration lives in a separate `.env.openemr` file:

1. `cp .env.openemr.example .env.openemr`
2. Pick scenario (A) Docker compose internal, (B) compose + host backend, or
   (C) native XAMPP — uncomment the matching block.
3. **Register OAuth client in OpenEMR Admin Panel** (Admin → System → API Clients)
   and paste the resulting `client_id` / `client_secret` into `.env.openemr`.
   Without this, OAuth2 calls fail and the service logs a warning at startup.

Docker stack details: see `docker/README.md`.

## Commands
- Backend dev: cd ASR1 && /c/Users/Huckleberry/miniconda3/envs/asr/python.exe -m uvicorn apps.backend.src.main:app --reload --host 127.0.0.1 --port 8700
- Frontend dev: cd apps/frontend && npm run dev
- Backend tests: /c/Users/Huckleberry/miniconda3/envs/asr/python.exe -m pytest apps/backend/tests/ -v
- Frontend tests: cd apps/frontend && npm test

## Code Style
- TypeScript strict mode, functional React components with hooks
- Python: type hints required, async/await for I/O, Pydantic v2 models
- No `any` in TypeScript, no `# type: ignore` in Python without justification
- All UI text in Turkish

## Security Requirements (CRITICAL - MEDICAL APP)
- Electron: contextIsolation=true, nodeIntegration=false, sandbox=true
- NEVER log PHI (patient names, TC Kimlik, medical records)
- Input validation on ALL API endpoints via Pydantic
- Audit logging for all data access and modifications
- KVKK compliance: explicit consent before recording

## Agent Coordination
- Frontend agent owns ONLY: apps/frontend/
- Backend agent owns ONLY: apps/backend/
- Shared contracts: shared/ (read by both)
- NEVER modify files in src/ or config/ (existing ASR pipeline)
