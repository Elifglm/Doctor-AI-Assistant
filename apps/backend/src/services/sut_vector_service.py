"""SUT tetkik vector search service using Turkish BERT embeddings + ChromaDB."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from apps.backend.src.services.embedding_config import get_profile

logger = logging.getLogger(__name__)


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
        self._profile = get_profile()

    async def initialize(self) -> None:
        """Load embedding model and ChromaDB collection."""
        import asyncio

        profile = self._profile

        def _load():
            from sentence_transformers import SentenceTransformer
            import chromadb

            model = SentenceTransformer(profile.model_id)
            client = chromadb.PersistentClient(path=str(profile.sut_chroma_dir))
            collection = client.get_collection("sut_tetkik_vectors")
            return model, collection

        self._model, self._collection = await asyncio.to_thread(_load)
        count = self._collection.count()
        logger.info(
            "SUTVectorService initialized (profile=%s, %d tetkik)",
            profile.name, count,
        )

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
        prefixed_query = self._profile.query_prefix + query

        def _query():
            emb = self._model.encode(
                [prefixed_query], normalize_embeddings=True,
            ).tolist()
            # SUT codes are tagged "dahiliye", "ortopedi" or "her ikisi".
            # When the caller asks for a specific specialty, ALSO include
            # cross-specialty codes ("her ikisi"); otherwise common tests
            # like "Akciğer Grafisi" (her ikisi) get filtered out.
            where: dict | None
            if brans:
                where = {"brans": {"$in": [brans, "her ikisi"]}}
            else:
                where = None
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
