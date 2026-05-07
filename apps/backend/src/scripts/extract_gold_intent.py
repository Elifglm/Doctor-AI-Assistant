"""Extract candidate tetkik mentions from controlled transcripts and produce
gold standard DRAFT JSON + human-reviewable Markdown for friend/doctor review.

Sources of test names (surface forms):
  - Tetkik.xlsx 231 ADI (anamnez.db.tetkik table)
  - medical_synonyms.json (lab_tests + imaging entries: halk_dili + tibbi_terim_tr)

For each transcript paragraph that contains a tetkik mention:
  - Capture the full sentence (kaynak_cumle)
  - Detect speaker from "Doktor:"/"Hasta:" prefix
  - Heuristically suggest tense + intent (regex on Turkish suffixes)
  - Write JSON for eval script + Markdown for human review

Usage: python -m apps.backend.src.scripts.extract_gold_intent
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from pathlib import Path

from docx import Document

PROJECT_ROOT = Path(__file__).resolve().parents[4]
TRANSCRIPT_DIR = Path(
    "C:/Users/Furkan/Desktop/kontrollu-veri/.manuel-transkripsiyonlar/dahiliye"
)
OUT_DIR = PROJECT_ROOT / "data" / "eval_intent"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Build search lexicon: surface_form (lower) → canonical
# ---------------------------------------------------------------------------

def _build_lexicon() -> dict[str, str]:
    """Map every known surface form to its canonical Turkish test name."""
    lexicon: dict[str, str] = {}

    # 1) 231 ADI from Tetkik.xlsx (already in anamnez.db)
    con = sqlite3.connect(str(PROJECT_ROOT / "data" / "anamnez.db"))
    for (adi,) in con.execute("SELECT DISTINCT ADI FROM tetkik"):
        canon = adi.strip()
        for token in (canon, canon.title(), canon.upper()):
            lexicon[token.lower()] = canon
    con.close()

    # 2) medical_synonyms.json — only lab_tests + imaging (tetkik domain)
    syn_path = PROJECT_ROOT / "data" / "medical_synonyms.json"
    if syn_path.exists():
        with syn_path.open(encoding="utf-8") as fp:
            syn = json.load(fp)
        for cat in ("lab_tests", "imaging"):
            for entry in syn.get(cat, []):
                canon = entry.get("tibbi_terim_tr", "").strip()
                if not canon:
                    continue
                # canonical form
                lexicon[canon.lower()] = canon
                # halk_dili (everyday Turkish synonyms)
                for surface in entry.get("halk_dili", []):
                    if isinstance(surface, str) and len(surface) >= 3:
                        lexicon[surface.lower().strip()] = canon

    # Drop ultra-short noisy keys
    lexicon = {k: v for k, v in lexicon.items() if len(k) >= 3}
    return lexicon


# ---------------------------------------------------------------------------
# Heuristic tense + intent labels (suggestion, doctor/user reviews)
# ---------------------------------------------------------------------------

_TENSE_PATTERNS = [
    # past narrative — most reliable past markers
    (r"\b\w+(mıştım|miştim|muştum|müştüm|mıştık|miştik)\b", "PAST_NARRATIVE"),
    (r"\b\w+(mış|miş|muş|müş)tı\b", "PAST_NARRATIVE"),
    (r"\b(baktırmıştım|yaptırmıştım|yaptırdım|yaptım|baktım|baktırdım)\b", "PAST_NARRATIVE"),
    (r"\b(baktınız|yaptınız|baktırdınız|yaptırdınız)\b", "PAST_NARRATIVE"),
    # optative / future — request markers
    (r"\b\w+(elim|alım|alalım|elimiz|alımız)\b", "OPTATIVE"),
    (r"\b\w+(eceğim|acağım|acam|ecem)\b", "FUTURE"),
    (r"\b(isteyelim|isteyeceğim|bakalım|bakacağım|yazalım|yazacağım)\b", "OPTATIVE"),
    # hypothetical
    (r"\b\w+sa\b", "HYPOTHETICAL"),
    # interrogative — question
    (r"\?$", "INTERROGATIVE"),
    (r"\b\w+ ?mi(\s|\?|$)", "INTERROGATIVE"),
    (r"\b\w+ ?mı(\s|\?|$)", "INTERROGATIVE"),
]


def detect_tense(sentence: str) -> str:
    s = sentence.strip().lower()
    for pat, label in _TENSE_PATTERNS:
        if re.search(pat, s):
            return label
    return "DECLARATIVE"


def suggest_intent(speaker: str, tense: str, sentence: str) -> str:
    """Heuristic intent label — to be reviewed by human."""
    s = sentence.lower()
    # Negative / refused mentions
    if any(t in s for t in ("gerek yok", "lazım değil", "olmaz", "yapmayalım")):
        return "OTHER"
    # Result discussion: numbers + test name (CRP 5, şeker 120)
    if re.search(r"\d+(\.\d+)?", s) and any(
        w in s for w in ("gelmiş", "çıkmış", "sonuç", "değer")
    ):
        return "RESULT_DISCUSS"
    # Hypothetical
    if tense == "HYPOTHETICAL":
        return "OTHER"
    # Speaker-based decisions
    if speaker == "DOCTOR":
        if tense in {"OPTATIVE", "FUTURE"}:
            return "REQUEST"
        if tense == "PAST_NARRATIVE":
            return "PAST_DONE"  # doctor recalling past
        if tense == "INTERROGATIVE":
            return "PATIENT_QUESTION"  # doctor asking ABOUT past
        return "OTHER"
    if speaker == "PATIENT":
        if tense == "PAST_NARRATIVE":
            return "PAST_DONE"
        if tense == "INTERROGATIVE":
            return "PATIENT_QUESTION"
        return "PATIENT_QUESTION"  # everything from patient is non-request
    return "OTHER"


# ---------------------------------------------------------------------------
# Mention extraction
# ---------------------------------------------------------------------------

def parse_speaker(line: str) -> tuple[str, str]:
    """Split 'Doktor: ...' / 'Hasta: ...' into (speaker, content)."""
    m = re.match(r"^(Doktor|Hasta)\s*:\s*(.+)$", line.strip(), re.IGNORECASE)
    if m:
        return m.group(1).upper().replace("DOKTOR", "DOCTOR").replace("HASTA", "PATIENT"), m.group(2).strip()
    return "OTHER", line.strip()


def find_mentions(text: str, lexicon: dict[str, str]) -> list[tuple[str, str]]:
    """Return list of (surface_form, canonical) found in text."""
    text_l = text.lower()
    found: list[tuple[str, str]] = []
    seen_canonicals: set[str] = set()
    # Sort by length desc to prefer multi-word matches first
    for surface in sorted(lexicon.keys(), key=lambda s: -len(s)):
        if surface in text_l:
            canon = lexicon[surface]
            if canon not in seen_canonicals:
                # Verify it's a "word boundary" match for short surfaces
                if len(surface) <= 5 and not re.search(rf"\b{re.escape(surface)}\b", text_l):
                    continue
                found.append((surface, canon))
                seen_canonicals.add(canon)
    return found


# ---------------------------------------------------------------------------
# Per-transcript processing
# ---------------------------------------------------------------------------

def process_transcript(path: Path, lexicon: dict[str, str]) -> dict:
    doc = Document(str(path))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    form_id = re.search(r"Kayıt\s*(\d+)", path.name)
    form_id = form_id.group(1) if form_id else path.stem

    mentions: list[dict] = []
    for idx, line in enumerate(paragraphs):
        speaker, content = parse_speaker(line)
        if speaker == "OTHER" and idx == 0:
            continue  # title line
        hits = find_mentions(content, lexicon)
        for surface, canon in hits:
            tense = detect_tense(content)
            intent = suggest_intent(speaker, tense, content)
            mentions.append(
                {
                    "line_idx": idx,
                    "kaynak_cumle": content,
                    "surface_form": surface,
                    "canonical_tetkik": canon,
                    "speaker": speaker,
                    "tense": tense,
                    "intent_etiketi_DRAFT": intent,
                    "include_DRAFT": intent == "REQUEST",
                }
            )

    return {
        "form_id": form_id,
        "transcript_file": path.name,
        "n_paragraphs": len(paragraphs),
        "n_mentions": len(mentions),
        "mentions": mentions,
    }


def write_review_md(data: dict, out_path: Path) -> None:
    fid = data["form_id"]
    n = data["n_mentions"]
    lines: list[str] = [
        f"# FORM {fid} — Gold Standard Review",
        "",
        f"**Dosya:** `{data['transcript_file']}`",
        f"**Toplam paragraf:** {data['n_paragraphs']}",
        f"**Tespit edilen tetkik mention sayisi:** {n}",
        "",
        "## Talimat",
        "",
        "Asagidaki her mention icin **Onerilen Intent** alanina bak:",
        "",
        "- **REQUEST** = doktorun simdi istedigi tetkik (rapora yazilacak)",
        "- **PAST_DONE** = gecmiste yapilmis (es gecilecek)",
        "- **PATIENT_QUESTION** = hasta sormus / kendi soylemis (es gecilecek)",
        "- **RESULT_DISCUSS** = tetkik sonucu konusuluyor (es gecilecek)",
        "- **OTHER** = hipotetik / reddedilen / diger (es gecilecek)",
        "",
        "Her satira [ ] kutucugunu **doldur** (X koy):",
        "- [X] = Onerilen etiket DOGRU",
        "- [ ] = Onerilen etiket YANLIS, alt satira dogru etiketi yaz",
        "",
        "---",
        "",
    ]
    if n == 0:
        lines.append("*(Bu transkriptte tetkik mention'i bulunamadi.)*")
    for i, m in enumerate(data["mentions"], 1):
        lines.extend(
            [
                f"## Mention {i}/{n}",
                "",
                f"- **Cumle (paragraph {m['line_idx']}):** {m['kaynak_cumle']!r}",
                f"- **Tetkik (yakalanan):** `{m['canonical_tetkik']}`  (surface: `{m['surface_form']}`)",
                f"- **Konusmaci:** {m['speaker']}",
                f"- **Zaman kipi (tahmin):** {m['tense']}",
                f"- **Onerilen Intent:** **{m['intent_etiketi_DRAFT']}**  " +
                ("(INCLUDE)" if m["include_DRAFT"] else "(EXCLUDE)"),
                "",
                "- [ ] **Doğru mu?** Yanlissa duzeltme: ___",
                "- [ ] **Tetkik adi dogru mu?** Yanlissa duzeltme: ___",
                "",
                "---",
                "",
            ]
        )
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"Loading lexicon...")
    lexicon = _build_lexicon()
    print(f"  lexicon size: {len(lexicon)} surface forms")

    files = sorted(TRANSCRIPT_DIR.glob("*.docx"))
    print(f"Found {len(files)} dahiliye transcripts")
    if not files:
        print(f"ERROR: no docx in {TRANSCRIPT_DIR}", file=sys.stderr)
        sys.exit(1)

    summary = {"total_mentions": 0, "transcripts": []}

    for f in files:
        data = process_transcript(f, lexicon)
        # Write DRAFT JSON (machine-readable for eval script)
        json_path = OUT_DIR / f"gold_{data['form_id']}_DRAFT.json"
        json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # Write REVIEW Markdown (human-readable for friend+doctor)
        md_path = OUT_DIR / f"REVIEW_{data['form_id']}.md"
        write_review_md(data, md_path)

        request_count = sum(
            1 for m in data["mentions"] if m["include_DRAFT"]
        )
        summary["total_mentions"] += data["n_mentions"]
        summary["transcripts"].append(
            {
                "form_id": data["form_id"],
                "n_paragraphs": data["n_paragraphs"],
                "n_mentions": data["n_mentions"],
                "n_request_DRAFT": request_count,
            }
        )
        print(
            f"  FORM {data['form_id']:>5}: {data['n_paragraphs']} para, "
            f"{data['n_mentions']:>3} mention ({request_count} REQUEST draft)"
        )

    summary_path = OUT_DIR / "gold_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nSummary: {summary['total_mentions']} mentions across {len(files)} transcripts")
    print(f"Written:")
    print(f"  - {OUT_DIR}/gold_<form>_DRAFT.json   (eval script input)")
    print(f"  - {OUT_DIR}/REVIEW_<form>.md         (human review form)")
    print(f"  - {summary_path}                     (overview)")


if __name__ == "__main__":
    main()
