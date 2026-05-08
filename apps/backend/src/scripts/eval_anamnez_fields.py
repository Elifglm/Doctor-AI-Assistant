"""Eval anamnez batch generation against gold field-by-field.

Reads:
  - data/eval_synthetic/transcript_<form_id>.txt (input)
  - data/eval_synthetic/gold_<form_id>_anamnez.json (gold 26 dahiliye fields)

Runs:
  - ReportGenerator.generate_report(segments, brans="dahiliye") — single LLM
    batch call producing all 26 fields. Compare each generated field to gold.

Per-field metrics (chosen by field type):
  - Free-text fields (yakinma, oykü, muayene, tedavi, ...):
      * exact_match (case-insensitive)
      * token-level F1 (unigram bag-of-words)
      * BLEU-1 (smoothed)
  - Numeric fields (sistolik, diyastolik, nabiz, ates, kilo, boy, so2):
      * tolerance match (±5% or ±2 absolute, whichever larger)
  - Categorical / short fields (sigara, alkol, alerji):
      * substring/normalized match
  - "BELIRTILMEDI" handling: agreement on emptiness counts as exact_match

Aggregates:
  - per_field across all forms (mean F1, mean exact_match)
  - macro: average across all 26 fields
  - micro: pooled token counts

Output: data/eval_anamnez/run_<ts>_<label>.json

Usage:
    python -m apps.backend.src.scripts.eval_anamnez_fields --label haiku_strict
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("eval_anamnez")

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "eval_synthetic"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data" / "eval_anamnez"
DEFAULT_FORM_IDS = ["S001", "S002", "S003", "S004", "S005"]

# Field-type classification (dahiliye 26 fields)
NUMERIC_FIELDS = {"sistolik", "diyastolik", "nabiz", "ates", "kilo", "boy", "so2", "agri_skalasi"}
SHORT_CATEGORICAL = {"sigara", "alkol", "alerji"}
LIST_FIELDS = {"icd10_list", "sut_tetkik_list"}
EMPTY_MARKERS = {"belirtilmedi", "belirtilmedi.", "", "-", "yok"}


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _is_empty(s: str) -> bool:
    return _norm(s) in EMPTY_MARKERS


def _tokenize(s: str) -> list[str]:
    """Lowercase + simple Turkish-friendly tokenizer (alnum + hyphen)."""
    return re.findall(r"[a-z0-9çğışöü]+", s.lower())


def _token_f1(sys_text: str, gold_text: str) -> float:
    sys_tokens = Counter(_tokenize(sys_text))
    gold_tokens = Counter(_tokenize(gold_text))
    if not sys_tokens and not gold_tokens:
        return 1.0
    if not sys_tokens or not gold_tokens:
        return 0.0
    common = sys_tokens & gold_tokens
    overlap = sum(common.values())
    if overlap == 0:
        return 0.0
    p = overlap / sum(sys_tokens.values())
    r = overlap / sum(gold_tokens.values())
    return 2 * p * r / (p + r)


def _bleu1(sys_text: str, gold_text: str) -> float:
    """Smoothed BLEU-1 (unigram precision with brevity penalty)."""
    sys_tokens = _tokenize(sys_text)
    gold_tokens = _tokenize(gold_text)
    if not sys_tokens or not gold_tokens:
        return 0.0
    sys_count = Counter(sys_tokens)
    gold_count = Counter(gold_tokens)
    overlap = sum((sys_count & gold_count).values())
    p = (overlap + 1) / (len(sys_tokens) + 1)  # add-1 smoothing
    bp = 1.0 if len(sys_tokens) >= len(gold_tokens) else \
        pow(2.71828, 1 - len(gold_tokens) / max(len(sys_tokens), 1))
    return p * bp


def _numeric_match(sys_val: str, gold_val: str) -> bool:
    """Tolerance-based numeric comparison. ±5% or ±2 absolute, whichever larger."""
    if _is_empty(sys_val) and _is_empty(gold_val):
        return True
    if _is_empty(sys_val) or _is_empty(gold_val):
        return False
    sys_num = re.findall(r"[\d.]+", sys_val)
    gold_num = re.findall(r"[\d.]+", gold_val)
    if not sys_num or not gold_num:
        return False
    try:
        s = float(sys_num[0])
        g = float(gold_num[0])
    except ValueError:
        return False
    tolerance = max(2.0, abs(g) * 0.05)
    return abs(s - g) <= tolerance


def _list_overlap_f1(sys_val: str, gold_val: str) -> float:
    """For list fields (comma-separated)."""
    sys_items = {x.strip().lower() for x in sys_val.split(",") if x.strip()}
    gold_items = {x.strip().lower() for x in gold_val.split(",") if x.strip()}
    if not sys_items and not gold_items:
        return 1.0
    if not sys_items or not gold_items:
        return 0.0
    overlap = len(sys_items & gold_items)
    if overlap == 0:
        return 0.0
    p = overlap / len(sys_items)
    r = overlap / len(gold_items)
    return 2 * p * r / (p + r)


def _eval_field(key: str, sys_val: str, gold_val: str) -> dict:
    """Compute metrics for a single field, type-aware."""
    sys_val = sys_val or ""
    gold_val = gold_val or ""

    # Empty agreement
    if _is_empty(sys_val) and _is_empty(gold_val):
        return {"key": key, "type": "empty_agree", "exact_match": 1.0,
                "token_f1": 1.0, "bleu1": 1.0, "score": 1.0}

    if key in NUMERIC_FIELDS:
        match = _numeric_match(sys_val, gold_val)
        return {"key": key, "type": "numeric", "exact_match": float(match),
                "token_f1": float(match), "bleu1": float(match), "score": float(match)}

    if key in LIST_FIELDS:
        f1 = _list_overlap_f1(sys_val, gold_val)
        return {"key": key, "type": "list", "exact_match": float(_norm(sys_val) == _norm(gold_val)),
                "token_f1": f1, "bleu1": f1, "score": f1}

    # Free text / short categorical
    em = float(_norm(sys_val) == _norm(gold_val))
    f1 = _token_f1(sys_val, gold_val)
    bleu = _bleu1(sys_val, gold_val)
    return {"key": key, "type": "text", "exact_match": em, "token_f1": f1,
            "bleu1": bleu, "score": f1}


def _load_gold(data_dir: Path, form_id: str) -> dict[str, str]:
    path = data_dir / f"gold_{form_id}_anamnez.json"
    obj = json.loads(path.read_text(encoding="utf-8"))
    return obj.get("fields", {})


def _read_transcript(data_dir: Path, form_id: str) -> str:
    return (data_dir / f"transcript_{form_id}.txt").read_text(encoding="utf-8")


async def init_pipeline():
    from config.settings import AppSettings
    from apps.backend.src.services.llm_factory import create_llm_service
    from apps.backend.src.services.ner_service import NERService
    from apps.backend.src.services.icd10_service import ICD10Service
    from apps.backend.src.services.icd10_vector_service import ICD10VectorService
    from apps.backend.src.services.icd10_suggestion_service import ICD10SuggestionService
    from apps.backend.src.services.sut_service import SUTService
    from apps.backend.src.services.sut_vector_service import SUTVectorService
    from apps.backend.src.services.sut_suggestion_service import SUTSuggestionService
    from apps.backend.src.services.report_generator import ReportGenerator

    settings = AppSettings()
    llm = create_llm_service(settings)
    try:
        await llm.initialize()
    except Exception:
        logger.warning("LLM init failed")

    ner = NERService()
    icd_svc, icd_vec = ICD10Service(), ICD10VectorService()
    sut_svc, sut_vec = SUTService(), SUTVectorService()
    try:
        await icd_vec.initialize()
        await sut_vec.initialize()
    except Exception:
        logger.warning("Vector init failed")

    icd_suggestion = ICD10SuggestionService(
        llm=llm, icd10_service=icd_svc, vector_service=icd_vec, ner_service=ner
    )
    sut_suggestion = SUTSuggestionService(
        llm=llm, sut_service=sut_svc, vector_service=sut_vec, ner_service=ner
    )
    return ReportGenerator(
        llm=llm, ner=ner, icd10=icd_suggestion, sut_tetkik=sut_suggestion
    )


async def evaluate_form(report_gen, data_dir: Path, form_id: str) -> dict:
    transcript = _read_transcript(data_dir, form_id)
    gold = _load_gold(data_dir, form_id)

    # ReportGenerator.generate_report expects segments in transcription format
    segments = [{
        "start_time": 0.0, "end_time": 1.0,
        "text": transcript, "speaker": ""
    }]

    report = await report_gen.generate_report(segments, brans="dahiliye")
    sys_sections = {s["key"]: s.get("content", "") for s in report.get("sections", [])}

    # Score each gold field
    field_results = []
    for key, gold_val in gold.items():
        sys_val = sys_sections.get(key, "")
        m = _eval_field(key, sys_val, gold_val)
        m["sys_value"] = sys_val[:120]
        m["gold_value"] = gold_val[:120]
        field_results.append(m)

    macro = {
        "exact_match": round(sum(f["exact_match"] for f in field_results) / max(len(field_results), 1), 3),
        "token_f1": round(sum(f["token_f1"] for f in field_results) / max(len(field_results), 1), 3),
        "bleu1": round(sum(f["bleu1"] for f in field_results) / max(len(field_results), 1), 3),
    }
    return {
        "form_id": form_id,
        "n_fields": len(field_results),
        "macro": macro,
        "fields": field_results,
    }


async def main(label: str, data_dir: Path, form_ids: list[str]) -> None:
    logger.info("=== eval_anamnez label=%s ===", label)
    DEFAULT_OUT_DIR.mkdir(parents=True, exist_ok=True)

    report_gen = await init_pipeline()
    logger.info("pipeline initialized")

    results = []
    for fid in form_ids:
        logger.info("--- FORM %s ---", fid)
        try:
            r = await evaluate_form(report_gen, data_dir, fid)
        except Exception:
            logger.exception("FORM %s eval FAILED", fid)
            continue
        m = r["macro"]
        logger.info(
            "  macro: exact=%.3f token_f1=%.3f bleu1=%.3f",
            m["exact_match"], m["token_f1"], m["bleu1"],
        )
        results.append(r)

    # Pool per-field across forms
    field_aggregates: dict[str, dict] = {}
    for r in results:
        for f in r["fields"]:
            key = f["key"]
            agg = field_aggregates.setdefault(key, {"em": [], "f1": [], "bleu": [], "type": f["type"]})
            agg["em"].append(f["exact_match"])
            agg["f1"].append(f["token_f1"])
            agg["bleu"].append(f["bleu1"])

    per_field_summary = {
        k: {
            "type": v["type"],
            "n": len(v["em"]),
            "mean_exact_match": round(sum(v["em"]) / max(len(v["em"]), 1), 3),
            "mean_token_f1": round(sum(v["f1"]) / max(len(v["f1"]), 1), 3),
            "mean_bleu1": round(sum(v["bleu"]) / max(len(v["bleu"]), 1), 3),
        }
        for k, v in field_aggregates.items()
    }

    macro_overall = {
        "exact_match": round(
            sum(s["mean_exact_match"] for s in per_field_summary.values()) / max(len(per_field_summary), 1), 3),
        "token_f1": round(
            sum(s["mean_token_f1"] for s in per_field_summary.values()) / max(len(per_field_summary), 1), 3),
        "bleu1": round(
            sum(s["mean_bleu1"] for s in per_field_summary.values()) / max(len(per_field_summary), 1), 3),
    }

    summary = {
        "label": label,
        "n_forms": len(results),
        "n_fields_per_form": 26,
        "macro_overall": macro_overall,
    }
    logger.info("=== SUMMARY ===\n%s", json.dumps(summary, indent=2, ensure_ascii=False))
    logger.info("Per-field:\n%s", json.dumps(per_field_summary, indent=2, ensure_ascii=False))

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = DEFAULT_OUT_DIR / f"run_{ts}_{label}.json"
    out_path.write_text(
        json.dumps({
            "summary": summary,
            "per_field": per_field_summary,
            "per_form": results,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("written: %s", out_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", type=str, default="anamnez_run")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--form-ids", type=str, default=None)
    args = parser.parse_args()

    data_dir = args.data_dir if args.data_dir else DEFAULT_DATA_DIR
    form_ids = (
        [s.strip() for s in args.form_ids.split(",") if s.strip()]
        if args.form_ids else DEFAULT_FORM_IDS
    )

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main(args.label, data_dir, form_ids))
