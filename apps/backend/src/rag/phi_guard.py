"""Defense-in-depth PHI masker for free-text strings.

Used in two places:
  1. build_anamnez_vectors.py — mask before embedding (1st layer, persistent)
  2. AnamnezRAGService.query_similar_cases — mask retrieval results (2nd layer)

Reuses the regex patterns + TC checksum validator from
``services.deid_service`` so we don't duplicate detection logic. Replaces
matches with **typed placeholders** (``[MASKED_TC]``, ``[MASKED_PHONE]``,
``[MASKED_EMAIL]``) so the downstream LLM understands what kind of value
was redacted.

Why a separate module instead of extending ``deid_service``: that service
is entity-aware (PHIContext, GLiNER NER, asyncio.Lock, PlaceholderMap) and
designed for live transcription. For bulk anonymous corpus text we just
need stateless regex sweeps; coupling here would be overkill.
"""

from __future__ import annotations

from apps.backend.src.services.deid_service import (
    DeIdentificationService,
    _valid_tc_kimlik,
)

_RE_TC = DeIdentificationService._RE_TC
_RE_PHONE = DeIdentificationService._RE_PHONE
_RE_EMAIL = DeIdentificationService._RE_EMAIL

_PLACEHOLDER_TC = "[MASKED_TC]"
_PLACEHOLDER_PHONE = "[MASKED_PHONE]"
_PLACEHOLDER_EMAIL = "[MASKED_EMAIL]"


def _replace_tc(match) -> str:
    """Only replace if the 11-digit number passes the TC checksum."""
    value = match.group(0)
    return _PLACEHOLDER_TC if _valid_tc_kimlik(value) else value


def mask_phi(text: str) -> str:
    """Mask TC kimlik / phone / email occurrences with typed placeholders.

    Stateless. Safe to call on already-masked text (idempotent — placeholders
    don't match the patterns). Returns the input unchanged when no match.
    """
    if not text:
        return text
    text = _RE_TC.sub(_replace_tc, text)
    text = _RE_PHONE.sub(_PLACEHOLDER_PHONE, text)
    text = _RE_EMAIL.sub(_PLACEHOLDER_EMAIL, text)
    return text


def mask_phi_count(text: str) -> tuple[str, dict[str, int]]:
    """Mask + return per-category match counts (for logging/audit).

    Counts only **valid** TC numbers (passed checksum), every phone/email
    pattern hit. Useful in build/eval scripts to track residual PHI.
    """
    if not text:
        return text, {"tc": 0, "phone": 0, "email": 0}

    counts = {"tc": 0, "phone": 0, "email": 0}

    def _tc_sub(m):
        if _valid_tc_kimlik(m.group(0)):
            counts["tc"] += 1
            return _PLACEHOLDER_TC
        return m.group(0)

    text = _RE_TC.sub(_tc_sub, text)

    def _phone_sub(m):
        counts["phone"] += 1
        return _PLACEHOLDER_PHONE

    text = _RE_PHONE.sub(_phone_sub, text)

    def _email_sub(m):
        counts["email"] += 1
        return _PLACEHOLDER_EMAIL

    text = _RE_EMAIL.sub(_email_sub, text)
    return text, counts
