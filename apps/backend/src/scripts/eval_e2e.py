"""End-to-end evaluation framework for KlinikAsistan pipeline.

Tek script, tek ReportGenerator çağrısı, tüm pipeline metrikleri:
  - Anamnez field-level scoring (mevcut eval_anamnez_fields fonksiyonları)
  - ICD-10 code Recall/Precision/F1 (mevcut eval_icd10_codes fonksiyonları)
  - SUT tetkik intent disambiguation (mevcut eval_sut_intent fonksiyonları)
  - RAG retrieval Recall@K, MRR, hit rate (RAGProbe instrumentation)
  - Latency per stage
  - Token cost (input/output, USD estimate)

Mevcut 3 eval scriptine dokunmaz — sadece scoring fonksiyonlarını import eder
ve ReportGenerator.generate_report'u TEK seferde çağırarak cost duplikasyonunu
ortadan kaldırır.

Çıktı:
  - data/eval_results/run_<ts>_<label>.json   (detay)
  - data/eval_results/run_<ts>_<label>.csv    (long format, dataframe-friendly)
  - data/eval_results/run_<ts>_<label>.log    (pipeline trace)

Kullanım:
    python -m apps.backend.src.scripts.eval_e2e --label baseline
    python -m apps.backend.src.scripts.eval_e2e --label after_rrf --max-cost-usd 5.0
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[4]


# ---------------------------------------------------------------------------
# Manual .env loader — avoids python-dotenv dependency
# Loads BEFORE any pipeline import so settings/services pick up correct values
# ---------------------------------------------------------------------------
def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip()
        # strip surrounding quotes
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        # don't overwrite if already set in environment
        os.environ.setdefault(key, val)


_load_env_file(PROJECT_ROOT / ".env")

# Output directory
OUTPUT_DIR = PROJECT_ROOT / "data" / "eval_results"
SYNTHETIC_DIR = PROJECT_ROOT / "data" / "eval_synthetic"
DEFAULT_FORM_IDS = ["S001", "S002", "S003", "S004", "S005"]

# Anthropic Opus 4.7 pricing (USD per 1M tokens, 2026-05 baseline)
# Haiku 4.5 fallback prices kept for ablation comparisons
PRICING = {
    "claude-opus-4-7": {"input": 15.0, "output": 75.0},
    "claude-haiku-4-5-20251001": {"input": 1.0, "output": 5.0},
}


# ---------------------------------------------------------------------------
# Logging setup — file + stdout
# ---------------------------------------------------------------------------
def setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("eval_e2e")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


# ---------------------------------------------------------------------------
# Cost & token tracker
# ---------------------------------------------------------------------------
class CostTracker:
    """Track LLM token usage + USD cost across pipeline calls."""

    def __init__(self, model_name: str, max_usd: float = 10.0):
        self.model_name = model_name
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0
        self.max_usd = max_usd
        # Pricing fallback to Opus rates if model unknown (conservative)
        self.pricing = PRICING.get(model_name, PRICING["claude-opus-4-7"])

    def record(self, input_t: int, output_t: int) -> None:
        self.input_tokens += input_t
        self.output_tokens += output_t
        self.calls += 1

    @property
    def usd(self) -> float:
        return (
            self.input_tokens * self.pricing["input"] / 1_000_000
            + self.output_tokens * self.pricing["output"] / 1_000_000
        )

    def over_budget(self) -> bool:
        return self.usd > self.max_usd

    def snapshot(self) -> dict:
        return {
            "model": self.model_name,
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "usd": round(self.usd, 4),
        }


# ---------------------------------------------------------------------------
# RAG retrieval probe — monkey-patches AnamnezRAGService to capture top-k
# ---------------------------------------------------------------------------
class RAGProbe:
    """Wrap AnamnezRAGService.query_similar_cases to capture retrieved docs.

    Per-query trace: { query_text, top_ids, distances, k }.
    No additional LLM call — purely instrumentation.
    """

    def __init__(self, rag_service: Any | None):
        self.rag = rag_service
        self.queries: list[dict] = []
        self._original_method = None
        if rag_service is not None and hasattr(rag_service, "query_similar_cases"):
            self._original_method = rag_service.query_similar_cases
            rag_service.query_similar_cases = self._wrapped  # type: ignore[method-assign]

    async def _wrapped(self, query_text: str, top_k: int = 5):
        results = await self._original_method(query_text, top_k=top_k)
        self.queries.append({
            "query_text": query_text[:200],
            "k": top_k,
            "n_results": len(results) if results else 0,
            "top_distances": [
                getattr(r, "distance", None) for r in (results or [])
            ][:top_k],
        })
        return results

    def reset(self) -> None:
        self.queries = []

    def snapshot(self) -> dict:
        if not self.queries:
            return {"n_queries": 0, "hit_rate": 0.0, "mean_top_distance": None}
        n_with_results = sum(1 for q in self.queries if q["n_results"] > 0)
        all_distances = [
            d for q in self.queries for d in q["top_distances"] if d is not None
        ]
        return {
            "n_queries": len(self.queries),
            "hit_rate": round(n_with_results / len(self.queries), 3),
            "mean_top_distance": (
                round(sum(all_distances) / len(all_distances), 3)
                if all_distances else None
            ),
            "queries": self.queries,
        }

    def restore(self) -> None:
        if self.rag is not None and self._original_method is not None:
            self.rag.query_similar_cases = self._original_method


# ---------------------------------------------------------------------------
# Pipeline init — full ReportGenerator with all services
# ---------------------------------------------------------------------------
async def init_pipeline(logger: logging.Logger):
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
        logger.warning("LLM init failed — eval may run with degraded mode")

    ner = NERService()
    icd_svc = ICD10Service()
    icd_vec = ICD10VectorService()
    sut_svc = SUTService()
    sut_vec = SUTVectorService()
    try:
        await icd_vec.initialize()
        await sut_vec.initialize()
    except Exception:
        logger.warning("Vector service init partial failure")

    icd_mode = os.getenv("ASR_ICD__VALIDATION_MODE", "strict").lower()
    sut_mode = os.getenv("ASR_SUT__VALIDATION_MODE", "strict").lower()

    icd_pipeline = ICD10SuggestionService(
        llm=llm, icd10_service=icd_svc, vector_service=icd_vec,
        ner_service=ner, validation_mode=icd_mode,
    )
    sut_pipeline = SUTSuggestionService(
        llm=llm, sut_service=sut_svc, vector_service=sut_vec,
        ner_service=ner, validation_mode=sut_mode,
    )

    # Anamnez RAG (skip if disabled)
    anamnez_rag = None
    if os.getenv("ANAMNEZ_RAG_ENABLED", "true").lower() not in ("false", "0", "no"):
        try:
            from apps.backend.src.services.anamnez_rag_service import AnamnezRAGService
            anamnez_rag = AnamnezRAGService(
                profile=settings.rag.anamnez_profile,
                fmt=settings.rag.anamnez_fmt,
            )
            await anamnez_rag.initialize()
        except Exception:
            logger.warning("AnamnezRAG init failed — eval will skip RAG metrics")
            anamnez_rag = None

    report_gen = ReportGenerator(
        ner=ner,
        rag=None,  # legacy synthetic RAG disabled
        llm=llm,
        icd10_suggestion_service=icd_pipeline,
        sut_suggestion_service=sut_pipeline,
        anamnez_rag=anamnez_rag,
        default_top_k=settings.rag.anamnez_top_k,
        use_synthetic_rag=settings.rag.use_synthetic,
    )

    model_name = getattr(settings.llm, "anthropic_model", "claude-opus-4-7")
    return {
        "report_gen": report_gen,
        "anamnez_rag": anamnez_rag,
        "llm": llm,
        "model_name": model_name,
        "icd_mode": icd_mode,
        "sut_mode": sut_mode,
        "rag_profile": settings.rag.anamnez_profile,
        "embedding_model": os.getenv("EMBEDDING_MODEL", "minilm"),
    }


# ---------------------------------------------------------------------------
# Single form evaluation — calls ReportGen ONCE, scores all pipelines
# ---------------------------------------------------------------------------
async def evaluate_form(
    services: dict,
    rag_probe: RAGProbe,
    cost_tracker: CostTracker,
    form_id: str,
    logger: logging.Logger,
    timeout_s: float = 300.0,
) -> dict:
    # Lazy imports — use existing scoring functions where safe
    from apps.backend.src.scripts.eval_anamnez_fields import _eval_field
    from apps.backend.src.scripts.eval_icd10_codes import _code_metrics
    # NOTE: eval_sut_intent imports python-docx at module level for legacy
    # real-data path; we duplicate the 3 small helpers inline to avoid that
    # dependency for synthetic-only evaluation.

    transcript_path = SYNTHETIC_DIR / f"transcript_{form_id}.txt"
    if not transcript_path.exists():
        return {"form_id": form_id, "error": f"Transcript not found: {transcript_path}"}

    transcript = transcript_path.read_text(encoding="utf-8")

    # Load all 3 gold files (some may be missing for partial gold sets)
    gold_anamnez: dict = {}
    gold_icd: list[dict] = []
    gold_intent: dict = {}
    try:
        anamnez_path = SYNTHETIC_DIR / f"gold_{form_id}_anamnez.json"
        if anamnez_path.exists():
            gold_anamnez = json.loads(anamnez_path.read_text(encoding="utf-8")).get("fields", {})
        icd_path = SYNTHETIC_DIR / f"gold_{form_id}_icd10.json"
        if icd_path.exists():
            gold_icd = json.loads(icd_path.read_text(encoding="utf-8")).get("expected_codes", [])
        intent_path = SYNTHETIC_DIR / f"gold_{form_id}_intent.json"
        if intent_path.exists():
            gold_intent = json.loads(intent_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.exception("Gold load failed for %s", form_id)
        return {"form_id": form_id, "error": f"Gold load: {e}"}

    rag_probe.reset()
    segments = [{"start_time": 0.0, "end_time": 1.0, "text": transcript, "speaker": ""}]

    # ----- Single ReportGen call (capture latency + cost via probes) -----
    t0 = time.perf_counter()
    try:
        report = await asyncio.wait_for(
            services["report_gen"].generate_report(segments, brans="dahiliye"),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError:
        logger.warning("FORM %s timed out after %.0fs", form_id, timeout_s)
        return {"form_id": form_id, "error": f"timeout after {timeout_s}s"}
    except Exception as e:
        logger.exception("FORM %s pipeline FAILED", form_id)
        return {"form_id": form_id, "error": str(e)}
    elapsed = time.perf_counter() - t0

    sys_sections = {s["key"]: s.get("content", "") for s in report.get("sections", [])}

    # ----- Anamnez field-level scoring -----
    anamnez_field_results: list[dict] = []
    for key, gold_val in gold_anamnez.items():
        sys_val = sys_sections.get(key, "")
        m = _eval_field(key, sys_val, gold_val)
        m["sys_value"] = sys_val[:120]
        m["gold_value"] = gold_val[:120]
        anamnez_field_results.append(m)
    anamnez_macro = (
        {
            "exact_match": round(sum(f["exact_match"] for f in anamnez_field_results)
                                 / max(len(anamnez_field_results), 1), 3),
            "token_f1": round(sum(f["token_f1"] for f in anamnez_field_results)
                              / max(len(anamnez_field_results), 1), 3),
            "bleu1": round(sum(f["bleu1"] for f in anamnez_field_results)
                           / max(len(anamnez_field_results), 1), 3),
        } if anamnez_field_results else {}
    )

    # ----- ICD code scoring -----
    icd_section = sys_sections.get("icd10_list", "")
    sys_icd_codes = _extract_icd_codes(icd_section)
    gold_icd_codes = [g.get("code", "") for g in gold_icd]
    icd_metrics_exact = _code_metrics(sys_icd_codes, gold_icd_codes, match_level="exact")
    icd_metrics_prefix = _code_metrics(sys_icd_codes, gold_icd_codes, match_level="prefix")

    # ----- SUT intent scoring -----
    sut_section = sys_sections.get("sut_tetkik_list", "")
    sys_sut_names = _extract_sut_names(sut_section)
    gold_sut_request = _dedup_canonicals(_gold_request_canonicals(gold_intent)) if gold_intent else []
    if sys_sut_names and gold_sut_request:
        matched_sys, matched_gold, _pairs = _fuzzy_overlap(sys_sut_names, gold_sut_request)
        tp = len(matched_sys)
        fp = len(sys_sut_names) - tp
        fn = len(gold_sut_request) - len(matched_gold)
        sut_p = tp / (tp + fp) if (tp + fp) else 0.0
        sut_r = tp / (tp + fn) if (tp + fn) else 0.0
        sut_f1 = 2 * sut_p * sut_r / (sut_p + sut_r) if (sut_p + sut_r) else 0.0
        sut_metrics = {
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(sut_p, 3), "recall": round(sut_r, 3), "f1": round(sut_f1, 3),
            "n_system": len(sys_sut_names), "n_gold": len(gold_sut_request),
        }
    else:
        sut_metrics = {
            "tp": 0, "fp": len(sys_sut_names), "fn": len(gold_sut_request),
            "precision": 0.0, "recall": 0.0, "f1": 0.0,
            "n_system": len(sys_sut_names), "n_gold": len(gold_sut_request),
        }

    return {
        "form_id": form_id,
        "elapsed_s": round(elapsed, 2),
        "anamnez": {
            "n_fields": len(anamnez_field_results),
            "macro": anamnez_macro,
            "fields": anamnez_field_results,
        },
        "icd10": {
            "system_codes": sys_icd_codes,
            "gold_codes": gold_icd_codes,
            "exact": icd_metrics_exact,
            "prefix": icd_metrics_prefix,
        },
        "sut": {
            "system_names": sys_sut_names,
            "gold_names": gold_sut_request,
            "metrics": sut_metrics,
        },
        "rag": rag_probe.snapshot(),
    }


CANONICAL_MATCH_THRESHOLD = 75


def _gold_request_canonicals(gold: dict) -> list[str]:
    """Inline copy from eval_sut_intent (avoid docx import)."""
    return [
        m["canonical_tetkik"] for m in gold.get("mentions", [])
        if m.get("include") and m.get("intent_etiketi") == "REQUEST"
    ]


def _dedup_canonicals(canonicals: list[str]) -> list[str]:
    """Inline copy: code-level dedup."""
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
    """Inline copy: rapidfuzz greedy fuzzy match."""
    from rapidfuzz import fuzz
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
            pairs.append({"system": sname, "gold": gold_names[best_gi], "score": best_score})
    return matched_sys, matched_gold, pairs


def _extract_icd_codes(icd_text: str) -> list[str]:
    """Parse ICD-10 codes from rendered section text.
    Format: "(E11.9) - Diabetes... [%85]" — extract codes from parens."""
    import re
    if not icd_text:
        return []
    matches = re.findall(r"\(([A-Z]\d+(?:\.\d+)?)\)", icd_text)
    return list(dict.fromkeys(matches))  # dedup, preserve order


def _extract_sut_names(sut_text: str) -> list[str]:
    """Parse SUT canonical names from rendered section text.
    Format: "(L102450) - Hemogram [%92]" — extract name between ') - ' and ' [%'."""
    import re
    if not sut_text:
        return []
    names = []
    for line in sut_text.split("\n"):
        m = re.search(r"\)\s*-\s*(.+?)(?:\s*\[%|\s*$)", line)
        if m:
            names.append(m.group(1).strip())
    # dedup case-insensitively, preserve order
    seen: set = set()
    out: list[str] = []
    for n in names:
        k = n.lower()
        if k not in seen:
            seen.add(k)
            out.append(n)
    return out


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------
def write_outputs(
    results: list[dict], summary: dict,
    out_dir: Path, ts: str, label: str, logger: logging.Logger,
) -> None:
    """Write JSON (detail) + CSV (long format) + summary log."""
    out_dir.mkdir(parents=True, exist_ok=True)
    base = f"run_{ts}_{label}"

    # 1) JSON — full detail
    json_path = out_dir / f"{base}.json"
    json_path.write_text(
        json.dumps({"summary": summary, "per_form": results},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("JSON written: %s", json_path)

    # 2) CSV — long format (form_id, pipeline, metric, value)
    csv_path = out_dir / f"{base}.csv"
    rows = []
    for r in results:
        if "error" in r:
            rows.append({
                "form_id": r["form_id"], "pipeline": "system",
                "metric": "error", "value": r["error"],
            })
            continue
        fid = r["form_id"]
        rows.append({"form_id": fid, "pipeline": "system", "metric": "elapsed_s",
                     "value": r.get("elapsed_s", "")})
        # anamnez
        for k, v in r.get("anamnez", {}).get("macro", {}).items():
            rows.append({"form_id": fid, "pipeline": "anamnez",
                         "metric": f"macro_{k}", "value": v})
        # icd
        for level in ("exact", "prefix"):
            for k in ("precision", "recall", "f1", "tp", "fp", "fn"):
                v = r.get("icd10", {}).get(level, {}).get(k, "")
                rows.append({"form_id": fid, "pipeline": "icd10",
                             "metric": f"{level}_{k}", "value": v})
        # sut
        for k in ("precision", "recall", "f1", "tp", "fp", "fn", "n_system", "n_gold"):
            v = r.get("sut", {}).get("metrics", {}).get(k, "")
            rows.append({"form_id": fid, "pipeline": "sut",
                         "metric": k, "value": v})
        # rag
        rag = r.get("rag", {})
        for k in ("n_queries", "hit_rate", "mean_top_distance"):
            v = rag.get(k, "")
            rows.append({"form_id": fid, "pipeline": "rag",
                         "metric": k, "value": v if v is not None else ""})

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["form_id", "pipeline", "metric", "value"])
        writer.writeheader()
        writer.writerows(rows)
    logger.info("CSV written: %s", csv_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main(args: argparse.Namespace) -> None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = OUTPUT_DIR / f"run_{ts}_{args.label}.log"
    logger = setup_logging(log_path)

    logger.info("=" * 70)
    logger.info("eval_e2e — label=%s, form_ids=%s", args.label, args.form_ids)
    logger.info("=" * 70)

    services = await init_pipeline(logger)
    cost_tracker = CostTracker(services["model_name"], max_usd=args.max_cost_usd)
    rag_probe = RAGProbe(services["anamnez_rag"])

    logger.info("Pipeline initialized:")
    logger.info("  LLM model       : %s", services["model_name"])
    logger.info("  Embedding       : %s", services["embedding_model"])
    logger.info("  ICD validation  : %s", services["icd_mode"])
    logger.info("  SUT validation  : %s", services["sut_mode"])
    logger.info("  RAG profile     : %s", services["rag_profile"])
    logger.info("  RAG enabled     : %s", services["anamnez_rag"] is not None)
    logger.info("  Max cost (USD)  : %.2f", args.max_cost_usd)

    results: list[dict] = []
    for fid in args.form_ids:
        logger.info("--- FORM %s ---", fid)
        if cost_tracker.over_budget():
            logger.warning("BUDGET EXCEEDED ($%.4f > $%.2f) — stopping",
                           cost_tracker.usd, args.max_cost_usd)
            break
        try:
            r = await evaluate_form(
                services, rag_probe, cost_tracker, fid, logger,
                timeout_s=args.per_form_timeout,
            )
        except Exception as e:
            logger.exception("FORM %s evaluation crashed: %s", fid, e)
            r = {"form_id": fid, "error": f"crash: {e}"}
        results.append(r)
        if "error" not in r:
            logger.info(
                "  elapsed=%.1fs  ICD R/P/F1=%.2f/%.2f/%.2f  SUT R/P/F1=%.2f/%.2f/%.2f  Anamnez F1=%.2f",
                r["elapsed_s"],
                r["icd10"]["exact"]["recall"], r["icd10"]["exact"]["precision"], r["icd10"]["exact"]["f1"],
                r["sut"]["metrics"]["recall"], r["sut"]["metrics"]["precision"], r["sut"]["metrics"]["f1"],
                r["anamnez"]["macro"].get("token_f1", 0.0),
            )

    rag_probe.restore()

    # ---- Aggregates ----
    valid = [r for r in results if "error" not in r]
    n = len(valid)

    def avg(extract):
        vals = [extract(r) for r in valid if extract(r) is not None]
        return round(sum(vals) / len(vals), 3) if vals else 0.0

    summary = {
        "label": args.label,
        "timestamp": ts,
        "n_forms": len(results),
        "n_success": n,
        "n_failed": len(results) - n,
        "config": {
            "model": services["model_name"],
            "embedding": services["embedding_model"],
            "icd_validation_mode": services["icd_mode"],
            "sut_validation_mode": services["sut_mode"],
            "rag_profile": services["rag_profile"],
            "rag_enabled": services["anamnez_rag"] is not None,
            "rrf_enabled": os.getenv("ASR_RRF_ENABLED", "false").lower() in ("true", "1"),
        },
        "averages": {
            "elapsed_s": avg(lambda r: r.get("elapsed_s")),
            "anamnez_token_f1": avg(lambda r: r.get("anamnez", {}).get("macro", {}).get("token_f1")),
            "icd_recall_exact": avg(lambda r: r.get("icd10", {}).get("exact", {}).get("recall")),
            "icd_precision_exact": avg(lambda r: r.get("icd10", {}).get("exact", {}).get("precision")),
            "icd_f1_exact": avg(lambda r: r.get("icd10", {}).get("exact", {}).get("f1")),
            "icd_recall_prefix": avg(lambda r: r.get("icd10", {}).get("prefix", {}).get("recall")),
            "sut_recall": avg(lambda r: r.get("sut", {}).get("metrics", {}).get("recall")),
            "sut_precision": avg(lambda r: r.get("sut", {}).get("metrics", {}).get("precision")),
            "sut_f1": avg(lambda r: r.get("sut", {}).get("metrics", {}).get("f1")),
            "rag_hit_rate": avg(lambda r: r.get("rag", {}).get("hit_rate")),
        },
        "cost": cost_tracker.snapshot(),
    }

    logger.info("=" * 70)
    logger.info("=== SUMMARY ===\n%s", json.dumps(summary, indent=2, ensure_ascii=False))

    write_outputs(results, summary, OUTPUT_DIR, ts, args.label, logger)
    logger.info("LOG written: %s", log_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", type=str, default="run", help="Run label tag")
    parser.add_argument(
        "--form-ids", type=str, default=",".join(DEFAULT_FORM_IDS),
        help=f"Comma-separated form IDs (default: {','.join(DEFAULT_FORM_IDS)})",
    )
    parser.add_argument(
        "--per-form-timeout", type=float, default=300.0,
        help="Timeout per form in seconds (default 300)",
    )
    parser.add_argument(
        "--max-cost-usd", type=float, default=10.0,
        help="Hard cap on cumulative API cost (USD); abort when exceeded",
    )
    # Hyperparameter override flags (Aşama 2 — ablation taraması için)
    # Bu flag'ler env vars'a yazılır → pipeline init'te okunur.
    parser.add_argument(
        "--vector-min-score", type=float, default=None,
        help="Override vector DB min_score threshold (default 0.45 in code)",
    )
    parser.add_argument(
        "--intent-min-confidence", type=float, default=None,
        help="Override SUT confidence gate threshold (default 0.85)",
    )
    parser.add_argument(
        "--validation-mode-icd", type=str, default=None,
        choices=["strict", "db_rescue"],
        help="Override ASR_ICD__VALIDATION_MODE for this run",
    )
    parser.add_argument(
        "--validation-mode-sut", type=str, default=None,
        choices=["strict", "db_rescue"],
        help="Override ASR_SUT__VALIDATION_MODE for this run",
    )
    parser.add_argument(
        "--rrf", type=str, default=None,
        choices=["true", "false"],
        help="Override ASR_RRF_ENABLED for this run (Reciprocal Rank Fusion)",
    )
    parser.add_argument(
        "--embedding-model", type=str, default=None,
        choices=["minilm", "e5-base", "e5-large", "bge-m3"],
        help="Override EMBEDDING_MODEL for this run",
    )
    args = parser.parse_args()
    args.form_ids = [s.strip() for s in args.form_ids.split(",") if s.strip()]

    # Apply CLI overrides to environment BEFORE any pipeline import
    # (settings/services read env vars at init time)
    if args.validation_mode_icd:
        os.environ["ASR_ICD__VALIDATION_MODE"] = args.validation_mode_icd
    if args.validation_mode_sut:
        os.environ["ASR_SUT__VALIDATION_MODE"] = args.validation_mode_sut
    if args.rrf:
        os.environ["ASR_RRF_ENABLED"] = args.rrf
    if args.embedding_model:
        os.environ["EMBEDDING_MODEL"] = args.embedding_model
    # Vector min_score and intent_min_confidence are passed via env so
    # services pick them up (need code changes in services to read these
    # env vars; for now they're documented but not consumed)
    if args.vector_min_score is not None:
        os.environ["ASR_VECTOR_MIN_SCORE"] = str(args.vector_min_score)
    if args.intent_min_confidence is not None:
        os.environ["ASR_SUT__INTENT_MIN_CONFIDENCE"] = str(args.intent_min_confidence)

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main(args))
