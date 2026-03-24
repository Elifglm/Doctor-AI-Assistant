"""ICD-10 vector search service using Turkish BERT embeddings + ChromaDB."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.settings import AppSettings

logger = logging.getLogger(__name__)

settings = AppSettings()

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_CHROMA_DIR = _PROJECT_ROOT / "data" / "icd10_chroma"
_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


@dataclass
class ICD10VectorResult:
    icd_kodu: str
    tani: str
    ust_kod: str
    seviye: int
    score: float
    source_term: str


class ICD10VectorService:
    """Semantic search over ICD-10 codes using sentence embeddings."""

    def __init__(self) -> None:
        self._model: Any = None
        self._collection: Any = None

    async def initialize(self) -> None:
        """Load embedding model and ChromaDB collection."""
        import asyncio

        def _load():
            from sentence_transformers import SentenceTransformer
            import chromadb

            model = SentenceTransformer(_EMBEDDING_MODEL)
            client = chromadb.PersistentClient(path=str(_CHROMA_DIR))
            collection = client.get_collection("icd10_vectors")
            return model, collection

        self._model, self._collection = await asyncio.to_thread(_load)
        count = self._collection.count()
        logger.info("ICD10VectorService initialized (%d codes)", count)

    @property
    def is_ready(self) -> bool:
        return self._model is not None and self._collection is not None

    async def search(
        self, query: str, n_results: int = 5
    ) -> list[ICD10VectorResult]:
        """Semantic search for ICD-10 codes matching a query term."""
        if not self.is_ready:
            return []

        import asyncio

        def _query():
            emb = self._model.encode([query]).tolist()
            return self._collection.query(
                query_embeddings=emb, n_results=n_results
            )

        results = await asyncio.to_thread(_query)

        items: list[ICD10VectorResult] = []
        for meta, dist in zip(
            results["metadatas"][0], results["distances"][0]
        ):
            items.append(
                ICD10VectorResult(
                    icd_kodu=meta["icd_kodu"],
                    tani=meta["tani"],
                    ust_kod=meta.get("ust_kod", ""),
                    seviye=meta.get("seviye", 3),
                    score=round(1 - dist, 3),
                    source_term=query,
                )
            )
        return items

    async def search_multiple(
        self, terms: list[str], n_per_term: int = 3, min_score: float = 0.5
    ) -> list[ICD10VectorResult]:
        """Search for multiple NER terms and return deduplicated candidates."""
        all_results: dict[str, ICD10VectorResult] = {}

        for term in terms:
            results = await self.search(term, n_results=n_per_term)
            for r in results:
                if r.score < min_score:
                    continue
                # Keep highest score per code
                if r.icd_kodu not in all_results or r.score > all_results[r.icd_kodu].score:
                    all_results[r.icd_kodu] = r

        # Sort by score descending
        return sorted(all_results.values(), key=lambda x: -x.score)
