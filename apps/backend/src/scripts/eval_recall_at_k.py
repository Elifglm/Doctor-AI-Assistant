"""Eval ICD-10 retrieval-stage Recall@k (vector DB only, no LLM).

Measures the quality of the ICD-10 vector retrieval layer in isolation:
for each gold ICD code, search the vector DB with the doctor's transcript
phrase (or fallback to the gold tani text) and check whether the gold code
appears in the top-k results.

Reads:
  - data/eval_synthetic/gold_<form_id>_icd10.json (gold codes + transcript_phrase)

Computes:
  - Recall@k for k in {5, 10, 20, 50}
  - Per-form recall + micro/macro aggregates
  - Mean rank of gold code when found

Output:
  - data/eval_icd10/recall_at_k_<ts>.json
  - data/eval_icd10/recall_at_k_<ts>.md (markdown table for thesis)

Usage:
    python -m apps.backend.src.scripts.eval_recall_at_k

Why this metric matters (thesis context):
    Vector retrieval is upstream of LLM selection. If gold code is never in
    top-k candidates, no LLM (Haiku/Opus) can recover it. Recall@k isolates
    embedding/index quality from LLM reasoning.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("eval_recall_at_k")

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "eval_synthetic"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data" / "eval_icd10"
DEFAULT_FORM_IDS = [f"T{i:02d}" for i in range(1, 21)]
K_VALUES = [5, 10, 20, 50]
MAX_K = max(K_VALUES)


def _load_gold(data_dir: Path, form_id: str) -> list[dict]:
    path = data_dir / f"gold_{form_id}_icd10.json"
    obj = json.loads(path.read_text(encoding="utf-8"))
    return obj.get("expected_codes", [])


def _norm_code(c: str) -> str:
    return (c or "").strip().upper()


async def evaluate_form(vec_svc, form_id: str, data_dir: Path) -> dict:
    gold = _load_gold(data_dir, form_id)
    per_code = []
    for entry in gold:
        gold_code = _norm_code(entry.get("icd_kodu", ""))
        if not gold_code:
            continue
        # Prefer the natural-Turkish doctor phrase; fall back to tani.
        query = (entry.get("transcript_phrase") or entry.get("tani") or "").strip()
        if not query:
            per_code.append({
                "gold_code": gold_code,
                "query": "",
                "rank": None,
                "found_at_k": {k: False for k in K_VALUES},
            })
            continue

        results = await vec_svc.search(query, n_results=MAX_K)
        retrieved = [_norm_code(r.icd_kodu) for r in results]

        rank = None
        for i, code in enumerate(retrieved, start=1):
            if code == gold_code:
                rank = i
                break

        per_code.append({
            "gold_code": gold_code,
            "query": query[:80],
            "rank": rank,
            "found_at_k": {k: (rank is not None and rank <= k) for k in K_VALUES},
        })

    return {"form_id": form_id, "per_code": per_code}


def aggregate(results: list[dict]) -> dict:
    """Recall@k = (# gold codes found in top-k) / (# total gold codes)."""
    total = 0
    hits = {k: 0 for k in K_VALUES}
    ranks_when_found = []

    for r in results:
        for c in r["per_code"]:
            total += 1
            for k in K_VALUES:
                if c["found_at_k"][k]:
                    hits[k] += 1
            if c["rank"] is not None:
                ranks_when_found.append(c["rank"])

    recall_at_k = {
        f"recall@{k}": round(hits[k] / total, 3) if total else 0.0
        for k in K_VALUES
    }
    mean_rank = (
        round(sum(ranks_when_found) / len(ranks_when_found), 2)
        if ranks_when_found else None
    )
    return {
        "n_gold_codes": total,
        "n_found_in_top50": hits[MAX_K],
        **recall_at_k,
        "mean_rank_when_found": mean_rank,
    }


def write_markdown(out_path: Path, summary: dict, per_form: list[dict]) -> None:
    lines = [
        "# ICD-10 Retrieval — Recall@k",
        "",
        f"**Tarih:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**Veri seti:** v2 sentetik ({summary['n_forms']} form, "
        f"{summary['aggregate']['n_gold_codes']} gold kod)",
        "",
        "## Aggregate",
        "",
        "| Metrik | Değer |",
        "|---|---:|",
    ]
    for k in K_VALUES:
        lines.append(f"| Recall@{k} | {summary['aggregate'][f'recall@{k}']:.3f} |")
    mr = summary['aggregate']['mean_rank_when_found']
    lines.append(f"| Ortalama rank (bulunduğunda) | {mr if mr is not None else 'N/A'} |")
    lines.append("")
    lines.append("## Per-form (Recall@10)")
    lines.append("")
    lines.append("| Form | Gold codes | Bulunan @10 | Recall@10 |")
    lines.append("|---|---:|---:|---:|")
    for r in per_form:
        n_total = len(r["per_code"])
        n_at10 = sum(1 for c in r["per_code"] if c["found_at_k"][10])
        rec = round(n_at10 / n_total, 3) if n_total else 0.0
        lines.append(f"| {r['form_id']} | {n_total} | {n_at10} | {rec:.3f} |")
    out_path.write_text("\n".join(lines), encoding="utf-8")


async def main(data_dir: Path, form_ids: list[str], profile: str | None = None,
               label: str = "default") -> None:
    DEFAULT_OUT_DIR.mkdir(parents=True, exist_ok=True)

    from apps.backend.src.services.icd10_vector_service import ICD10VectorService
    from apps.backend.src.services.embedding_config import get_profile

    vec_svc = ICD10VectorService()
    if profile:
        vec_svc._profile = get_profile(profile)
    await vec_svc.initialize()
    logger.info("ICD10 vector service ready (profile=%s)",
                vec_svc._profile.name)

    results = []
    for fid in form_ids:
        logger.info("--- FORM %s ---", fid)
        try:
            r = await evaluate_form(vec_svc, fid, data_dir)
        except Exception:
            logger.exception("FORM %s eval FAILED", fid)
            continue
        n_total = len(r["per_code"])
        n_at10 = sum(1 for c in r["per_code"] if c["found_at_k"][10])
        logger.info("  recall@10 = %d/%d", n_at10, n_total)
        results.append(r)

    agg = aggregate(results)
    summary = {
        "n_forms": len(results),
        "profile": vec_svc._profile.name,
        "k_values": K_VALUES,
        "aggregate": agg,
    }
    logger.info("=== SUMMARY ===\n%s", json.dumps(summary, indent=2, ensure_ascii=False))

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = DEFAULT_OUT_DIR / f"recall_at_k_{ts}_{label}.json"
    md_path = DEFAULT_OUT_DIR / f"recall_at_k_{ts}_{label}.md"
    json_path.write_text(
        json.dumps({"summary": summary, "per_form": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_markdown(md_path, summary, results)
    logger.info("Wrote %s", json_path)
    logger.info("Wrote %s", md_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--form-ids", nargs="+", default=DEFAULT_FORM_IDS)
    parser.add_argument("--profile", default=None,
                        help="Override embedding profile (e.g. bge-m3, bge-m3-dahiliye)")
    parser.add_argument("--label", default="default",
                        help="Label appended to output filenames")
    args = parser.parse_args()
    asyncio.run(main(args.data_dir, args.form_ids, args.profile, args.label))
