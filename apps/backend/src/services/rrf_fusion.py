"""Reciprocal Rank Fusion (RRF) — multiple retrieval kanalını birleştirme.

RRF Formula (Cormack et al. 2009):
    score(d) = Σ_q 1/(k + rank_q(d))

Burada:
- d = aday (kod)
- q = retrieval kanalı (vector, text, llm-extract, sözlük, ...)
- rank_q(d) = q kanalında d'nin sırası (1-indexed)
- k = sabit (default 60), düşük rank dominansını dengeler

**Niye RRF?** Naive merge (dedup + concat) farklı kanalların güvenilirlik
farkını GÖRMEZDEN GELİR. RRF ise:
- Aynı aday birden çok kanalda ÜSTLERDE çıkarsa skor TOPLANARAK artar
- Tek kanalda altta görünen alakasız aday düşük skorda kalır
- Kanal sayısı ne olursa olsun normalize sonuç verir

Akademik referans: Cormack, Clarke, Büttcher (2009) "Reciprocal rank
fusion outperforms condorcet and individual rank learning methods", SIGIR.

Feature flag: ``ASR_RRF_ENABLED`` (default false → mevcut naive merge davranışı)

Kullanım:
    from apps.backend.src.services.rrf_fusion import rrf_fuse

    fused = rrf_fuse(
        ranked_lists=[
            vector_candidates,    # 1. kanal
            text_candidates,      # 2. kanal
            llm_extract_candidates,  # 3. kanal
        ],
        id_field="icd_kodu",  # veya "kodu" SUT için
        k=60,
    )
    # → tek liste, RRF skoruna göre sıralı
"""
from __future__ import annotations

import logging
import os
from typing import Iterable

logger = logging.getLogger(__name__)


def rrf_fuse(
    ranked_lists: Iterable[list[dict]],
    id_field: str = "icd_kodu",
    k: int = 60,
) -> list[dict]:
    """Reciprocal Rank Fusion — birden fazla sıralı listeyi birleştirir.

    Args:
        ranked_lists: Aday listeleri (her biri zaten kendi kanalında sıralı,
                      en alakalı en üstte). Her aday dict, id_field ile uniq.
        id_field: Aday kimliği alanı (örn. "icd_kodu", "kodu")
        k: RRF sabiti (default 60, Cormack et al. tarafından önerilen)

    Returns:
        Tek aday listesi, RRF skoruna göre azalan sırada.
        Her aday'a ``rrf_score`` alanı eklenir; orijinal alanlar (skor, source)
        ilk gözlemden korunur (kanal merge order'ına göre).

    Empty input → empty output. Tek liste verilmişse RRF tek kanaldan
    rank'a karşılık gelir; davranış mevcut sıralamayı korur.
    """
    score_map: dict[str, float] = {}
    rep_map: dict[str, dict] = {}  # canonical aday objesi (ilk gözlem)
    sources_map: dict[str, list[str]] = {}  # her aday'ın hangi kanallardan geldiği

    for channel_idx, ranked in enumerate(ranked_lists):
        for rank, item in enumerate(ranked, start=1):
            kodu = str(item.get(id_field, "")).strip()
            if not kodu:
                continue
            # RRF contribution
            contrib = 1.0 / (k + rank)
            score_map[kodu] = score_map.get(kodu, 0.0) + contrib
            # Save first observation as canonical
            if kodu not in rep_map:
                rep_map[kodu] = dict(item)
                sources_map[kodu] = []
            sources_map[kodu].append(item.get("source", f"channel_{channel_idx}"))

    # Build sorted output list
    sorted_codes = sorted(score_map.keys(), key=lambda c: score_map[c], reverse=True)
    fused: list[dict] = []
    for kodu in sorted_codes:
        c = rep_map[kodu]
        c["rrf_score"] = round(score_map[kodu], 6)
        c["rrf_sources"] = sources_map[kodu]
        c["rrf_n_channels"] = len(sources_map[kodu])
        fused.append(c)

    logger.debug(
        "RRF fused %d unique candidates from %d channels (k=%d)",
        len(fused), sum(1 for _ in ranked_lists) if hasattr(ranked_lists, "__len__") else "?", k,
    )
    return fused


def is_rrf_enabled() -> bool:
    """Check feature flag — default False (naive merge fallback)."""
    return os.getenv("ASR_RRF_ENABLED", "false").lower() in ("true", "1", "yes", "on")
