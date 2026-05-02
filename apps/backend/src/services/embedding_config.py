"""Embedding model profiles for the retrieval pipeline.

Lets us run two ChromaDB index sets side-by-side and switch between them
via the ``EMBEDDING_MODEL`` env var. Each profile has its own model
identifier and its own on-disk ChromaDB directory, so swapping does not
overwrite the other.

  EMBEDDING_MODEL=minilm    (default — fast, 384-d, multilingual)
  EMBEDDING_MODEL=e5-large  (heavier, 1024-d, better Turkish semantic)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class EmbeddingProfile:
    name: str
    model_id: str
    icd_chroma_dir: Path
    sut_chroma_dir: Path
    rag_chroma_dir: Path
    # Optional prefixes the model expects. e5 family in particular requires
    # ``query: `` for queries and ``passage: `` for indexed documents —
    # without them the model collapses to generic embeddings and retrieval
    # quality is no better than random.
    query_prefix: str = ""
    passage_prefix: str = ""


PROFILES: dict[str, EmbeddingProfile] = {
    "minilm": EmbeddingProfile(
        name="minilm",
        model_id="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        icd_chroma_dir=_PROJECT_ROOT / "data" / "icd10_chroma",
        sut_chroma_dir=_PROJECT_ROOT / "data" / "sut_tetkik_chroma",
        rag_chroma_dir=_PROJECT_ROOT / "data" / "rag" / "chroma_db",
    ),
    "e5-large": EmbeddingProfile(
        name="e5-large",
        model_id="intfloat/multilingual-e5-large",
        icd_chroma_dir=_PROJECT_ROOT / "data" / "icd10_chroma_e5",
        sut_chroma_dir=_PROJECT_ROOT / "data" / "sut_tetkik_chroma_e5",
        rag_chroma_dir=_PROJECT_ROOT / "data" / "rag" / "chroma_db_e5",
        # e5 family requires these prefixes; without them retrieval collapses
        # (every query returns the same generic-embedding cluster).
        query_prefix="query: ",
        passage_prefix="passage: ",
    ),
}


def get_profile(name: str | None = None) -> EmbeddingProfile:
    """Resolve the active embedding profile.

    Order: explicit ``name`` arg → ``EMBEDDING_MODEL`` env var → "minilm".
    Unknown names fall back to "minilm" so a typo never breaks startup.
    """
    key = (name or os.getenv("EMBEDDING_MODEL") or "minilm").strip().lower()
    return PROFILES.get(key, PROFILES["minilm"])
