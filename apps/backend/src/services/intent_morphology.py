"""Turkish morphological intent pre-classifier — LLM-free.

Pure regex/suffix-based classifier for verb tense and speaker → intent.
Built as the runtime-NLP counterpart to the LLM-based intent disambiguation:
the LLM still does the final selection, but this module provides a
deterministic ground-truth signal for the same task without any model call.

Rules encoded:
- Verb suffix detection: -mIş/-dI (PAST), -AcAk (FUTURE), -AlIm (OPTATIVE),
  -sIn (PASSIVE_IMPERATIVE), -sA (HYPOTHETICAL), -mI/-? (INTERROGATIVE)
- List-inheritance: when a sentence has "list head verb : items, items, ...",
  the items inherit the head verb's tense
- Speaker detection from "Doktor:" / "Hasta:" prefix

Usage:
    from apps.backend.src.services.intent_morphology import predict_intent

    pred = predict_intent(
        sentence="Tahliller isteyeceğiz: TSH, T3, T4, hemogram",
        surface_form="t3",
        line_prefix="Doktor:",
    )
    # pred.intent == Intent.REQUEST
    # pred.tense == Tense.FUTURE
    # pred.rule_fired == "list_inheritance"
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Tense(str, Enum):
    PAST_NARRATIVE = "PAST_NARRATIVE"
    OPTATIVE = "OPTATIVE"
    FUTURE = "FUTURE"
    IMPERATIVE_PASSIVE = "IMPERATIVE_PASSIVE"
    IMPERATIVE_ACTIVE = "IMPERATIVE_ACTIVE"
    HYPOTHETICAL = "HYPOTHETICAL"
    INTERROGATIVE = "INTERROGATIVE"
    DECLARATIVE = "DECLARATIVE"
    UNKNOWN = "UNKNOWN"


class Speaker(str, Enum):
    DOCTOR = "DOCTOR"
    PATIENT = "PATIENT"
    UNKNOWN = "UNKNOWN"


class Intent(str, Enum):
    REQUEST = "REQUEST"
    PAST_DONE = "PAST_DONE"
    PATIENT_QUESTION = "PATIENT_QUESTION"
    RESULT_DISCUSS = "RESULT_DISCUSS"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


@dataclass
class IntentPrediction:
    speaker: Speaker
    tense: Tense
    intent: Intent
    confidence: float  # heuristic, 0.0-1.0
    rule_fired: str    # debugging trace
    head_verb: str = ""  # captured verb when list-inheritance fires


# ---------------------------------------------------------------------------
# Suffix patterns — Turkish verb morphology
# Vowel harmony: a/e (back/front), ı/i/u/ü (high)
# ---------------------------------------------------------------------------

# -mIştI / -mIş / -dI / -dIk / -dIn / -dIlAr → past
# Patterns ordered: most specific first
PAST_PAT = re.compile(
    r"\b\w*?(?:m[ıiuü]şt[ıiuü]m?|m[ıiuü]ş(?:s[ıiuü]n[ıi]z)?|d[ıiuü](?:m|n|k|n[ıi]z|l[ae]r)?|t[ıiuü](?:m|n|k)?)\b",
    re.IGNORECASE,
)

# -AlIm 1.plural optative ("isteyelim", "bakalım", "alalım", "edelim")
OPTATIVE_PAT = re.compile(
    r"\b\w*?(?:y[ae]l[ıi]m|al[ıi]m|el[ıi]m)\b",
    re.IGNORECASE,
)

# -AcAk future ("isteyeceğim", "isteyeceğiz", "yapacağız", "bakacağız")
FUTURE_PAT = re.compile(
    r"\b\w*?(?:y[ae]ceğ[ıi](?:m|z)|y[ae]cağ[ıi](?:m|z)|[ae]cağ[ıi](?:m|z)|[ae]ceğ[ıi](?:m|z)|y[ae]cak|[ae]cak|y[ae]cek|[ae]cek)\w*\b",
    re.IGNORECASE,
)

# -sIn 3.singular passive imperative ("bakılsın", "yapılsın", "ölçülsün", "istensin")
# Pattern: stem + ıl/il/ul/ül + sın/sin/sun/sün
IMPERATIVE_PASSIVE_PAT = re.compile(
    r"\b\w+?[ıiuü]l(?:s[ıiuü]n)\b|\b\w+?ns[ıi]n\b|\b\w+?[ıi]ls[ıi]n\b",
    re.IGNORECASE,
)

# -sA conditional/hypothetical ("yüksekse", "olursa", "gerekirse", "çıkarsa")
HYPOTHETICAL_PAT = re.compile(
    r"\b(?:gerek[ıi]rse|olursa|olsayd[ıi]|olmazsa|\w+?[ıiuü]rse|\w+?[ae]rse|\w+?ssa|\w+?[ıi]se)\b",
    re.IGNORECASE,
)

# Interrogative: question mark or "mI" particle
INTERROGATIVE_PAT = re.compile(
    r"(?:\?|\bm[ıiuü](?:\b|y[ıi]m|s[ıi]n|y[ıi]z|d[ıi]r))",
    re.IGNORECASE,
)

# Speaker prefixes
DOCTOR_PREFIX = re.compile(r"^\s*(?:doktor|dr\.?|doctor|hekim)\s*[:\-]", re.IGNORECASE)
PATIENT_PREFIX = re.compile(r"^\s*(?:hasta|patient)\s*[:\-]", re.IGNORECASE)

# List context: head verb followed by ":" and comma-separated items
# Common heads: "tahliller isteyeceğiz:", "şunları yapalım:", etc.
# Capture the head verb so its tense can be classified
LIST_HEAD_PAT = re.compile(
    r"(\w+(?:y[ae]ceğ[ıi]z|y[ae]cağ[ıi]z|[ae]ceğ[ıi]z|[ae]cağ[ıi]z|y[ae]ceğ[ıi]m|y[ae]cağ[ıi]m|y[ae]l[ıi]m|al[ıi]m|el[ıi]m|[ıi]ls[ıi]n|s[ıi]n))[^:]{0,40}:\s*[\w].*?,",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_speaker(text: str) -> Speaker:
    """Detect speaker from a line prefix. Returns UNKNOWN if no marker."""
    if not text:
        return Speaker.UNKNOWN
    if DOCTOR_PREFIX.search(text):
        return Speaker.DOCTOR
    if PATIENT_PREFIX.search(text):
        return Speaker.PATIENT
    return Speaker.UNKNOWN


def classify_tense(verb_or_sentence: str) -> Tense:
    """Classify the tense of a single verb or short sentence.

    Order matters — most specific patterns checked first to avoid
    over-matching by generic ones (e.g. PAST -dI suffix is short).
    """
    s = verb_or_sentence.strip()
    if not s:
        return Tense.UNKNOWN

    # Interrogative trumps everything (sentence-level marker)
    if INTERROGATIVE_PAT.search(s):
        return Tense.INTERROGATIVE

    # Hypothetical (-sA) often shadows future / past — check early
    if HYPOTHETICAL_PAT.search(s):
        return Tense.HYPOTHETICAL

    # Future (-AcAk) — long suffix, low ambiguity
    if FUTURE_PAT.search(s):
        return Tense.FUTURE

    # Optative 1.pl (-AlIm)
    if OPTATIVE_PAT.search(s):
        return Tense.OPTATIVE

    # Passive imperative (-sIn after passive marker)
    if IMPERATIVE_PASSIVE_PAT.search(s):
        return Tense.IMPERATIVE_PASSIVE

    # Past (-mIş, -dI) — broad, check last
    if PAST_PAT.search(s):
        return Tense.PAST_NARRATIVE

    return Tense.DECLARATIVE


def find_list_head_verb(sentence: str, surface_form: str) -> str:
    """If `surface_form` appears in a list (after a colon), return the head verb.

    Returns "" if no list context detected.
    """
    if not sentence or ":" not in sentence:
        return ""

    head_match = LIST_HEAD_PAT.search(sentence)
    if not head_match:
        return ""

    # Confirm the surface_form appears AFTER the colon (i.e. is a list item)
    colon_pos = sentence.find(":", head_match.start())
    if colon_pos < 0:
        return ""
    after_colon = sentence[colon_pos + 1 :].lower()
    if surface_form.lower() not in after_colon:
        return ""

    return head_match.group(1)


def derive_intent(speaker: Speaker, tense: Tense) -> Intent:
    """Speaker + tense → intent label (rule-based)."""
    request_tenses = {
        Tense.FUTURE,
        Tense.OPTATIVE,
        Tense.IMPERATIVE_PASSIVE,
        Tense.IMPERATIVE_ACTIVE,
    }
    if tense == Tense.PAST_NARRATIVE:
        return Intent.PAST_DONE
    if tense == Tense.HYPOTHETICAL:
        return Intent.OTHER
    if tense == Tense.INTERROGATIVE:
        if speaker == Speaker.PATIENT:
            return Intent.PATIENT_QUESTION
        if speaker == Speaker.DOCTOR:
            # Doctor asking patient a question (e.g. "Şeker var mı?") → not a request
            return Intent.PATIENT_QUESTION
        return Intent.PATIENT_QUESTION
    if tense in request_tenses:
        if speaker == Speaker.DOCTOR:
            return Intent.REQUEST
        # Patient using future tense ("baktıracağım") = past intent / self-statement
        return Intent.OTHER
    if tense == Tense.DECLARATIVE:
        # Cannot decide from morphology alone
        return Intent.UNKNOWN
    return Intent.UNKNOWN


def predict_intent(
    sentence: str,
    surface_form: str = "",
    line_prefix: str = "",
) -> IntentPrediction:
    """Full pipeline: speaker + tense + list-context → intent prediction.

    Args:
        sentence: the full sentence containing the tetkik mention
        surface_form: the tetkik mention text (for list-context check)
        line_prefix: optional explicit speaker line prefix (e.g. "Doktor:")
    """
    speaker = detect_speaker(line_prefix) if line_prefix else detect_speaker(sentence)

    # 1) List-inheritance check first
    if surface_form:
        head_verb = find_list_head_verb(sentence, surface_form)
        if head_verb:
            head_tense = classify_tense(head_verb)
            intent = derive_intent(speaker, head_tense)
            return IntentPrediction(
                speaker=speaker,
                tense=head_tense,
                intent=intent,
                confidence=0.90,
                rule_fired="list_inheritance",
                head_verb=head_verb,
            )

    # 2) Sentence-level tense classification
    tense = classify_tense(sentence)
    intent = derive_intent(speaker, tense)
    confidence = 0.80 if tense != Tense.DECLARATIVE else 0.50
    return IntentPrediction(
        speaker=speaker,
        tense=tense,
        intent=intent,
        confidence=confidence,
        rule_fired=f"sentence_tense:{tense.value}",
    )


# ---------------------------------------------------------------------------
# Smoke test cases — run with `python -m apps.backend.src.services.intent_morphology`
# ---------------------------------------------------------------------------


_TEST_CASES = [
    # (sentence, surface, expected_intent, expected_tense, line_prefix)
    (
        "Tahliller isteyeceğiz: TSH, T3, T4, anti-TPO, hemogram, açlık kan şekeri",
        "t3", Intent.REQUEST, Tense.FUTURE, "Doktor:",
    ),
    (
        "AKŞT tekrar bi 8 saat aç kaldıktan sonra açlık kan şekerine bakılsın",
        "açlık kan şekeri", Intent.REQUEST, Tense.IMPERATIVE_PASSIVE, "Doktor:",
    ),
    (
        "Açlık kan şekeri, HbA1c ve lipid profili isteyeceğiz",
        "açlık kan şekeri", Intent.REQUEST, Tense.FUTURE, "Doktor:",
    ),
    (
        "Şimdi rutin tahliller isteyeceğiz: kan şekeri, böbrek, hemogram, TSH",
        "tsh", Intent.REQUEST, Tense.FUTURE, "Doktor:",
    ),
    (
        "Şimdilik ilaç vermiyoruz, takip edelim. Gerekirse 24 saatlik tansiyon holteri takarız.",
        "holter", Intent.OTHER, Tense.HYPOTHETICAL, "Doktor:",
    ),
    (
        "Daha önce rutin tahlillerime baktırmak istemiştim",
        "tahlil", Intent.PAST_DONE, Tense.PAST_NARRATIVE, "Hasta:",
    ),
    (
        "Şeker, hipertansiyon, kolesterol var mı?",
        "kolesterol", Intent.PATIENT_QUESTION, Tense.INTERROGATIVE, "Doktor:",
    ),
    (
        "Sizden akciğer grafisi, EKG ve troponin isteyeceğim.",
        "ekg", Intent.REQUEST, Tense.FUTURE, "Doktor:",
    ),
    (
        "Tetkik sonuçlarınıza baktım; tiroid normal, hemoglobin on iki nokta bir.",
        "hemoglobin", Intent.PAST_DONE, Tense.PAST_NARRATIVE, "Doktor:",
    ),
    (
        "EKG, troponin bir de akciğer testiyle gelirsiniz bize geçmiş olsun.",
        "ekg", Intent.OTHER, Tense.HYPOTHETICAL, "Doktor:",
    ),
]


def _run_smoke_tests() -> None:
    """Print pass/fail for each test case."""
    n_pass = 0
    for i, (sent, surface, exp_intent, exp_tense, prefix) in enumerate(_TEST_CASES, 1):
        pred = predict_intent(sent, surface, prefix)
        intent_ok = pred.intent == exp_intent
        tense_ok = pred.tense == exp_tense
        status = "PASS" if (intent_ok and tense_ok) else "FAIL"
        if intent_ok and tense_ok:
            n_pass += 1
        print(
            f"[{status}] case {i}: intent={pred.intent.value}/{exp_intent.value} "
            f"tense={pred.tense.value}/{exp_tense.value} "
            f"rule={pred.rule_fired} head={pred.head_verb!r}"
        )
        if not (intent_ok and tense_ok):
            print(f"        sent: {sent[:80]}")
    print(f"\n{n_pass}/{len(_TEST_CASES)} passed")


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    _run_smoke_tests()
