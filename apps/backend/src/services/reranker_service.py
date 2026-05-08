"""Cross-encoder reranker — biencoder→cross-encoder cascade için precision boost.

Vector DB'nin (BGE-M3 biencoder) verdiği top-K aday havuzunu,
cross-encoder ile yeniden sıralar. Cross-encoder query × candidate çiftini
BİRLİKTE encode eder → daha hassas relevance skoru.

Akademik referans:
- Reimers & Gurevych 2019 (sentence-BERT cascade)
- Nogueira & Cho 2019 (passage rerank with BERT)
- BAAI/bge-reranker-v2-m3: multilingual (Türkçe destekli), ~600MB

Feature flag: ``ASR_RERANKER_ENABLED`` env var.
  - "true"  → reranker aktif, biencoder→cross-encoder cascade çalışır
  - "false" (default) → reranker yok, mevcut davranış korunur

Kullanım:
    reranker = RerankerService()
    await reranker.initialize()  # lazy, ~30 sn ilk yüklemede
    top_10 = await reranker.rerank(
        query="Hastada tip 2 diyabet ve hipertansiyon var",
        candidates=[{"icd_kodu": "E11.9", "tani": "...", ...}, ...],
        top_k=10,
        doc_field="tani",
    )
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class RerankerService:
    """Lazy-loaded cross-encoder reranker.

    Model BGE-reranker-v2-m3 (~600MB) HF cache'den yüklenir; ilk init ~30 sn,
    sonraki çağrılar hızlı. Tek bir query × N candidate scoring yaklaşık
    150ms (CPU, N=25).

    Feature flag default OFF — production behavior değişmez. Açmak için
    ``ASR_RERANKER_ENABLED=true`` env var.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        max_length: int = 512,
    ) -> None:
        self._model_name = model_name
        self._max_length = max_length
        self._model: Any = None
        self._enabled = os.getenv("ASR_RERANKER_ENABLED", "false").lower() in (
            "true", "1", "yes", "on",
        )
        logger.info(
            "RerankerService configured (enabled=%s, model=%s)",
            self._enabled, self._model_name,
        )

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def is_ready(self) -> bool:
        return self._model is not None

    async def initialize(self) -> None:
        """Lazy-load model. No-op if disabled or already loaded."""
        if not self._enabled or self._model is not None:
            return
        try:
            from sentence_transformers import CrossEncoder
            logger.info("RerankerService loading model: %s", self._model_name)
            self._model = await asyncio.to_thread(
                CrossEncoder, self._model_name, max_length=self._max_length
            )
            logger.info("RerankerService model loaded")
        except Exception:
            logger.exception("RerankerService model load failed — disabling")
            self._enabled = False
            self._model = None

    async def rerank(
        self,
        query: str,
        candidates: list[dict],
        top_k: int = 10,
        doc_field: str = "tani",
    ) -> list[dict]:
        """Rerank candidate list by cross-encoder relevance to query.

        Args:
            query: Free-text query (transkript veya rapor bağlamı)
            candidates: Aday liste (her aday dict, doc_field içerir)
            top_k: En üstten kaç aday döndür (default 10)
            doc_field: Aday içindeki metin alanı (örn. "tani" ICD, "adi" SUT)

        Returns:
            Yeniden sıralanmış aday listesi (top_k uzunluğunda).
            Her aday'a ``rerank_score`` alanı eklenir.

        Reranker disabled veya henüz init edilmemişse adayları olduğu gibi
        kırpıp döner (mevcut sırayla). Çağıran tarafın güvenle kullanması için.
        """
        if not candidates:
            return []

        # Disabled or not initialized → preserve existing order, just trim
        if not self._enabled or self._model is None:
            return candidates[:top_k]

        # Build (query, doc) pairs for cross-encoder
        pairs = [(query, str(c.get(doc_field, "") or "")) for c in candidates]
        try:
            scores = await asyncio.to_thread(
                self._model.predict, pairs, show_progress_bar=False,
            )
        except Exception:
            logger.exception("Reranker prediction failed — falling back to original order")
            return candidates[:top_k]

        # Annotate + sort descending by rerank score
        for c, s in zip(candidates, scores):
            c["rerank_score"] = float(s)

        sorted_cands = sorted(
            candidates, key=lambda c: c.get("rerank_score", 0.0), reverse=True
        )
        return sorted_cands[:top_k]
