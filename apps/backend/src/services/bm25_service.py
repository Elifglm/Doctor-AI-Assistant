"""BM25 sparse retrieval — ICD-10 + SUT corpus.

BM25 (Best Match 25, Robertson & Zaragoza 2009) is a probabilistic ranking
function that complements dense embeddings. Where BGE-M3 encodes semantic
meaning, BM25 captures **lexical exact matches** — surface tokens like
"E11.9", "demir", "kreatinin" that the doctor literally said.

Why hybrid? Phase 1.1 + 1.2 error analysis showed retrieval gaps:
  - T11/T12: E11.9 not retrieved (doctor said "şeker hastalığı", semantic
    mapping went to E13)
  - T14: E78 not retrieved (doctor said "kolesterol")
  - T15 (SUT): "troponin", "INR", "sodyum" not retrieved
  - T18 (SUT): "arter kan gazı" not retrieved

These are surface-form failures: BGE-M3 abstracts away from the literal
token. BM25 fixes this by indexing on the raw lexicon.

Pipeline integration (via RRF fusion):
    dense_results   = BGE-M3 + ChromaDB.search(query_embedding)
    bm25_results    = BM25Service.search(query_text)
    text_results    = SQL LIKE fallback
    fused           = rrf_fuse([dense, bm25, text])

Reference: Robertson & Zaragoza (2009), "The Probabilistic Relevance
Framework: BM25 and Beyond", Foundations and Trends in IR.
"""
from __future__ import annotations

import logging
import pickle
import re
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi
from sqlalchemy import text

from apps.backend.src.db.icd10_database import icd10_session_maker
from apps.backend.src.db.sut_database import sut_session_maker

logger = logging.getLogger(__name__)

# Turkish character normalization for BM25 tokens (case-fold + ascii fold)
_TR_MAP = str.maketrans("ıİöÖüÜçÇşŞğĞ", "iIoOuUcCsSgG")

# Cache location — rebuild only if missing
_CACHE_DIR = Path(__file__).resolve().parents[4] / "data" / "bm25_cache"

# ─── Phase 2.2: Lemmatization ──────────────────────────────────────────────
# Zeyrek (pure Python Zemberek port) reduces Turkish inflected forms to
# canonical lemmas: "diyabetin" → "diyabet", "tetkikleri" → "tetkik".
# This bridges morphological gaps in BM25 token-matching.
#
# Loading is lazy + cached because zeyrek init is ~3s.
_LEMMATIZER = None
# In-memory token cache to avoid re-lemmatizing same words across queries
_LEMMA_CACHE: dict[str, str] = {}
# Skip lemmatization for tokens matching: pure numbers, codes (E11.9, HbA1c),
# very short tokens. Lemmatizing these wastes time and can corrupt them.
_SKIP_LEMMA_RE = re.compile(r"^([a-z]?\d|.{0,2}|[a-z]+\d.*|.*\.\d)$")


def _get_lemmatizer():
    """Lazy-init zeyrek MorphAnalyzer (one-time ~3s)."""
    global _LEMMATIZER
    if _LEMMATIZER is None:
        try:
            import zeyrek
            _LEMMATIZER = zeyrek.MorphAnalyzer()
            logger.info("Zeyrek lemmatizer initialized")
        except ImportError:
            logger.warning("zeyrek not installed; lemmatization disabled")
            _LEMMATIZER = False
    return _LEMMATIZER


def _lemmatize_token(token: str) -> str:
    """Return lemma for a single token, or token itself on skip/failure."""
    if token in _LEMMA_CACHE:
        return _LEMMA_CACHE[token]
    if _SKIP_LEMMA_RE.match(token):
        _LEMMA_CACHE[token] = token
        return token
    lem = _get_lemmatizer()
    if not lem:
        return token
    try:
        results = lem.lemmatize(token)
        if results and results[0][1]:
            # Take first lemma candidate (most common interpretation)
            out = results[0][1][0].lower()
        else:
            out = token
    except Exception:
        out = token
    _LEMMA_CACHE[token] = out
    return out


def _tokenize(text: str, lemmatize: bool = False) -> list[str]:
    """Lowercase + alphanumeric split + lemmatize + Turkish-fold.

    Phase 2.2 ORDER FIX: lemmatize BEFORE Turkish character folding because
    zeyrek requires real Turkish characters ("böbrek" not "bobrek") to find
    the correct lemma. After lemmatization, fold chars for case-insensitive
    BM25 matching with the corpus.

    Medical codes (E11.9, L107020) and short tokens are preserved as-is.
    """
    if not text:
        return []
    # Step 1: lowercase ONLY (preserve TR chars for lemmatizer)
    lowered = text.lower()
    # Step 2: tokenize (allow Turkish chars in regex)
    tokens = re.findall(r"[a-z0-9çğıöşü]+(?:\.[a-z0-9çğıöşü]+)?", lowered)
    tokens = [t for t in tokens if len(t) >= 2]
    # Step 3: lemmatize (with TR chars intact)
    if lemmatize:
        tokens = [_lemmatize_token(t) for t in tokens]
    # Step 4: NOW fold TR chars for ASCII matching
    tokens = [t.translate(_TR_MAP) for t in tokens]
    return tokens


class BM25Service:
    """Generic BM25 retrieval over a list of (id, text) tuples.

    Two static factory methods build the canonical indexes:
      - BM25Service.for_icd10()  → 11k ICD-10 codes by tani text
      - BM25Service.for_sut()    → 600+ SUT codes by adi text

    The index is built once and pickled to disk. Subsequent loads are <1s.
    """

    def __init__(self, ids: list[str], texts: list[str], extra: list[dict] | None = None):
        self._ids = ids
        self._texts = texts
        self._extra = extra or [{} for _ in ids]
        self._tokenized = [_tokenize(t) for t in texts]
        self._bm25 = BM25Okapi(self._tokenized)
        logger.info("BM25 index ready: %d documents", len(ids))

    def search(self, query: str, top_k: int = 25, expand_synonyms: bool = True) -> list[dict]:
        """Return top_k results as list of dicts with id, text, score, extra.

        Phase 2.3: when ``expand_synonyms`` is True (default), each query token
        is expanded with its TR/EN medical synonyms before BM25 scoring.
        Bridges "diabetes" ↔ "diyabetes", "hypertension" ↔ "hipertansiyon" etc.
        """
        tokens = _tokenize(query)
        if not tokens:
            return []
        if expand_synonyms:
            from apps.backend.src.services.medical_synonyms import expand_tokens
            tokens = expand_tokens(tokens)
        scores = self._bm25.get_scores(tokens)
        # Sort descending, take top_k
        indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        results = []
        for i in indices:
            if scores[i] <= 0:
                continue
            row = {
                "id": self._ids[i],
                "text": self._texts[i],
                "score": float(scores[i]),
                **self._extra[i],
            }
            results.append(row)
        return results

    @staticmethod
    async def for_icd10(force_rebuild: bool = False) -> "BM25Service":
        """Build/load BM25 index for ICD-10 corpus."""
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        # Phase 2.2: separate cache for lemmatized index
        cache_path = _CACHE_DIR / "icd10_bm25_lemma.pkl"
        if cache_path.exists() and not force_rebuild:
            logger.info("Loading ICD-10 BM25 from cache: %s", cache_path)
            with cache_path.open("rb") as f:
                ids, texts, extra = pickle.load(f)
            return BM25Service(ids, texts, extra)

        logger.info("Building ICD-10 BM25 index (first run)...")
        ids, texts, extra = [], [], []
        async with icd10_session_maker() as session:
            rows = await session.execute(
                text("SELECT icd_kodu, tani, ust_kod, seviye FROM icd10")
            )
            for row in rows:
                ids.append(row[0])
                # Index by tani + code (so "E11.9" tokens also match)
                texts.append(f"{row[1]} {row[0]}")
                extra.append({"icd_kodu": row[0], "tani": row[1], "ust_kod": row[2], "seviye": row[3]})

        with cache_path.open("wb") as f:
            pickle.dump((ids, texts, extra), f)
        logger.info("ICD-10 BM25 cached at %s (%d codes)", cache_path, len(ids))
        return BM25Service(ids, texts, extra)

    @staticmethod
    async def for_sut(force_rebuild: bool = False) -> "BM25Service":
        """Build/load BM25 index for SUT tetkik corpus."""
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        # Phase 2.2: separate cache for lemmatized index
        cache_path = _CACHE_DIR / "sut_bm25_lemma.pkl"
        if cache_path.exists() and not force_rebuild:
            logger.info("Loading SUT BM25 from cache: %s", cache_path)
            with cache_path.open("rb") as f:
                ids, texts, extra = pickle.load(f)
            return BM25Service(ids, texts, extra)

        logger.info("Building SUT BM25 index (first run)...")
        ids, texts, extra = [], [], []
        async with sut_session_maker() as session:
            rows = await session.execute(
                text("SELECT kodu, adi, brans, ana_kategori, alt_kategori, puan FROM sut_tetkik")
            )
            for row in rows:
                ids.append(row[0])
                # Index by adi + kategori + brans (so "kan", "biyokimya" match)
                texts.append(f"{row[1]} {row[3] or ''} {row[4] or ''} {row[2] or ''} {row[0]}")
                extra.append({
                    "kodu": row[0], "adi": row[1], "brans": row[2],
                    "ana_kategori": row[3], "alt_kategori": row[4], "puan": row[5],
                })

        with cache_path.open("wb") as f:
            pickle.dump((ids, texts, extra), f)
        logger.info("SUT BM25 cached at %s (%d codes)", cache_path, len(ids))
        return BM25Service(ids, texts, extra)
