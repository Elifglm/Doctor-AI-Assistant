"""Eval ICD-10 code suggestions against gold standard.

Reads:
  - data/eval_synthetic/gold_<form_id>_icd10.json (expected ICD codes)
  - data/eval_synthetic/gold_<form_id>_anamnez.json (anamnez fields, for isolated mode)
  - data/eval_synthetic/transcript_<form_id>.txt (raw transcript, for e2e mode)

Modes:
  - isolated (default): use gold anamnez fields as input to ICD pipeline.
    Tests JUST the NER → vector retrieval → LLM selection chain, with
    anamnez quality held constant (=ground truth).
  - e2e: run full pipeline transcript → anamnez gen → ICD. Tests the chain
    end-to-end including anamnez generation errors.

Computes (per-form and micro-aggregated):
  - precision, recall, F1 at:
      * exact code level (e.g. E11.9 must match E11.9)
      * 3-char prefix level (e.g. E11.0 == E11.9 both match "E11")
  - hallucination_rate: % system codes not in candidate pool (strict) or DB (db_rescue)

Output:
  - data/eval_icd10/run_<ts>_<label>.json

Usage:
    # Isolated, strict mode, Haiku:
    python -m apps.backend.src.scripts.eval_icd10_codes \\
        --label icd_strict_haiku --mode isolated

    # E2E, db_rescue mode:
    ASR_ICD__VALIDATION_MODE=db_rescue python -m apps.backend.src.scripts.eval_icd10_codes \\
        --label icd_dbrescue --mode e2e
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Load .env so EMBEDDING_MODEL and other env vars match the running backend.
# Without this, get_profile() falls back to "minilm" default — which uses a
# different ChromaDB and previously crashed on this dataset.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("eval_icd10")

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "eval_synthetic"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data" / "eval_icd10"
DEFAULT_FORM_IDS = [f"T{i:02d}" for i in range(1, 21)]  # T01..T20 (v2 dataset)


def _load_gold_icd10(data_dir: Path, form_id: str) -> list[dict]:
    """Return list of expected codes: [{icd_kodu, tani, source, reasoning}, ...]"""
    path = data_dir / f"gold_{form_id}_icd10.json"
    obj = json.loads(path.read_text(encoding="utf-8"))
    return obj.get("expected_codes", [])


def _load_gold_anamnez(data_dir: Path, form_id: str) -> dict[str, str]:
    """Return anamnez fields dict (26 keys for dahiliye)."""
    path = data_dir / f"gold_{form_id}_anamnez.json"
    obj = json.loads(path.read_text(encoding="utf-8"))
    return obj.get("fields", {})


def _read_transcript(data_dir: Path, form_id: str) -> str:
    path = data_dir / f"transcript_{form_id}.txt"
    return path.read_text(encoding="utf-8")


def _code_metrics(
    system_codes: list[str], gold_codes: list[str], match_level: str = "exact"
) -> dict:
    """Compute P/R/F1 between system and gold ICD-10 code sets.

    match_level:
        "exact"  — codes must match exactly (E11.9 == E11.9 only)
        "prefix" — 3-char prefix match (E11.9 == E11.0 both match "E11")
    """
    def _norm(c: str) -> str:
        c = c.strip().upper()
        if match_level == "prefix":
            return c.split(".")[0][:3]
        return c

    sys_set = {_norm(c) for c in system_codes if c}
    gold_set = {_norm(c) for c in gold_codes if c}

    tp = len(sys_set & gold_set)
    fp = len(sys_set - gold_set)
    fn = len(gold_set - sys_set)
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return {
        "match_level": match_level,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(p, 3),
        "recall": round(r, 3),
        "f1": round(f1, 3),
    }


async def init_pipeline(mode: str):
    """Boot the necessary services for the chosen eval mode."""
    from config.settings import AppSettings
    from apps.backend.src.services.llm_factory import create_llm_service
    from apps.backend.src.services.icd10_service import ICD10Service
    from apps.backend.src.services.icd10_vector_service import ICD10VectorService
    from apps.backend.src.services.icd10_suggestion_service import ICD10SuggestionService
    from apps.backend.src.services.ner_service import NERService

    settings = AppSettings()
    llm = create_llm_service(settings)
    try:
        await llm.initialize()
    except Exception:
        logger.warning("LLM init failed (provider=%s)", llm.provider_name)

    icd_svc = ICD10Service()
    vec_svc = ICD10VectorService()
    try:
        await vec_svc.initialize()
    except Exception:
        logger.warning("ICD10 vector init failed")

    ner = NERService()

    validation_mode = os.environ.get("ASR_ICD__VALIDATION_MODE", "strict")
    suggestion = ICD10SuggestionService(
        llm=llm,
        icd10_service=icd_svc,
        vector_service=vec_svc,
        ner_service=ner,
        validation_mode=validation_mode,
    )

    if mode == "e2e":
        # Full report generator needed to convert transcript → anamnez → ICD
        from apps.backend.src.services.report_generator import ReportGenerator
        from apps.backend.src.services.sut_service import SUTService
        from apps.backend.src.services.sut_vector_service import SUTVectorService
        from apps.backend.src.services.sut_suggestion_service import SUTSuggestionService

        sut_svc = SUTService()
        sut_vec = SUTVectorService()
        try:
            await sut_vec.initialize()
        except Exception:
            logger.warning("SUT vector init failed")
        sut_suggestion = SUTSuggestionService(
            llm=llm, sut_service=sut_svc, vector_service=sut_vec, ner_service=ner
        )
        report_gen = ReportGenerator(
            ner=ner,
            rag=None,
            llm=llm,
            icd10_suggestion_service=suggestion,
            sut_suggestion_service=sut_suggestion,
        )
        return {"icd": suggestion, "report_gen": report_gen, "validation_mode": validation_mode}

    return {"icd": suggestion, "report_gen": None, "validation_mode": validation_mode}


async def evaluate_form_isolated(services: dict, data_dir: Path, form_id: str) -> dict:
    """Use gold anamnez fields as input to ICD pipeline."""
    anamnez = _load_gold_anamnez(data_dir, form_id)
    gold_codes_full = _load_gold_icd10(data_dir, form_id)
    gold_codes = [c["icd_kodu"] for c in gold_codes_full]

    suggestions = await services["icd"].suggest_from_report(anamnez)
    sys_codes = [s.icd_kodu for s in suggestions]

    return {
        "form_id": form_id,
        "mode": "isolated",
        "n_gold": len(gold_codes),
        "n_system": len(sys_codes),
        "system_codes": sys_codes,
        "gold_codes": gold_codes,
        "system_full": [
            {
                "icd_kodu": s.icd_kodu,
                "tani": s.tani,
                "confidence": float(getattr(s, "confidence", 0.0)),
                "reasoning": getattr(s, "reasoning", ""),
            } for s in suggestions
        ],
        "gold_full": gold_codes_full,
        "metrics_exact": _code_metrics(sys_codes, gold_codes, "exact"),
        "metrics_prefix": _code_metrics(sys_codes, gold_codes, "prefix"),
    }


async def evaluate_form_e2e(services: dict, data_dir: Path, form_id: str) -> dict:
    """Run full pipeline: transcript → anamnez gen → ICD."""
    transcript = _read_transcript(data_dir, form_id)
    gold_codes_full = _load_gold_icd10(data_dir, form_id)
    gold_codes = [c["icd_kodu"] for c in gold_codes_full]

    report = await services["report_gen"].generate_report(
        [{"start_time": 0, "end_time": 1, "text": transcript, "speaker": ""}],
        brans="dahiliye",
    )
    icd_section = next(
        (s for s in report.get("sections", []) if s["key"] == "icd10_list"),
        None,
    )
    sys_codes_str = (icd_section or {}).get("content", "")
    # Parse "E11.9, I10, E78.0" or similar
    sys_codes = [c.strip() for c in sys_codes_str.replace(";", ",").split(",") if c.strip()]

    return {
        "form_id": form_id,
        "mode": "e2e",
        "n_gold": len(gold_codes),
        "n_system": len(sys_codes),
        "system_codes": sys_codes,
        "gold_codes": gold_codes,
        "icd10_section_raw": sys_codes_str,
        "gold_full": gold_codes_full,
        "metrics_exact": _code_metrics(sys_codes, gold_codes, "exact"),
        "metrics_prefix": _code_metrics(sys_codes, gold_codes, "prefix"),
    }


async def main(label: str, mode: str, data_dir: Path, form_ids: list[str]) -> None:
    logger.info("=== eval_icd10 label=%s mode=%s ===", label, mode)
    DEFAULT_OUT_DIR.mkdir(parents=True, exist_ok=True)

    services = await init_pipeline(mode)
    logger.info("pipeline initialized (validation_mode=%s)", services["validation_mode"])

    eval_fn = evaluate_form_e2e if mode == "e2e" else evaluate_form_isolated

    results = []
    for fid in form_ids:
        logger.info("--- FORM %s ---", fid)
        try:
            r = await eval_fn(services, data_dir, fid)
        except Exception:
            logger.exception("FORM %s eval FAILED", fid)
            continue
        ex = r["metrics_exact"]
        pf = r["metrics_prefix"]
        logger.info(
            "  exact: P=%.3f R=%.3f F1=%.3f  prefix: P=%.3f R=%.3f F1=%.3f",
            ex["precision"], ex["recall"], ex["f1"],
            pf["precision"], pf["recall"], pf["f1"],
        )
        results.append(r)

    # Micro-aggregate
    def _micro(level: str) -> dict:
        tp = sum(r[f"metrics_{level}"]["tp"] for r in results)
        fp = sum(r[f"metrics_{level}"]["fp"] for r in results)
        fn = sum(r[f"metrics_{level}"]["fn"] for r in results)
        p = tp / (tp + fp) if (tp + fp) else 0.0
        rc = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * p * rc / (p + rc) if (p + rc) else 0.0
        return {
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(p, 3),
            "recall": round(rc, 3),
            "f1": round(f1, 3),
        }

    summary = {
        "label": label,
        "mode": mode,
        "validation_mode": services["validation_mode"],
        "n_forms": len(results),
        "micro_exact": _micro("exact"),
        "micro_prefix": _micro("prefix"),
    }
    logger.info("=== SUMMARY ===\n%s", json.dumps(summary, indent=2, ensure_ascii=False))

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = DEFAULT_OUT_DIR / f"run_{ts}_{label}.json"
    out_path.write_text(
        json.dumps({"summary": summary, "per_form": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("written: %s", out_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", type=str, default="icd_run", help="run label")
    parser.add_argument(
        "--mode", type=str, choices=["isolated", "e2e"], default="isolated",
        help="isolated: gold anamnez → ICD. e2e: transcript → anamnez gen → ICD.",
    )
    parser.add_argument(
        "--data-dir", type=Path, default=None,
        help=f"Directory with gold_*_icd10.json + gold_*_anamnez.json (default: {DEFAULT_DATA_DIR})",
    )
    parser.add_argument(
        "--form-ids", type=str, default=None,
        help="Comma-separated form IDs (default: S001,S002,S003,S004,S005)",
    )
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
    asyncio.run(main(args.label, args.mode, data_dir, form_ids))
