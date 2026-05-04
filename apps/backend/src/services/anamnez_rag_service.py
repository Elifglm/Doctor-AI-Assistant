"""Retrieval service over the dahiliye anamnez ChromaDB collections.

Parallel to RAGService — does not touch the existing medical_knowledge
collection. Loads its own embedding model (per profile) and queries the
collection produced by build_anamnez_vectors.py.

Usage at startup:
    svc = AnamnezRAGService(profile="e5-base", fmt="baseline")
    await svc.initialize()
    results = await svc.query_similar_cases("boğaz ağrısı 2 gündür", top_k=5)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apps.backend.src.rag.phi_guard import mask_phi
from apps.backend.src.services.embedding_config import (
    EmbeddingProfile,
    PROFILES,
    get_profile,
)

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]


@dataclass
class AnamnezResult:
    form_id: int
    document: str
    metadata: dict[str, Any]
    distance: float


class AnamnezRAGService:
    """Read-only retrieval over a pre-built anamnez ChromaDB collection."""

    def __init__(
        self,
        profile: str = "e5-base",
        fmt: str = "baseline",
        persist_dir: str | None = None,
        collection_name: str | None = None,
    ) -> None:
        if profile not in PROFILES:
            raise ValueError(f"unknown profile {profile!r}; pick from {sorted(PROFILES)}")
        self._profile: EmbeddingProfile = get_profile(profile)
        self._fmt = fmt
        self._persist_dir = persist_dir or str(
            _PROJECT_ROOT / "data" / f"anamnez_chroma_{profile}_{fmt}"
        )
        self._collection_name = collection_name or f"anamnez_{fmt}"
        self._client: Any = None
        self._collection: Any = None
        self._model: Any = None

    async def initialize(self) -> None:
        import chromadb  # type: ignore[import-untyped]
        from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

        path = Path(self._persist_dir)
        if not path.exists():
            raise FileNotFoundError(
                f"Anamnez chroma dir not found: {path}. "
                f"Run build_anamnez_vectors.py for profile={self._profile.name} fmt={self._fmt} first."
            )

        self._client = chromadb.PersistentClient(path=str(path))
        self._collection = self._client.get_collection(self._collection_name)

        # Lazy model load on a worker thread (sentence-transformers is heavy)
        self._model = await asyncio.to_thread(
            SentenceTransformer, self._profile.model_id
        )
        logger.info(
            "AnamnezRAGService ready (profile=%s fmt=%s docs=%d)",
            self._profile.name, self._fmt, self._collection.count(),
        )

    @property
    def is_ready(self) -> bool:
        return self._collection is not None and self._model is not None

    @property
    def doc_count(self) -> int:
        if self._collection is None:
            return 0
        return self._collection.count()

    def _embed_query(self, text: str) -> list[float]:
        if self._profile.query_prefix:
            text = self._profile.query_prefix + text
        emb = self._model.encode(
            [text], normalize_embeddings=True, convert_to_numpy=True
        )
        return emb[0].tolist()

    async def query_similar_cases(
        self,
        text: str,
        top_k: int = 5,
        where: dict[str, Any] | None = None,
        n_candidates: int | None = None,
    ) -> list[AnamnezResult]:
        if not self.is_ready or not text.strip():
            return []

        n = n_candidates or max(top_k * 4, 20)
        n = min(n, self._collection.count())

        # encode + chroma both sync; offload to thread
        def _run() -> list[AnamnezResult]:
            emb = self._embed_query(text)
            kwargs: dict[str, Any] = {"query_embeddings": [emb], "n_results": n}
            if where:
                kwargs["where"] = where
            res = self._collection.query(**kwargs)
            ids = res["ids"][0]
            docs = res["documents"][0]
            metas = res["metadatas"][0]
            dists = res["distances"][0]
            out: list[AnamnezResult] = []
            for _id, doc, meta, dist in zip(ids, docs, metas, dists):
                # Defense-in-depth: 2nd PHI mask layer (1st is at build time).
                # Idempotent — already-masked text passes through unchanged.
                safe_doc = mask_phi(doc) if doc else doc
                out.append(
                    AnamnezResult(
                        form_id=int(meta.get("form_id", 0)),
                        document=safe_doc,
                        metadata=meta or {},
                        distance=float(dist),
                    )
                )
            return out[:top_k]

        return await asyncio.to_thread(_run)
