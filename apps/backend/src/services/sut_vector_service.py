"""SUT tetkik vector search service using Turkish BERT embeddings + ChromaDB."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_CHROMA_DIR = _PROJECT_ROOT / "data" / "sut_tetkik_chroma"
_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


@dataclass
class SUTVectorResult:
    kodu: str
    adi: str
    brans: str
    ana_kategori: str
    puan: float
    score: float
    source_term: str


class SUTVectorService:
    """Semantic search over SUT tetkik codes using sentence embeddings."""

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
            collection = client.get_collection("sut_tetkik_vectors")
            return model, collection

        self._model, self._collection = await asyncio.to_thread(_load)
        count = self._collection.count()
        logger.info("SUTVectorService initialized (%d tetkik)", count)

    @property
    def is_ready(self) -> bool:
        return self._model is not None and self._collection is not None

    async def search(
        self, query: str, n_results: int = 5, brans: str | None = None
    ) -> list[SUTVectorResult]:
        """Semantic search for SUT tetkik codes matching a query term."""
        if not self.is_ready:
            return []

        import asyncio

        def _query():
            emb = self._model.encode([query]).tolist()
            where = {"brans": brans} if brans else None
            return self._collection.query(
                query_embeddings=emb, n_results=n_results, where=where
            )

        results = await asyncio.to_thread(_query)

        items: list[SUTVectorResult] = []
        for meta, dist in zip(
            results["metadatas"][0], results["distances"][0]
        ):
            items.append(
                SUTVectorResult(
                    kodu=meta["kodu"],
                    adi=meta["adi"],
                    brans=meta["brans"],
                    ana_kategori=meta.get("ana_kategori", ""),
                    puan=meta.get("puan", 0.0),
                    score=round(1 - dist, 3),
                    source_term=query,
                )
            )
        return items

    async def search_multiple(
        self, terms: list[str], n_per_term: int = 3, min_score: float = 0.5,
        brans: str | None = None
    ) -> list[SUTVectorResult]:
        """Search for multiple NER terms and return deduplicated candidates."""
        all_results: dict[str, SUTVectorResult] = {}

        for term in terms:
            results = await self.search(term, n_results=n_per_term, brans=brans)
            for r in results:
                if r.score < min_score:
                    continue
                if r.kodu not in all_results or r.score > all_results[r.kodu].score:
                    all_results[r.kodu] = r

        return sorted(all_results.values(), key=lambda x: -x.score)
