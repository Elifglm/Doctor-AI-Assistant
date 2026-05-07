"""Medical synonym dictionary for query expansion.

Loads a curated halk_dili → tibbi_terim_tr dictionary at startup and
provides substring-based expansion that vector search uses to bridge
colloquial input and formal terminology (e.g. "kan şekerime baktırma"
expands to include "Glukoz", "şeker", "kan şekeri" → vector finds it).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

# data/medical_synonyms.json (project root)
_DATA_PATH = Path(__file__).resolve().parents[4] / "data" / "medical_synonyms.json"


class MedicalSynonymExpander:
    """Substring-matched synonym expander.

    Loads JSON dictionary once. Builds a flat lowercase index from every
    halk_dili variation, every tibbi_terim_tr, and every kisaltma to the
    full synonym set for that entry.
    """

    CATEGORIES = ("symptoms", "diseases", "lab_tests", "imaging", "medications")

    def __init__(self, dict_path: Path | None = None) -> None:
        self._index: dict[str, set[str]] = {}
        path = dict_path or _DATA_PATH
        if not path.exists():
            logger.warning("Medical synonym dict not found at %s", path)
            return
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        self._build_index(data)
        logger.info(
            "MedicalSynonymExpander loaded: %d phrases indexed (from %s)",
            len(self._index), path.name,
        )

    def _build_index(self, data: dict) -> None:
        for category in self.CATEGORIES:
            for entry in data.get(category, []):
                halk_list = entry.get("halk_dili", []) or []
                tibbi = (entry.get("tibbi_terim_tr") or "").strip()
                kisaltma = (entry.get("kisaltma") or "").strip()
                synonyms: set[str] = set()
                if tibbi:
                    synonyms.add(tibbi)
                if kisaltma:
                    synonyms.add(kisaltma)
                for h in halk_list:
                    if isinstance(h, str) and h.strip():
                        synonyms.add(h.strip())
                if not synonyms:
                    continue
                # Index every variation (lowercase) → full synonym set
                keys: set[str] = set()
                for h in halk_list:
                    if isinstance(h, str) and h.strip():
                        keys.add(h.strip().lower())
                if tibbi:
                    keys.add(tibbi.lower())
                if kisaltma:
                    keys.add(kisaltma.lower())
                for key in keys:
                    bucket = self._index.setdefault(key, set())
                    bucket.update(synonyms)

    # Short phrases (likely abbreviations: AST, DM, HT, BNP) require word
    # boundary to avoid false positives like "hAST" inside "hastalık".
    _SHORT_THRESHOLD = 4

    def expand(self, text: str) -> list[str]:
        """Return all synonyms for any indexed phrase that appears in `text`.

        Long phrases use substring match; short ones (≤4 chars, typically
        abbreviations) require word-boundary match to prevent false hits
        like AST matching inside "hastalık".
        """
        if not text:
            return []
        lower = text.lower()
        matched: set[str] = set()
        for phrase, synonyms in self._index.items():
            if not phrase:
                continue
            if len(phrase) <= self._SHORT_THRESHOLD:
                if re.search(r"\b" + re.escape(phrase) + r"\b", lower):
                    matched.update(synonyms)
            else:
                if phrase in lower:
                    matched.update(synonyms)
        matched.discard(text)
        return list(matched)

    def expand_term(self, term: str) -> list[str]:
        """Return synonyms for an exact term (or [] if no match).

        Use when the input is a single keyword/phrase, not free text.
        """
        if not term:
            return []
        key = term.strip().lower()
        synonyms = self._index.get(key, set())
        result = {s for s in synonyms if s.lower() != key}
        return list(result)

    def expand_terms(self, terms: Iterable[str]) -> list[str]:
        """Expand a list of terms; returns terms + their synonyms (deduplicated)."""
        result: set[str] = set()
        for t in terms:
            if not t:
                continue
            t_clean = t.strip()
            if not t_clean:
                continue
            result.add(t_clean)
            result.update(self.expand_term(t_clean))
        return list(result)


# Common Turkish noise words that drown medical signal in dense embedding when
# the input is a long phrase (e.g. "MENENJİT İHTİMALİ GÖZE ALINIYOR" → vector
# search picks up "ihtimali"/"göze"/"alınıyor" rather than "menenjit").
# We strip these and add the remaining significant tokens as separate queries.
_NOISE_TOKENS: set[str] = {
    # Modal / hedge words
    "ihtimali", "ihtimal", "olasi", "olası", "olabilir", "olabilen", "şüphesi",
    "şüpheli", "muhtemelen", "muhtemel", "düşünülüyor", "düşünüldü",
    "ekarte", "dışlandı", "doğrulandı", "doğrulanmadı", "ayırıcı",
    # Discourse / connectors
    "için", "ile", "ve", "veya", "ya", "ya da", "ancak", "fakat",
    "ama", "rağmen", "halde", "üzere", "gibi", "diye",
    # Auxiliary / status verbs (often inflected)
    "var", "yok", "edildi", "edilmiş", "edilen", "yapıldı", "yapılmış",
    "olunmuş", "alınıyor", "alındı", "verildi", "verilmiş", "yazıldı",
    "geldi", "gitti", "açıldı", "kapatıldı",
    # Generic action / observation nouns
    "göze", "kontrol", "kontrolü", "kontrole", "değerlendirildi",
    "değerlendirme", "değerlendirildiği", "tetkik", "tetkikleri",
    "konsültasyon", "konsültasyonu", "muayene", "muayenesi",
    "isteme", "istek", "öneri", "önerisi", "tarafından", "olarak",
    # Generic medical filler not specific enough for retrieval
    "hasta", "hastada", "hastaya", "hastanın", "klinik", "kliniği",
    "tani", "tanı", "tanısı", "bulgu", "bulguları", "anlamlı", "açık",
    "yapılan", "yapılması", "ilgili", "ilişkili", "akut", "kronik",
    "şikayet", "şikayetleri", "yakınma", "yakınmaları",
}


# Pre-normalize the noise list so token comparison works with ASCII-folded
# Turkish (Python's str.lower() inserts combining dots for İ → "i̇",
# which breaks both vector embedding and direct comparison).
# We intentionally translate FIRST, then lower — sut_service.normalize_turkish
# does the reverse and is left as-is for backward compatibility with the
# existing adi_normalized column.
_TR_TRANSLATE = str.maketrans("ıİöÖüÜçÇşŞğĞIİ", "iioouuccssggIi")


def _norm_tr(s: str) -> str:
    """ASCII-fold Turkish → lowercase, no combining marks."""
    return s.translate(_TR_TRANSLATE).lower()


_NOISE_TOKENS_NORM: set[str] = {_norm_tr(t) for t in _NOISE_TOKENS}


# Medical abbreviations that fall below the default min_len=4 token filter
# but are still high-signal for retrieval. Whitelist them so they survive.
# All entries pre-normalized (ASCII-fold lowercase).
_ABBREV_WHITELIST: set[str] = {
    # Hastalık kısaltmaları
    "dm", "ht", "kah", "kby", "kyf", "kvh",
    # Görüntüleme
    "bt", "mr", "us", "usg", "mri", "pet", "pat",
    # Lab kısaltmaları
    "ekg", "eko", "eeg", "tit", "iye", "kcc", "tsh",
    "ast", "alt", "bnp", "crp", "gfr", "ldl", "hdl",
    "wbc", "rbc", "hb", "hgb", "mcv", "mch", "plt",
    "egr", "fbg", "psa", "afp", "cea", "iyt", "tdm",
}


def _tokenize_significant(text: str, min_len: int = 4) -> set[str]:
    """Split text into significant tokens for vector retrieval.

    Drops common Turkish noise words ("ihtimali", "göze", "alınıyor", ...)
    that dominate embedding similarity in long phrases and obscure the
    medical signal. Output uses ASCII-folded Turkish (via normalize_turkish)
    so embedding tokenizers don't get tripped up by combining marks.

    Medical abbreviations in ``_ABBREV_WHITELIST`` (DM, HT, BT, MR, EKG,
    TSH, AST, ALT, BNP …) bypass the ``min_len`` filter — they're shorter
    than 4 chars but carry high retrieval signal.
    """
    if not text:
        return set()
    raw = text.replace("/", " ").replace("(", " ").replace(")", " ")
    tokens: set[str] = set()
    for w in raw.split():
        wc = w.strip(".,!?;:[]\"'")
        if not wc:
            continue
        wn = _norm_tr(wc)
        # Whitelisted abbreviations bypass the length check
        if wn in _ABBREV_WHITELIST:
            tokens.add(wn)
            continue
        if len(wn) < min_len:
            continue
        if wn in _NOISE_TOKENS_NORM:
            continue
        if wn.isdigit():
            continue
        tokens.add(wn)
    return tokens


def expand_with_tokens(expander: MedicalSynonymExpander, terms: Iterable[str]) -> list[str]:
    """Synonym-expand AND add per-word significant tokens.

    Architectural fix for dense-embedding noise: for any phrase like
    "MENENJİT İHTİMALİ GÖZE ALINIYOR", we end up querying vector with
    both the full phrase AND the bare significant tokens ("menenjit"),
    so the vector index can match on the medical term even when the
    full phrase carries too much noise.

    Uses BOTH ``expand_term`` (exact-key match) and ``expand`` (substring
    match) so phrases that don't exactly match a dictionary key still
    surface synonyms (e.g. "üriner sistem ultrasonu" → "üriner sistem"
    substring → its synonyms).
    """
    result: set[str] = set()
    for t in terms:
        if not t:
            continue
        t_clean = t.strip()
        if not t_clean:
            continue
        result.add(t_clean)
        # Synonyms — exact-key match (fast path)
        result.update(expander.expand_term(t_clean))
        # Synonyms — substring match (catches partial / qualified phrases)
        result.update(expander.expand(t_clean))
        # Significant per-word tokens
        result.update(_tokenize_significant(t_clean))
    return list(result)


_INSTANCE: MedicalSynonymExpander | None = None


def get_expander() -> MedicalSynonymExpander:
    """Singleton accessor — dictionary loaded on first use."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = MedicalSynonymExpander()
    return _INSTANCE
