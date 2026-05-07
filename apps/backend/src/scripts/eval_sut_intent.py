"""Eval SUT tetkik intent disambiguation against user-reviewed gold standard.

Reads:
  - data/eval_intent/gold_<form>.json (user-reviewed REQUEST mentions)
  - controlled-veri transcripts (.docx) from desktop folder

Runs:
  - SUTSuggestionService.suggest(transcript, brans="dahiliye") for each form
  - Extracts system output codes + intent labels

Computes (code-level, treating each test as a unique entity):
  - precision = |system_request ∩ gold_request| / |system_request|
  - recall    = |system_request ∩ gold_request| / |gold_request|
  - F1
  - intent_accuracy: when system mention matches a gold mention, % correct intent

Output:
  - data/eval_intent/run_<ts>_<label>.json (per-form + summary)

Usage:
    # Baseline:
    python -m apps.backend.src.scripts.eval_sut_intent --label baseline_v2
    # After changes:
    python -m apps.backend.src.scripts.eval_sut_intent --label v3_katman1
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from docx import Document
from rapidfuzz import fuzz

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("eval_intent")

PROJECT_ROOT = Path(__file__).resolve().parents[4]
EVAL_DIR = PROJECT_ROOT / "data" / "eval_intent"
TRANSCRIPT_DIR = Path(
    "C:/Users/Furkan/Desktop/kontrollu-veri/.manuel-transkripsiyonlar/dahiliye"
)
FORM_IDS = ["105", "106", "108", "109", "110", "111"]

# Code-name fuzzy match threshold for matching system output to gold canonicals
CANONICAL_MATCH_THRESHOLD = 75


def _read_transcript(form_id: str) -> str:
    """Read .docx for a form_id, return as raw 'Doktor: ... Hasta: ...' text."""
    paths = list(TRANSCRIPT_DIR.glob(f"Kayıt {form_id}*.docx"))
    if not paths:
        raise FileNotFoundError(f"No transcript .docx for FORM {form_id} in {TRANSCRIPT_DIR}")
    doc = Document(str(paths[0]))
    lines = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n".join(lines)


def _load_gold(form_id: str) -> dict:
    path = EVAL_DIR / f"gold_{form_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _gold_request_canonicals(gold: dict) -> list[str]:
    """Return list of canonical_tetkik strings for every REQUEST gold mention."""
    return [
        m["canonical_tetkik"] for m in gold["mentions"]
        if m.get("include") and m.get("intent_etiketi") == "REQUEST"
    ]


def _dedup_canonicals(canonicals: list[str]) -> list[str]:
    """Code-level dedup: collapse duplicate canonical names."""
    seen: set[str] = set()
    out: list[str] = []
    for c in canonicals:
        key = c.strip().lower()
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def _fuzzy_overlap(
    system_names: list[str], gold_names: list[str]
) -> tuple[set[int], set[int], list[dict]]:
    """Greedy fuzzy match between system canonical names and gold canonicals.

    Returns:
        matched_system_idx, matched_gold_idx, pair_log
    """
    matched_sys: set[int] = set()
    matched_gold: set[int] = set()
    pairs: list[dict] = []

    for si, sname in enumerate(system_names):
        best_gi, best_score = None, 0
        for gi, gname in enumerate(gold_names):
            if gi in matched_gold:
                continue
            sc = int(fuzz.token_set_ratio(sname.lower(), gname.lower()))
            if sc > best_score:
                best_score = sc
                best_gi = gi
        if best_score >= CANONICAL_MATCH_THRESHOLD and best_gi is not None:
            matched_sys.add(si)
            matched_gold.add(best_gi)
            pairs.append({
                "system": sname,
                "gold": gold_names[best_gi],
                "score": best_score,
            })
    return matched_sys, matched_gold, pairs


async def init_pipeline():
    from config.settings import AppSettings
    from apps.backend.src.services.llm_factory import create_llm_service
    from apps.backend.src.services.ner_service import NERService
    from apps.backend.src.services.sut_service import SUTService
    from apps.backend.src.services.sut_vector_service import SUTVectorService
    from apps.backend.src.services.sut_suggestion_service import SUTSuggestionService

    settings = AppSettings()
    llm = create_llm_service(settings)
    try:
        await llm.initialize()
    except Exception:
        logger.warning("LLM init failed (provider=%s)", llm.provider_name)

    ner = NERService()
    sut = SUTService()
    vec = SUTVectorService()
    try:
        await vec.initialize()
    except Exception:
        logger.warning("SUT vector init failed")

    return SUTSuggestionService(
        llm=llm, sut_service=sut, vector_service=vec, ner_service=ner
    )


async def evaluate_form(service, form_id: str) -> dict:
    """Run pipeline on a transcript, compare to gold, return scores."""
    transcript = _read_transcript(form_id)
    gold = _load_gold(form_id)

    gold_request = _dedup_canonicals(_gold_request_canonicals(gold))
    logger.info("FORM %s: %d gold REQUEST codes", form_id, len(gold_request))

    try:
        suggestions = await service.suggest(transcript, brans="dahiliye")
    except Exception:
        logger.exception("FORM %s pipeline FAILED", form_id)
        suggestions = []

    # Filter system output to REQUEST-intent only
    sys_request: list[dict] = []
    for s in suggestions:
        intent = getattr(s, "intent_etiketi", None)
        intent_str = intent.value if hasattr(intent, "value") else str(intent or "REQUEST")
        if intent_str == "REQUEST":
            sys_request.append({
                "kodu": str(s.kodu),
                "adi": str(s.adi),
                "confidence": float(getattr(s, "confidence", 0.0)),
                "intent": intent_str,
                "kaynak_cumle": getattr(s, "kaynak_cumle", "")[:100],
            })

    sys_names = _dedup_canonicals([s["adi"] for s in sys_request])
    matched_sys, matched_gold, pairs = _fuzzy_overlap(sys_names, gold_request)

    tp = len(matched_sys)
    fp = len(sys_names) - tp
    fn = len(gold_request) - len(matched_gold)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    missing_gold = [gold_request[gi] for gi in range(len(gold_request)) if gi not in matched_gold]
    extra_sys = [sys_names[si] for si in range(len(sys_names)) if si not in matched_sys]

    return {
        "form_id": form_id,
        "n_system_request": len(sys_names),
        "n_gold_request": len(gold_request),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "system_request_names": sys_names,
        "gold_request_names": gold_request,
        "matched_pairs": pairs,
        "missing_gold": missing_gold,
        "extra_system": extra_sys,
        "system_full_output": sys_request,
    }


async def main(label: str) -> None:
    logger.info("=== eval_sut_intent label=%s ===", label)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)

    service = await init_pipeline()
    logger.info("pipeline initialized")

    results = []
    for fid in FORM_IDS:
        logger.info("--- FORM %s ---", fid)
        try:
            r = await evaluate_form(service, fid)
        except Exception:
            logger.exception("FORM %s evaluation FAILED", fid)
            continue
        logger.info(
            "  precision=%.3f recall=%.3f f1=%.3f (tp=%d fp=%d fn=%d)",
            r["precision"], r["recall"], r["f1"], r["tp"], r["fp"], r["fn"],
        )
        results.append(r)

    # Micro-aggregate (sum tp/fp/fn across forms)
    total_tp = sum(r["tp"] for r in results)
    total_fp = sum(r["fp"] for r in results)
    total_fn = sum(r["fn"] for r in results)
    micro_p = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0.0
    micro_r = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0.0
    micro_f1 = (
        2 * micro_p * micro_r / (micro_p + micro_r) if (micro_p + micro_r) else 0.0
    )

    summary = {
        "label": label,
        "n_forms": len(results),
        "total_tp": total_tp,
        "total_fp": total_fp,
        "total_fn": total_fn,
        "micro_precision": round(micro_p, 3),
        "micro_recall": round(micro_r, 3),
        "micro_f1": round(micro_f1, 3),
        "fuzzy_threshold": CANONICAL_MATCH_THRESHOLD,
    }
    logger.info("=== SUMMARY ===\n%s", json.dumps(summary, indent=2))

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = EVAL_DIR / f"run_{ts}_{label}.json"
    out_path.write_text(
        json.dumps({"summary": summary, "per_form": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("written: %s", out_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", type=str, default="run", help="run label tag")
    args = parser.parse_args()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main(args.label))
