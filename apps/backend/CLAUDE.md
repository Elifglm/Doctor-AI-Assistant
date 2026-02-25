# Backend - FastAPI

## Scope
This directory contains the FastAPI backend that wraps the existing ASR pipeline.

## Key Rules
- Import ASR pipeline from `src.pipeline` and settings from `config.settings`
- NEVER modify files in `src/` or `config/`
- All endpoints must use Pydantic models for validation
- Use `asyncio.to_thread()` for GPU-heavy ASR operations
- Never log PHI (patient identifiers, medical data)
- Audit log every data access via `services/audit_service.py`

## Running
```bash
cd ASR1
/c/Users/Huckleberry/miniconda3/envs/asr/python.exe -m uvicorn apps.backend.src.main:app --reload --host 127.0.0.1 --port 8700
```

## Testing
```bash
/c/Users/Huckleberry/miniconda3/envs/asr/python.exe -m pytest apps/backend/tests/ -v
```

## Database
SQLite at `data/asr.db`. Schema managed in `src/db/database.py`.
