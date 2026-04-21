"""De-identification service for Turkish medical ASR transcripts.

Strips PHI (personally identifiable information) from text using four
sequential detection layers: exact-match, fuzzy-match, regex, and NER.
Replacements use opaque tokens (e.g. hasta_1) which are proven to
preserve LLM output quality better than bracketed label tokens.

IMPORTANT: This module never logs PHI values — only entity counts.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Category constants (opaque prefix used in placeholder tokens)
# ---------------------------------------------------------------------------

CAT_PATIENT_NAME = "hasta"
CAT_DOCTOR_NAME = "doktor"
CAT_TC_KIMLIK = "tc"
CAT_PHONE = "telefon"
CAT_EMAIL = "email"
CAT_PERSON = "kisi"
CAT_ADDRESS = "adres"
CAT_INSURANCE = "sigorta"

# Regex pattern that matches any placeholder produced by this service
_PLACEHOLDER_PATTERN = re.compile(
    r"\b(hasta|doktor|tc|telefon|email|kisi|adres|sigorta)_\d+\b"
)

# Turkish words that double as common personal names — exempt from fuzzy masking only.
_MEDICAL_TERM_WHITELIST: frozenset[str] = frozenset({
    "ates", "ateş",      # fever
    "nur",                # light (ophthalmology)
    "can",                # life/soul
    "deniz",              # sea (rarely medical but common name)
    "ilhan",              # not medical but common false positive
    "bulut",              # cloud (rarely medical)
    "yildiz", "yıldız",  # star
    "gunes", "güneş",    # sun
    "bahar",              # spring (season)
    "dogan", "doğan",    # born
    "selin", "sel",       # flood
    "ege",                # Aegean
    "baris", "barış",    # peace
    "umut",               # hope
    "basak", "başak",    # spike/ear (botany)
    "defne",              # laurel
    "ceren",              # gazelle
    "derya",              # sea/ocean
    "pinar", "pınar",    # spring/source
    "yagmur", "yağmur",  # rain
})

# ---------------------------------------------------------------------------
# Turkish-aware helpers
# ---------------------------------------------------------------------------


def _turkish_lower(text: str) -> str:
    """Case-fold text using Turkish locale rules.

    Python's built-in str.lower() maps 'I' -> 'i' which is incorrect for
    Turkish ('I' should become 'ı' and 'İ' should become 'i').
    """
    return text.replace("İ", "i").replace("I", "ı").lower()


# ---------------------------------------------------------------------------
# TC Kimlik checksum validation (same algorithm as patient schema)
# ---------------------------------------------------------------------------


def _valid_tc_kimlik(value: str) -> bool:
    """Return True if the 11-digit string passes the TC Kimlik checksum."""
    if len(value) != 11 or not value.isdigit():
        return False
    digits = [int(c) for c in value]
    if digits[0] == 0:
        return False
    d10_check = (
        (digits[0] + digits[2] + digits[4] + digits[6] + digits[8]) * 7
        - (digits[1] + digits[3] + digits[5] + digits[7])
    ) % 10
    if d10_check != digits[9]:
        return False
    d11_check = sum(digits[:10]) % 10
    return d11_check == digits[10]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PHIContext:
    """Known PII values extracted from the active session/patient record.

    All fields are plain strings; empty string means "not available".
    """

    patient_first_name: str = ""
    patient_last_name: str = ""
    patient_tc_kimlik: str = ""
    patient_phone: str = ""
    patient_email: str = ""
    patient_birth_date: str = ""
    patient_address: str = ""
    patient_city: str = ""
    patient_emergency_contact_name: str = ""
    patient_emergency_contact_phone: str = ""
    patient_insurance_number: str = ""
    doctor_display_name: str = ""
    doctor_username: str = ""
    session_patient_name: str = ""


@dataclass(frozen=True)
class PHIEntity:
    """A single detected PHI span."""

    original: str
    category: str
    start: int
    end: int
    detection_layer: str


@dataclass
class PlaceholderMap:
    """Bidirectional mapping between opaque placeholder tokens and their
    original PHI values.

    __repr__ intentionally shows only the count of entries, never the
    actual values, to prevent PHI from leaking into logs.
    """

    _placeholder_to_original: dict[str, str] = field(default_factory=dict)
    _original_to_placeholder: dict[str, str] = field(default_factory=dict)
    _counters: dict[str, int] = field(default_factory=dict)

    def add(self, original: str, category: str) -> str:
        """Register *original* and return its opaque placeholder token.

        If the same original value was already registered the existing
        placeholder is returned unchanged (idempotent).
        """
        if original in self._original_to_placeholder:
            return self._original_to_placeholder[original]

        self._counters[category] = self._counters.get(category, 0) + 1
        placeholder = f"{category}_{self._counters[category]}"

        self._placeholder_to_original[placeholder] = original
        self._original_to_placeholder[original] = placeholder
        return placeholder

    def get_original(self, placeholder: str) -> str | None:
        """Look up the PHI value for a given placeholder token."""
        return self._placeholder_to_original.get(placeholder)

    def get_placeholder(self, original: str) -> str | None:
        """Look up the placeholder token for a given PHI value."""
        return self._original_to_placeholder.get(original)

    @property
    def all_placeholders(self) -> dict[str, str]:
        """Return a copy of the {placeholder: original} mapping."""
        return dict(self._placeholder_to_original)

    def __repr__(self) -> str:
        # Never expose the actual PHI values in repr / log output.
        return f"PlaceholderMap(entries={len(self._placeholder_to_original)})"


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------


class DeIdentificationService:
    """Four-layer PHI de-identification for Turkish medical transcripts.

    Layers run in order:
      1. Exact match  — known values from PHIContext
      2. Fuzzy match  — typo-tolerant name matching via rapidfuzz
      3. Regex        — TC Kimlik, phone numbers, e-mail addresses
      4. NER          — GLiNER PII model (lazy-loaded, GPU-optional)
    """

    # NER labels and their mapping to our category constants
    _NER_LABELS: list[str] = ["person", "phone number", "email", "address"]
    _NER_LABEL_TO_CAT: dict[str, str] = {
        "person": CAT_PERSON,
        "phone number": CAT_PHONE,
        "email": CAT_EMAIL,
        "address": CAT_ADDRESS,
    }

    # Pre-compiled regex patterns
    _RE_TC = re.compile(r"\b[1-9]\d{10}\b")
    _RE_PHONE = re.compile(
        r"\b(?:\+90|0090|0)?\s*5\d{2}[\s\-.]?\d{3}[\s\-.]?\d{2}[\s\-.]?\d{2}\b"
    )
    _RE_EMAIL = re.compile(
        r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"
    )

    def __init__(
        self,
        *,
        enabled: bool = True,
        fuzzy_threshold: float = 0.85,
        ner_model_name: str = "knowledgator/gliner-pii-base-v1.0",
        use_ner_layer: bool = True,
    ) -> None:
        self._enabled = enabled
        self._fuzzy_threshold = fuzzy_threshold
        self._ner_model_name = ner_model_name
        self._use_ner_layer = use_ner_layer

        # Lazy-loaded NER model; _ner_lock prevents concurrent init races
        self._ner_model: Any = None
        self._ner_lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def deidentify(
        self, text: str, context: PHIContext
    ) -> tuple[str, PlaceholderMap]:
        """Detect and replace PHI in *text* using context-aware layers.

        Returns the sanitised text and the placeholder map needed for
        later re-identification.  Only entity counts are logged.
        """
        if not self._enabled:
            return text, PlaceholderMap()

        pmap = PlaceholderMap()

        # Layer 1 — exact match
        exact_entities = self._detect_exact(text, context, pmap)
        logger.info(
            "deid layer=exact entities_found=%d", len(exact_entities)
        )

        # Layer 2 — fuzzy match
        fuzzy_entities = self._detect_fuzzy(text, context, pmap)
        logger.info(
            "deid layer=fuzzy entities_found=%d", len(fuzzy_entities)
        )

        # Layer 3 — regex
        regex_entities = self._detect_regex(text, pmap)
        logger.info(
            "deid layer=regex entities_found=%d", len(regex_entities)
        )

        # Layer 4 — NER (optional, graceful degradation on failure)
        ner_entities: list[PHIEntity] = []
        if self._use_ner_layer:
            ner_entities = await self._detect_ner(text, pmap)
            logger.info(
                "deid layer=ner entities_found=%d", len(ner_entities)
            )

        clean_text = self._apply_replacements(text, pmap)
        total = len(exact_entities) + len(fuzzy_entities) + len(regex_entities) + len(ner_entities)
        logger.info("deid complete total_entities=%d", total)
        return clean_text, pmap

    def reidentify(self, text: str, pmap: PlaceholderMap) -> str:
        """Restore original PHI values from placeholder tokens.

        Replacements are applied longest-first to avoid partial matches
        (e.g. ``hasta_10`` must be replaced before ``hasta_1``).
        """
        all_ph = pmap.all_placeholders
        # Sort by placeholder length descending so longer tokens win
        for placeholder in sorted(all_ph, key=len, reverse=True):
            original = all_ph[placeholder]
            text = text.replace(placeholder, original)
        return text

    def reidentify_sections(
        self, sections: list[dict[str, Any]], pmap: PlaceholderMap
    ) -> list[dict[str, Any]]:
        """Re-identify the ``content`` field of each anamnesis section."""
        result: list[dict[str, Any]] = []
        for section in sections:
            updated = dict(section)
            if "content" in updated and isinstance(updated["content"], str):
                updated["content"] = self.reidentify(updated["content"], pmap)
            result.append(updated)
        return result

    def check_residual_placeholders(self, text: str) -> list[str]:
        """Return any placeholder tokens still present in *text*.

        Used to detect incomplete re-identification before sending output
        to external systems.
        """
        return _PLACEHOLDER_PATTERN.findall(text)

    # ------------------------------------------------------------------
    # Layer 1: Exact match
    # ------------------------------------------------------------------

    def _detect_exact(
        self, text: str, context: PHIContext, pmap: PlaceholderMap
    ) -> list[PHIEntity]:
        """Find known PHI values via case-insensitive exact string search."""
        # Build candidate list: (value, category)
        # Full name must appear before individual parts (longest-first principle)
        candidates: list[tuple[str, str]] = []

        full_name = " ".join(
            part
            for part in (context.patient_first_name, context.patient_last_name)
            if part
        ).strip()
        if full_name:
            candidates.append((full_name, CAT_PATIENT_NAME))
        if context.patient_first_name:
            candidates.append((context.patient_first_name, CAT_PATIENT_NAME))
        if context.patient_last_name:
            candidates.append((context.patient_last_name, CAT_PATIENT_NAME))
        if context.session_patient_name:
            candidates.append((context.session_patient_name, CAT_PATIENT_NAME))
        if context.doctor_display_name:
            candidates.append((context.doctor_display_name, CAT_DOCTOR_NAME))
        if context.patient_tc_kimlik:
            candidates.append((context.patient_tc_kimlik, CAT_TC_KIMLIK))
        if context.patient_phone:
            candidates.append((context.patient_phone, CAT_PHONE))
        if context.patient_email:
            candidates.append((context.patient_email, CAT_EMAIL))
        if context.patient_emergency_contact_name:
            candidates.append(
                (context.patient_emergency_contact_name, CAT_PERSON)
            )
        if context.patient_emergency_contact_phone:
            candidates.append(
                (context.patient_emergency_contact_phone, CAT_PHONE)
            )
        if context.patient_insurance_number:
            candidates.append((context.patient_insurance_number, CAT_INSURANCE))

        entities: list[PHIEntity] = []
        text_lower = _turkish_lower(text)

        for value, category in candidates:
            if len(value) < 2:
                continue
            value_lower = _turkish_lower(value)
            start = 0
            while True:
                idx = text_lower.find(value_lower, start)
                if idx == -1:
                    break
                original_slice = text[idx : idx + len(value)]
                placeholder = pmap.add(original_slice, category)  # noqa: F841
                entities.append(
                    PHIEntity(
                        original=original_slice,
                        category=category,
                        start=idx,
                        end=idx + len(value),
                        detection_layer="exact",
                    )
                )
                start = idx + len(value)

        return entities

    # ------------------------------------------------------------------
    # Layer 2: Fuzzy match
    # ------------------------------------------------------------------

    def _detect_fuzzy(
        self, text: str, context: PHIContext, pmap: PlaceholderMap
    ) -> list[PHIEntity]:
        """Catch near-miss name variants using token-level fuzzy similarity."""
        try:
            from rapidfuzz.fuzz import ratio as fuzz_ratio  # type: ignore[import-untyped]
        except ImportError:
            import difflib

            def fuzz_ratio(a: str, b: str) -> float:  # type: ignore[misc]
                return difflib.SequenceMatcher(None, a, b).ratio() * 100

        # Known name parts to check against (min 3 chars)
        name_parts: list[tuple[str, str]] = []
        for part in (context.patient_first_name, context.patient_last_name):
            if len(part) >= 3:
                name_parts.append((part, CAT_PATIENT_NAME))
        if len(context.doctor_display_name) >= 3:
            name_parts.append((context.doctor_display_name, CAT_DOCTOR_NAME))
        if len(context.patient_emergency_contact_name) >= 3:
            name_parts.append(
                (context.patient_emergency_contact_name, CAT_PERSON)
            )

        if not name_parts:
            return []

        # Tokenise text on whitespace/punctuation
        token_pattern = re.compile(r"[^\s,;:.!?()\[\]\"']+")
        entities: list[PHIEntity] = []

        for match in token_pattern.finditer(text):
            word = match.group()
            word_lower = _turkish_lower(word)

            # Skip very short tokens and tokens already caught by exact match
            if len(word) < 3 or pmap.get_placeholder(word) is not None:
                # Also check case-insensitive already-caught
                already = any(
                    _turkish_lower(orig) == word_lower
                    for orig in pmap.all_placeholders.values()
                )
                if already or len(word) < 3:
                    continue

            # Skip tokens that are known medical vocabulary to avoid false positives.
            if word_lower in _MEDICAL_TERM_WHITELIST:
                continue

            for known_value, category in name_parts:
                known_lower = _turkish_lower(known_value)
                score = fuzz_ratio(word_lower, known_lower)
                # rapidfuzz returns 0-100; normalise to 0-1 for comparison
                normalised = score / 100.0
                if normalised >= self._fuzzy_threshold:
                    placeholder = pmap.add(word, category)  # noqa: F841
                    entities.append(
                        PHIEntity(
                            original=word,
                            category=category,
                            start=match.start(),
                            end=match.end(),
                            detection_layer="fuzzy",
                        )
                    )
                    break  # one category per token is sufficient

        return entities

    # ------------------------------------------------------------------
    # Layer 3: Regex
    # ------------------------------------------------------------------

    def _detect_regex(
        self, text: str, pmap: PlaceholderMap
    ) -> list[PHIEntity]:
        """Detect TC Kimlik numbers, Turkish phone numbers, and e-mail addresses."""
        entities: list[PHIEntity] = []

        # TC Kimlik
        for m in self._RE_TC.finditer(text):
            value = m.group()
            if not _valid_tc_kimlik(value):
                continue
            if pmap.get_placeholder(value) is not None:
                continue
            pmap.add(value, CAT_TC_KIMLIK)
            entities.append(
                PHIEntity(
                    original=value,
                    category=CAT_TC_KIMLIK,
                    start=m.start(),
                    end=m.end(),
                    detection_layer="regex",
                )
            )

        # Phone numbers
        for m in self._RE_PHONE.finditer(text):
            value = m.group()
            if pmap.get_placeholder(value) is not None:
                continue
            pmap.add(value, CAT_PHONE)
            entities.append(
                PHIEntity(
                    original=value,
                    category=CAT_PHONE,
                    start=m.start(),
                    end=m.end(),
                    detection_layer="regex",
                )
            )

        # Email addresses
        for m in self._RE_EMAIL.finditer(text):
            value = m.group()
            if pmap.get_placeholder(value) is not None:
                continue
            pmap.add(value, CAT_EMAIL)
            entities.append(
                PHIEntity(
                    original=value,
                    category=CAT_EMAIL,
                    start=m.start(),
                    end=m.end(),
                    detection_layer="regex",
                )
            )

        # NOTE: Dates are intentionally NOT masked (product decision).

        return entities

    # ------------------------------------------------------------------
    # Layer 4: NER (lazy-loaded GLiNER PII model)
    # ------------------------------------------------------------------

    async def _load_ner_model(self) -> Any:
        """Load the GLiNER PII model inside asyncio.to_thread."""
        from gliner import GLiNER  # type: ignore[import-untyped]

        return GLiNER.from_pretrained(self._ner_model_name)

    async def _ensure_ner_model(self) -> bool:
        """Lazily initialise the NER model with double-checked locking.

        Returns True when the model is ready, False if loading failed.
        """
        if self._ner_model is not None:
            return True
        async with self._ner_lock:
            if self._ner_model is not None:
                return True
            try:
                logger.info(
                    "deid loading NER model model=%s", self._ner_model_name
                )
                self._ner_model = await asyncio.to_thread(
                    # Run the blocking pretrained-load off the event loop
                    lambda: __import__("gliner", fromlist=["GLiNER"]).GLiNER.from_pretrained(  # type: ignore[attr-defined]
                        self._ner_model_name
                    )
                )
                logger.info("deid NER model loaded")
                return True
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning(
                    "deid NER model load failed — layer disabled. error=%s",
                    type(exc).__name__,
                )
                return False

    async def _detect_ner(
        self, text: str, pmap: PlaceholderMap
    ) -> list[PHIEntity]:
        """Run GLiNER PII inference and register new entities."""
        ready = await self._ensure_ner_model()
        if not ready:
            return []

        try:
            raw: list[dict[str, Any]] = await asyncio.to_thread(
                self._ner_model.predict_entities,
                text,
                self._NER_LABELS,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(
                "deid NER inference failed error=%s", type(exc).__name__
            )
            return []

        entities: list[PHIEntity] = []
        for ent in raw:
            ner_label: str = ent.get("label", "")
            category = self._NER_LABEL_TO_CAT.get(ner_label)
            if category is None:
                continue

            value: str = ent.get("text", "")
            if not value or pmap.get_placeholder(value) is not None:
                continue

            # Skip values already handled by earlier layers (case-insensitive)
            already_caught = any(
                _turkish_lower(orig) == _turkish_lower(value)
                for orig in pmap.all_placeholders.values()
            )
            if already_caught:
                continue

            pmap.add(value, category)
            entities.append(
                PHIEntity(
                    original=value,
                    category=category,
                    start=ent.get("start", 0),
                    end=ent.get("end", 0),
                    detection_layer="ner",
                )
            )

        return entities

    # ------------------------------------------------------------------
    # Replacement application
    # ------------------------------------------------------------------

    def _apply_replacements(self, text: str, pmap: PlaceholderMap) -> str:
        """Replace all registered PHI values with their placeholder tokens.

        Sorted by original-value length descending to prevent shorter
        substrings from matching inside longer ones first.
        """
        all_ph = pmap.all_placeholders  # {placeholder: original}

        # Sort entries by length of original value, longest first
        sorted_entries = sorted(
            all_ph.items(), key=lambda kv: len(kv[1]), reverse=True
        )

        for placeholder, original in sorted_entries:
            pattern = re.compile(re.escape(original), re.IGNORECASE)
            text = pattern.sub(placeholder, text)

        return text
