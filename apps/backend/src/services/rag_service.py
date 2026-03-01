"""ChromaDB-based RAG service for medical knowledge retrieval."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.settings import AppSettings

logger = logging.getLogger(__name__)

settings = AppSettings()

_PROJECT_ROOT = Path(__file__).resolve().parents[4]


@dataclass
class RAGResult:
    content: str
    metadata: dict[str, Any]
    distance: float


class RAGService:
    """Retrieval-Augmented Generation using ChromaDB + default embeddings."""

    def __init__(self, persist_dir: str | None = None) -> None:
        self._persist_dir = persist_dir or str(
            _PROJECT_ROOT / settings.rag.persist_dir
        )
        self._client: Any = None
        self._collection: Any = None

    async def initialize(self) -> None:
        """Create or load the ChromaDB collection."""
        import chromadb  # type: ignore[import-untyped]

        Path(self._persist_dir).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=self._persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=settings.rag.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        doc_count = self._collection.count()
        logger.info(
            "RAGService initialized (dir=%s, docs=%d)", self._persist_dir, doc_count
        )

    @property
    def is_ready(self) -> bool:
        return self._collection is not None

    @property
    def doc_count(self) -> int:
        if self._collection is None:
            return 0
        return self._collection.count()

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def add_documents(
        self,
        documents: list[str],
        metadatas: list[dict[str, Any]],
        ids: list[str],
    ) -> None:
        """Add documents to the collection (synchronous, for seeding)."""
        if self._collection is None:
            raise RuntimeError("RAGService not initialized.")
        self._collection.add(documents=documents, metadatas=metadatas, ids=ids)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    async def query(
        self,
        text: str,
        n_results: int | None = None,
    ) -> list[RAGResult]:
        """Retrieve the most relevant documents for a query string."""
        if self._collection is None or self._collection.count() == 0:
            return []

        n = min(n_results or settings.rag.n_results, self._collection.count())
        results = self._collection.query(query_texts=[text], n_results=n)

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]

        return [
            RAGResult(content=doc, metadata=meta, distance=dist)
            for doc, meta, dist in zip(docs, metas, dists)
        ]
