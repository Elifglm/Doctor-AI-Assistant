"""Bootstrap 95% confidence intervals for ICD / SUT / Anamnez F1 metrics.

Why: With n=20 forms, a single F1 number (e.g. 0.46) does not reveal how
sensitive the metric is to small dataset perturbations. Bootstrap resampling
(1000 iterations, with replacement) yields a 95% CI — a defensible answer to
"is this number reliable?" in a thesis viva.

Reads existing eval JSON outputs (no pipeline re-run required):
  - data/eval_icd10/run_*.json     (per_form metrics_exact / metrics_prefix)
  - data/eval_intent/run_*.json    (per_form precision/recall/f1)
  - data/eval_anamnez/run_*.json   (per_form per_field — macro_f1 derived)

For each per-form F1 list, computes:
  - mean F1
  - 95% CI (2.5 / 97.5 percentile bootstrap)
  - standard error

Output:
  - data/eval_results/bootstrap_ci_<ts>.json
  - data/eval_results/bootstrap_ci_<ts>.md (thesis-ready markdown table)

Usage:
    python -m apps.backend.src.scripts.bootstrap_ci
    python -m apps.backend.src.scripts.bootstrap_ci --n-bootstrap 5000
"""
from __future__ import annotations

import argparse
import json
import logging
import random
from datetime import datetime
from pathlib import Path
from statistics import mean, stdev

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("bootstrap_ci")

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = PROJECT_ROOT / "data"
OUT_DIR = DATA_DIR / "eval_results"


def bootstrap_ci(values: list[float], n_iter: int = 1000,
                 seed: int = 42) -> dict:
    """Return mean + 95% CI from bootstrap resampling with replacement."""
    if not values:
        return {"n": 0, "mean": 0.0, "ci_low": 0.0, "ci_high": 0.0, "se": 0.0}

    rng = random.Random(seed)
    n = len(values)
    boot_means = []
    for _ in range(n_iter):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        boot_means.append(sum(sample) / n)
    boot_means.sort()
    lo = boot_means[int(0.025 * n_iter)]
    hi = boot_means[int(0.975 * n_iter)]
    return {
        "n": n,
        "mean": round(mean(values), 4),
        "ci_low": round(lo, 4),
        "ci_high": round(hi, 4),
        "se": round(stdev(boot_means) if len(boot_means) > 1 else 0.0, 4),
    }


def latest_runs(directory: Path, limit: int = 4) -> list[Path]:
    return sorted(directory.glob("run_*.json"), reverse=True)[:limit]


def extract_icd_f1s(run_path: Path) -> tuple[list[float], list[float], dict]:
    """Return (exact_f1_per_form, prefix_f1_per_form, label)."""
    obj = json.loads(run_path.read_text(encoding="utf-8"))
    summary = obj.get("summary", {})
    exact = [r.get("metrics_exact", {}).get("f1", 0.0)
             for r in obj.get("per_form", [])]
    prefix = [r.get("metrics_prefix", {}).get("f1", 0.0)
              for r in obj.get("per_form", [])]
    return exact, prefix, {
        "label": summary.get("label", run_path.stem),
        "validation_mode": summary.get("validation_mode", "?"),
    }


def extract_intent_f1s(run_path: Path) -> tuple[list[float], dict]:
    obj = json.loads(run_path.read_text(encoding="utf-8"))
    summary = obj.get("summary", {})
    f1s = [r.get("f1", 0.0) for r in obj.get("per_form", [])]
    return f1s, {"label": summary.get("label", run_path.stem)}


def extract_anamnez_f1s(run_path: Path) -> tuple[list[float], dict]:
    """Approximate per-form macro token-F1 from per_form per_field results."""
    obj = json.loads(run_path.read_text(encoding="utf-8"))
    summary = obj.get("summary", {})
    per_form_f1: list[float] = []
    for r in obj.get("per_form", []):
        field_f1s = [
            f.get("token_f1", 0.0)
            for f in r.get("per_field", [])
            if "token_f1" in f
        ]
        if field_f1s:
            per_form_f1.append(sum(field_f1s) / len(field_f1s))
    return per_form_f1, {"label": summary.get("label", run_path.stem)}


def write_markdown(out_path: Path, results: list[dict], n_iter: int) -> None:
    lines = [
        "# Bootstrap 95% Confidence Intervals",
        "",
        f"**Tarih:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**Bootstrap iterasyonu:** {n_iter} (with replacement, seed=42)",
        "",
        "F1 metrikleri için %95 güven aralığı. n=20 form üzerinden "
        "yerine-koymalı yeniden örnekleme (bootstrap resampling) ile hesaplandı. ",
        "Tezdeki yorumu: 'F1 = 0.46, %95 CI = [0.38, 0.54]' → metriğin gerçek "
        "değeri büyük olasılıkla bu aralıkta.",
        "",
        "## Sonuçlar",
        "",
        "| Katman | Etiket | Metrik | n | F1 (mean) | 95% CI | SE |",
        "|---|---|---|---:|---:|---|---:|",
    ]
    for r in results:
        ci = r["ci"]
        lines.append(
            f"| {r['layer']} | {r['label']} | {r['metric']} | {ci['n']} | "
            f"{ci['mean']:.3f} | [{ci['ci_low']:.3f}, {ci['ci_high']:.3f}] | "
            f"{ci['se']:.3f} |"
        )
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main(n_bootstrap: int) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []

    # ICD-10
    for run in latest_runs(DATA_DIR / "eval_icd10"):
        try:
            exact, prefix, meta = extract_icd_f1s(run)
        except Exception:
            logger.warning("skip %s", run.name)
            continue
        if exact:
            results.append({
                "layer": "ICD-10",
                "label": meta["label"],
                "metric": "exact F1",
                "source_file": run.name,
                "ci": bootstrap_ci(exact, n_iter=n_bootstrap),
            })
        if prefix:
            results.append({
                "layer": "ICD-10",
                "label": meta["label"],
                "metric": "prefix F1",
                "source_file": run.name,
                "ci": bootstrap_ci(prefix, n_iter=n_bootstrap),
            })

    # SUT intent
    for run in latest_runs(DATA_DIR / "eval_intent"):
        try:
            f1s, meta = extract_intent_f1s(run)
        except Exception:
            logger.warning("skip %s", run.name)
            continue
        if f1s:
            results.append({
                "layer": "SUT intent",
                "label": meta["label"],
                "metric": "F1",
                "source_file": run.name,
                "ci": bootstrap_ci(f1s, n_iter=n_bootstrap),
            })

    # Anamnez
    for run in latest_runs(DATA_DIR / "eval_anamnez"):
        try:
            f1s, meta = extract_anamnez_f1s(run)
        except Exception:
            logger.warning("skip %s", run.name)
            continue
        if f1s:
            results.append({
                "layer": "Anamnez",
                "label": meta["label"],
                "metric": "macro token-F1",
                "source_file": run.name,
                "ci": bootstrap_ci(f1s, n_iter=n_bootstrap),
            })

    if not results:
        logger.error("Hiç eval run JSON bulunamadı.")
        return

    logger.info("=== %d metric için CI hesaplandı ===", len(results))
    for r in results:
        ci = r["ci"]
        logger.info(
            "  %s | %s | %s: %.3f [%.3f, %.3f] (n=%d)",
            r["layer"], r["label"], r["metric"],
            ci["mean"], ci["ci_low"], ci["ci_high"], ci["n"],
        )

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = OUT_DIR / f"bootstrap_ci_{ts}.json"
    md_path = OUT_DIR / f"bootstrap_ci_{ts}.md"
    json_path.write_text(
        json.dumps(
            {"n_bootstrap": n_bootstrap, "results": results},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    write_markdown(md_path, results, n_bootstrap)
    logger.info("Wrote %s", json_path)
    logger.info("Wrote %s", md_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-bootstrap", type=int, default=1000)
    args = parser.parse_args()
    main(args.n_bootstrap)
