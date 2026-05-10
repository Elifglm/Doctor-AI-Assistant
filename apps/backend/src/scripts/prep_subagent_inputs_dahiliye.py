"""Prep subagent inputs using the dahiliye-filtered ICD vector DB (5,971 codes).

Wraps prep_subagent_inputs.py: forces EMBEDDING_MODEL=bge-m3-dahiliye and
redirects output to data/subagent_inputs_dahiliye/.

Usage:
    python -m apps.backend.src.scripts.prep_subagent_inputs_dahiliye
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Force dahiliye profile BEFORE any project import that reads env
os.environ["EMBEDDING_MODEL"] = "bge-m3-dahiliye"

try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass
# Re-assert after .env load (ensures override even if .env had a different value)
os.environ["EMBEDDING_MODEL"] = "bge-m3-dahiliye"

from apps.backend.src.scripts import prep_subagent_inputs as _base  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[4]
_base.OUT_DIR = PROJECT_ROOT / "data" / "subagent_inputs_dahiliye"
_base.OUT_DIR.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
    print(f"EMBEDDING_MODEL={os.environ.get('EMBEDDING_MODEL')}")
    print(f"OUT_DIR={_base.OUT_DIR}")
    asyncio.run(_base.main())
