"""Tests for DeIdentificationService.

All tests are self-contained: no external API calls, no database access,
and no real model downloads.  GLiNER (Layer 4 NER) is mocked via
unittest.mock.patch so the test suite works without a GPU or network.

Valid TC Kimlik used throughout: 10000000146
Checksum verification:
  digits = [1,0,0,0,0,0,0,0,1,4,6]
  d10 = ((1+0+0+0+1)*7 - (0+0+0+0)) % 10 = (14) % 10 = 4  ✓
  d11 = sum(digits[:10]) % 10 = 6 % 10 = 6  ✓
"""

from __future__ import annotations

import asyncio
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
from apps.backend.src.services.deid_service import (
    CAT_PATIENT_NAME,
    CAT_PHONE,
    CAT_TC_KIMLIK,
    DeIdentificationService,
    PHIContext,
    PHIEntity,
    PlaceholderMap,
    _turkish_lower,
    _valid_tc_kimlik,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_TC = "10000000146"
INVALID_TC_BAD_CHECKSUM = "10000000147"  # last digit wrong
INVALID_TC_STARTS_ZERO = "01234567890"


def _run(coro):
    """Execute a coroutine synchronously (avoids pytest-asyncio requirement)."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _svc(**kwargs) -> DeIdentificationService:
    """Return a service instance with NER disabled (no model download)."""
    return DeIdentificationService(use_ner_layer=False, **kwargs)


# ===========================================================================
# _turkish_lower
# ===========================================================================


class TestTurkishLower:
    def test_dotted_I_becomes_lowercase_i(self):
        assert _turkish_lower("İSTANBUL") == "istanbul"

    def test_dotless_I_becomes_dotless_lowercase(self):
        assert _turkish_lower("IĞDIR") == "ığdır"

    def test_regular_ascii_unaffected(self):
        assert _turkish_lower("AHMET") == "ahmet"

    def test_mixed_case(self):
        assert _turkish_lower("İbrahim") == "ibrahim"

    def test_empty_string(self):
        assert _turkish_lower("") == ""


# ===========================================================================
# _valid_tc_kimlik
# ===========================================================================


class TestValidTcKimlik:
    def test_known_valid_tc(self):
        assert _valid_tc_kimlik(VALID_TC) is True

    def test_invalid_bad_checksum(self):
        assert _valid_tc_kimlik(INVALID_TC_BAD_CHECKSUM) is False

    def test_invalid_starts_with_zero(self):
        assert _valid_tc_kimlik(INVALID_TC_STARTS_ZERO) is False

    def test_wrong_length_short(self):
        assert _valid_tc_kimlik("1234567") is False

    def test_wrong_length_long(self):
        assert _valid_tc_kimlik("123456789012") is False

    def test_non_digit_characters(self):
        assert _valid_tc_kimlik("1000000014X") is False


# ===========================================================================
# PlaceholderMap
# ===========================================================================


class TestPlaceholderMap:
    def test_add_returns_opaque_token(self):
        pmap = PlaceholderMap()
        ph = pmap.add("Ahmet", CAT_PATIENT_NAME)
        assert ph == "hasta_1"

    def test_same_value_returns_same_placeholder(self):
        pmap = PlaceholderMap()
        ph1 = pmap.add("Ahmet", CAT_PATIENT_NAME)
        ph2 = pmap.add("Ahmet", CAT_PATIENT_NAME)
        assert ph1 == ph2

    def test_different_values_get_sequential_ids(self):
        pmap = PlaceholderMap()
        ph1 = pmap.add("Ahmet", CAT_PATIENT_NAME)
        ph2 = pmap.add("Yilmaz", CAT_PATIENT_NAME)
        assert ph1 == "hasta_1"
        assert ph2 == "hasta_2"

    def test_get_original_round_trip(self):
        pmap = PlaceholderMap()
        ph = pmap.add("Ahmet", CAT_PATIENT_NAME)
        assert pmap.get_original(ph) == "Ahmet"

    def test_get_placeholder_round_trip(self):
        pmap = PlaceholderMap()
        ph = pmap.add("Ahmet", CAT_PATIENT_NAME)
        assert pmap.get_placeholder("Ahmet") == ph

    def test_get_original_missing_returns_none(self):
        pmap = PlaceholderMap()
        assert pmap.get_original("hasta_99") is None

    def test_get_placeholder_missing_returns_none(self):
        pmap = PlaceholderMap()
        assert pmap.get_placeholder("Nonexistent") is None

    def test_repr_shows_count_not_values(self):
        pmap = PlaceholderMap()
        pmap.add("Ahmet", CAT_PATIENT_NAME)
        pmap.add("05321234567", CAT_PHONE)
        r = repr(pmap)
        assert "Ahmet" not in r
        assert "05321234567" not in r
        assert "entries=2" in r

    def test_repr_empty(self):
        pmap = PlaceholderMap()
        assert "entries=0" in repr(pmap)

    def test_all_placeholders_copy(self):
        pmap = PlaceholderMap()
        pmap.add("Ahmet", CAT_PATIENT_NAME)
        copy = pmap.all_placeholders
        # Mutating the copy must not affect the map
        copy["hasta_1"] = "MUTATED"
        assert pmap.get_original("hasta_1") == "Ahmet"

    def test_placeholder_format_is_opaque(self):
        """Placeholder must look like 'category_N', not '[CATEGORY_1]'."""
        pmap = PlaceholderMap()
        ph = pmap.add("Ahmet", CAT_PATIENT_NAME)
        assert ph.startswith("hasta_")
        assert "[" not in ph
        assert "]" not in ph


# ===========================================================================
# Layer 1 — Exact match
# ===========================================================================


class TestLayer1ExactMatch:
    def test_full_name_detected(self):
        svc = _svc()
        ctx = PHIContext(patient_first_name="Ahmet", patient_last_name="Yilmaz")
        text = "Doktor: Ahmet Yilmaz nasil hissediyorsunuz?"
        masked, pmap = _run(svc.deidentify(text, ctx))
        assert "Ahmet" not in masked
        assert "Yilmaz" not in masked

    def test_full_name_replaced_as_single_unit(self):
        """'Ahmet Yilmaz' should produce ONE placeholder, not two."""
        svc = _svc()
        ctx = PHIContext(patient_first_name="Ahmet", patient_last_name="Yilmaz")
        text = "Hasta Ahmet Yilmaz muayeneye geldi."
        masked, pmap = _run(svc.deidentify(text, ctx))
        # The full name should map to hasta_1 (longest first)
        full_ph = pmap.get_placeholder("Ahmet Yilmaz")
        assert full_ph is not None
        assert full_ph in masked

    def test_tc_kimlik_detected(self):
        svc = _svc()
        ctx = PHIContext(patient_tc_kimlik=VALID_TC)
        text = f"TC kimlik numarasi: {VALID_TC}"
        masked, pmap = _run(svc.deidentify(text, ctx))
        assert VALID_TC not in masked
        assert pmap.get_placeholder(VALID_TC) is not None

    def test_phone_from_context_detected(self):
        svc = _svc()
        ctx = PHIContext(patient_phone="05321234567")
        text = "Telefon numaraniz 05321234567 mi?"
        masked, pmap = _run(svc.deidentify(text, ctx))
        assert "05321234567" not in masked

    def test_case_insensitive_matching(self):
        svc = _svc()
        ctx = PHIContext(patient_first_name="Ahmet")
        text = "AHMET bugün muayeneye geldi."
        masked, _ = _run(svc.deidentify(text, ctx))
        assert "AHMET" not in masked

    def test_short_values_skipped(self):
        """Single-char context values must not be processed."""
        svc = _svc()
        ctx = PHIContext(patient_first_name="A")  # too short
        text = "A harfi var burada."
        masked, pmap = _run(svc.deidentify(text, ctx))
        # No PHI registered — text unchanged
        assert masked == text
        assert len(pmap.all_placeholders) == 0

    def test_turkish_name_ibrahimcase_insensitive(self):
        svc = _svc()
        ctx = PHIContext(patient_first_name="İbrahim")
        text = "IBRAHIM geldi."
        masked, _ = _run(svc.deidentify(text, ctx))
        assert "IBRAHIM" not in masked


# ===========================================================================
# Layer 2 — Fuzzy match
# ===========================================================================


class TestLayer2FuzzyMatch:
    def test_typo_first_name_matched(self):
        """'Ahned' should match 'Ahmet' above the default 85% threshold."""
        # Use a lower threshold so difflib also catches this
        svc = DeIdentificationService(use_ner_layer=False, fuzzy_threshold=0.80)
        ctx = PHIContext(patient_first_name="Ahmet")
        text = "Hasta Ahned ağrıdan şikayetci."
        masked, pmap = _run(svc.deidentify(text, ctx))
        # "Ahned" should be registered as PHI
        assert pmap.get_placeholder("Ahned") is not None

    def test_typo_last_name_matched(self):
        svc = DeIdentificationService(use_ner_layer=False, fuzzy_threshold=0.80)
        ctx = PHIContext(patient_last_name="Yilmaz")
        text = "Bay Yilmas bugün geldi."
        masked, pmap = _run(svc.deidentify(text, ctx))
        assert pmap.get_placeholder("Yilmas") is not None

    def test_already_exact_matched_tokens_skipped(self):
        """Tokens caught by exact match must not be double-counted."""
        svc = DeIdentificationService(use_ner_layer=False, fuzzy_threshold=0.80)
        ctx = PHIContext(patient_first_name="Ahmet")
        text = "Ahmet burada."
        _, pmap = _run(svc.deidentify(text, ctx))
        # "Ahmet" should appear exactly once in the map values
        occurrences = list(pmap.all_placeholders.values()).count("Ahmet")
        assert occurrences == 1

    def test_short_word_skipped_by_fuzzy(self):
        """Words shorter than 3 chars must not be evaluated by fuzzy layer."""
        svc = DeIdentificationService(use_ner_layer=False, fuzzy_threshold=0.80)
        ctx = PHIContext(patient_first_name="Ali")  # 3 chars, name_parts OK
        text = "Al bunu ver."
        masked, pmap = _run(svc.deidentify(text, ctx))
        # "Al" (2 chars) must not be fuzzily matched
        assert pmap.get_placeholder("Al") is None


# ===========================================================================
# Layer 3 — Regex
# ===========================================================================


class TestLayer3Regex:
    def test_valid_tc_kimlik_masked(self):
        svc = _svc()
        ctx = PHIContext()
        text = f"Numara: {VALID_TC} kayıtlı."
        masked, pmap = _run(svc.deidentify(text, ctx))
        assert VALID_TC not in masked
        assert pmap.get_placeholder(VALID_TC) is not None

    def test_invalid_tc_not_masked(self):
        svc = _svc()
        ctx = PHIContext()
        text = f"Yanlis numara: {INVALID_TC_BAD_CHECKSUM}"
        masked, pmap = _run(svc.deidentify(text, ctx))
        assert INVALID_TC_BAD_CHECKSUM in masked
        assert pmap.get_placeholder(INVALID_TC_BAD_CHECKSUM) is None

    def test_phone_number_detected(self):
        svc = _svc()
        ctx = PHIContext()
        text = "Arayin: 05321234567"
        masked, pmap = _run(svc.deidentify(text, ctx))
        assert "05321234567" not in masked

    def test_email_detected(self):
        svc = _svc()
        ctx = PHIContext()
        text = "E-posta: test@example.com adresine gonderin."
        masked, pmap = _run(svc.deidentify(text, ctx))
        assert "test@example.com" not in masked
        assert pmap.get_placeholder("test@example.com") is not None

    def test_dates_not_detected(self):
        """Dates are intentionally excluded from regex detection."""
        svc = _svc()
        ctx = PHIContext()
        text = "Randevu tarihi: 12.03.2024"
        masked, pmap = _run(svc.deidentify(text, ctx))
        # Dates must remain untouched
        assert "12.03.2024" in masked


# ===========================================================================
# Layer 4 — NER (mocked GLiNER)
# ===========================================================================


def _make_fake_gliner_module(entities_to_return: list[dict]) -> types.ModuleType:
    """Return a minimal fake 'gliner' module whose GLiNER class returns a
    mock model that yields *entities_to_return* from predict_entities."""
    fake_model = MagicMock()
    fake_model.predict_entities.return_value = entities_to_return

    FakeGLiNER = MagicMock()
    FakeGLiNER.from_pretrained.return_value = fake_model

    gliner_mod = types.ModuleType("gliner")
    gliner_mod.GLiNER = FakeGLiNER  # type: ignore[attr-defined]
    return gliner_mod


class TestLayer4NER:
    def test_ner_person_entity_masked(self):
        """GLiNER returns 'Fatma' as a person → must become kisi_1."""
        entities = [{"text": "Fatma", "label": "person", "start": 10, "end": 15}]
        fake_gliner = _make_fake_gliner_module(entities)

        svc = DeIdentificationService(use_ner_layer=True)
        ctx = PHIContext()
        text = "Annesinin Fatma oldugunu soyledi."

        with patch.dict(sys.modules, {"gliner": fake_gliner}):
            masked, pmap = _run(svc.deidentify(text, ctx))

        assert "Fatma" not in masked
        assert pmap.get_placeholder("Fatma") == "kisi_1"

    def test_ner_skips_entities_already_caught(self):
        """If Ahmet was caught by exact match, NER must not re-register it."""
        entities = [{"text": "Ahmet", "label": "person", "start": 0, "end": 5}]
        fake_gliner = _make_fake_gliner_module(entities)

        svc = DeIdentificationService(use_ner_layer=True)
        ctx = PHIContext(patient_first_name="Ahmet")
        text = "Ahmet ağrı şikayetiyle geldi."

        with patch.dict(sys.modules, {"gliner": fake_gliner}):
            masked, pmap = _run(svc.deidentify(text, ctx))

        # "Ahmet" must be in the map exactly once
        values = list(pmap.all_placeholders.values())
        assert values.count("Ahmet") == 1

    def test_ner_graceful_failure_when_model_unavailable(self):
        """If GLiNER import fails the service must degrade gracefully."""
        # Hide gliner from sys.modules so import raises ImportError
        original = sys.modules.pop("gliner", None)
        try:
            svc = DeIdentificationService(use_ner_layer=True)
            ctx = PHIContext()
            text = "Normal metin burada."
            # Should not raise
            masked, pmap = _run(svc.deidentify(text, ctx))
            assert masked == text
        finally:
            if original is not None:
                sys.modules["gliner"] = original

    def test_ner_disabled_skips_layer(self):
        """use_ner_layer=False must never touch GLiNER."""
        svc = DeIdentificationService(use_ner_layer=False)
        ctx = PHIContext()
        text = "Hasta geldi."
        # Patch would raise if called — verifies it is NOT called
        with patch(
            "apps.backend.src.services.deid_service.DeIdentificationService._ensure_ner_model",
            new_callable=AsyncMock,
            side_effect=AssertionError("NER must not be called"),
        ):
            masked, _ = _run(svc.deidentify(text, ctx))
        assert masked == text


# ===========================================================================
# Integration — full roundtrip
# ===========================================================================


class TestFullRoundtrip:
    def test_deidentify_then_reidentify(self):
        svc = _svc()
        ctx = PHIContext(
            patient_first_name="Ahmet",
            patient_last_name="Yilmaz",
            patient_tc_kimlik=VALID_TC,
            patient_phone="05321234567",
        )
        original = (
            "Doktor: Ahmet Yilmaz 05321234567 numaran dogru mu? "
            "Hasta: Evet doktor bey."
        )
        masked, pmap = _run(svc.deidentify(original, ctx))

        # Real values must not appear in masked text
        assert "Ahmet" not in masked
        assert "Yilmaz" not in masked
        assert "05321234567" not in masked

        # Round-trip must restore original
        restored = svc.reidentify(masked, pmap)
        assert restored == original

    def test_placeholder_format_opaque(self):
        """Placeholders must be category_N, never bracketed labels."""
        svc = _svc()
        ctx = PHIContext(patient_first_name="Zeynep")
        text = "Hasta Zeynep burada."
        masked, pmap = _run(svc.deidentify(text, ctx))
        for ph in pmap.all_placeholders:
            assert ph.startswith(("hasta_", "doktor_", "tc_", "telefon_", "email_", "kisi_", "adres_", "sigorta_"))
            assert "[" not in ph

    def test_ner_entity_also_round_trips(self):
        """Entity discovered by NER (mocked) must survive a full roundtrip."""
        entities = [{"text": "Fatma", "label": "person", "start": 27, "end": 32}]
        fake_gliner = _make_fake_gliner_module(entities)

        svc = DeIdentificationService(use_ner_layer=True)
        ctx = PHIContext(
            patient_first_name="Ahmet",
            patient_tc_kimlik=VALID_TC,
            patient_phone="05321234567",
        )
        original = (
            f"Doktor: Ahmet {VALID_TC} 05321234567 dogru mu? "
            "Hasta: Evet, annem Fatma da arasin."
        )

        with patch.dict(sys.modules, {"gliner": fake_gliner}):
            masked, pmap = _run(svc.deidentify(original, ctx))

        assert "Fatma" not in masked
        restored = svc.reidentify(masked, pmap)
        assert "Fatma" in restored


# ===========================================================================
# Disabled mode
# ===========================================================================


class TestDisabledMode:
    def test_disabled_returns_text_unchanged(self):
        svc = DeIdentificationService(enabled=False)
        ctx = PHIContext(patient_first_name="Ahmet", patient_tc_kimlik=VALID_TC)
        text = f"Hasta Ahmet TC:{VALID_TC}"
        masked, pmap = _run(svc.deidentify(text, ctx))
        assert masked == text

    def test_disabled_placeholder_map_empty(self):
        svc = DeIdentificationService(enabled=False)
        ctx = PHIContext(patient_first_name="Ahmet")
        _, pmap = _run(svc.deidentify("Ahmet geldi.", ctx))
        assert len(pmap.all_placeholders) == 0


# ===========================================================================
# check_residual_placeholders
# ===========================================================================


class TestCheckResidualPlaceholders:
    def test_finds_leftover_placeholder(self):
        svc = _svc()
        text = "hastanin hasta_1 bilgisi eksik."
        residuals = svc.check_residual_placeholders(text)
        assert "hasta_1" in residuals

    def test_no_residuals_in_clean_text(self):
        svc = _svc()
        text = "normal metin burada herhangi bir yer tutucu yok."
        residuals = svc.check_residual_placeholders(text)
        assert residuals == []

    def test_all_category_prefixes_detected(self):
        svc = _svc()
        text = "doktor_1 tc_2 telefon_3 email_4 kisi_5 adres_6 sigorta_7"
        residuals = svc.check_residual_placeholders(text)
        assert len(residuals) == 7

    def test_partial_prefix_not_matched(self):
        """Words like 'hasta' alone (without _N suffix) must not match."""
        svc = _svc()
        text = "Hasta muayeneye geldi."
        residuals = svc.check_residual_placeholders(text)
        assert residuals == []


# ===========================================================================
# reidentify_sections
# ===========================================================================


class TestReidentifySections:
    def test_content_field_restored(self):
        svc = _svc()
        pmap = PlaceholderMap()
        pmap.add("Ahmet Yilmaz", CAT_PATIENT_NAME)  # → hasta_1

        sections = [{"title": "Muayene", "content": "hasta_1 muayeneye geldi."}]
        result = svc.reidentify_sections(sections, pmap)
        assert result[0]["content"] == "Ahmet Yilmaz muayeneye geldi."

    def test_non_content_fields_untouched(self):
        svc = _svc()
        pmap = PlaceholderMap()
        pmap.add("Ahmet", CAT_PATIENT_NAME)  # → hasta_1

        sections = [{"title": "hasta_1", "content": "hasta_1 muayene"}]
        result = svc.reidentify_sections(sections, pmap)
        # title must NOT be modified, only content
        assert result[0]["title"] == "hasta_1"
        assert result[0]["content"] == "Ahmet muayene"

    def test_missing_content_field_skipped(self):
        svc = _svc()
        pmap = PlaceholderMap()
        sections = [{"title": "Bolum"}]  # no 'content' key
        result = svc.reidentify_sections(sections, pmap)
        assert result == [{"title": "Bolum"}]

    def test_multiple_sections(self):
        svc = _svc()
        pmap = PlaceholderMap()
        pmap.add("Zeynep", CAT_PATIENT_NAME)  # → hasta_1

        sections = [
            {"content": "hasta_1 basvurdu."},
            {"content": "hasta_1 iyilesti."},
        ]
        result = svc.reidentify_sections(sections, pmap)
        assert result[0]["content"] == "Zeynep basvurdu."
        assert result[1]["content"] == "Zeynep iyilesti."


# ===========================================================================
# reidentify — longest-first ordering
# ===========================================================================


class TestReidentifyLongestFirst:
    def test_longer_placeholder_wins_over_prefix(self):
        """hasta_10 must be restored before hasta_1 to prevent partial match."""
        svc = _svc()
        pmap = PlaceholderMap()
        # Force specific counter values via direct internal manipulation
        # (bypasses add() to control counter order for this edge-case test)
        pmap._counters["hasta"] = 10
        pmap._placeholder_to_original["hasta_10"] = "Zeynep Kaya"
        pmap._original_to_placeholder["Zeynep Kaya"] = "hasta_10"
        pmap._counters["hasta"] = 1
        pmap._placeholder_to_original["hasta_1"] = "Ahmet"
        pmap._original_to_placeholder["Ahmet"] = "hasta_1"

        text = "hasta_10 ve hasta_1 geldi."
        restored = svc.reidentify(text, pmap)
        assert "Zeynep Kaya" in restored
        assert "Ahmet" in restored
        # Check no leftover garbled token like "Ahmetkaya" or "Ahmet0"
        assert "hasta_" not in restored
