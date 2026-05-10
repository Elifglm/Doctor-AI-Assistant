"""SUT intent confusion matrix + NER recall (single-number metric).

Reads manually-reviewed gold from data/eval_intent/gold_<form>.json files.
Produces:
  1. Gold intent distribution (REQUEST / PAST_DONE / PATIENT_QUESTION /
     HYPOTHETICAL / OTHER counts)
  2. NER recall as a single number: (n_total - n_missed) / n_total
  3. Intent confusion matrix — populated from system run JSON if available,
     else from documented error categories in gold_summary.json

Reads:
  - data/eval_intent/gold_<form>.json (per-mention gold)
  - data/eval_intent/gold_summary.json (aggregate counts + error categories)
  - data/eval_intent/run_<ts>_<label>.json (optional, for full confusion matrix)

Output:
  - data/eval_intent/confusion_matrix_<ts>.json
  - data/eval_intent/confusion_matrix_<ts>.md (markdown table for thesis)

Usage:
    python -m apps.backend.src.scripts.intent_confusion_matrix
"""
from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("intent_confusion")

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_EVAL_DIR = PROJECT_ROOT / "data" / "eval_intent"
INTENT_LABELS = ["REQUEST", "PAST_DONE", "PATIENT_QUESTION", "HYPOTHETICAL", "OTHER"]


def _norm_intent(label: str) -> str:
    """Map raw intent labels to the 5-class taxonomy used in the thesis."""
    if not label:
        return "OTHER"
    label = label.strip().upper()
    if label in INTENT_LABELS:
        return label
    # Common aliases
    if label in {"REQUESTED", "ORDER", "FUTURE_REQUEST"}:
        return "REQUEST"
    if label in {"PAST", "PAST_NARRATIVE", "DONE"}:
        return "PAST_DONE"
    if label in {"QUESTION", "INTERROGATIVE"}:
        return "PATIENT_QUESTION"
    if label in {"HYPOTHESIS", "CONDITIONAL"}:
        return "HYPOTHETICAL"
    return "OTHER"


def load_gold_mentions(eval_dir: Path) -> list[dict]:
    """Load all per-mention gold entries from gold_<form>.json files."""
    mentions = []
    for path in sorted(eval_dir.glob("gold_*.json")):
        if "DRAFT" in path.name or "summary" in path.name:
            continue
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("skip %s", path.name)
            continue
        for m in obj.get("mentions", []):
            mentions.append({
                "form_id": obj.get("form_id"),
                "mention_id": m.get("id"),
                "surface_form": m.get("surface_form"),
                "canonical": m.get("canonical_tetkik"),
                "intent_gold": _norm_intent(m.get("intent_etiketi", "")),
                "missed_by_system": bool(m.get("missed_by_system", False)),
                "include": bool(m.get("include", False)),
            })
    return mentions


def gold_distribution(mentions: list[dict]) -> dict:
    counts = Counter(m["intent_gold"] for m in mentions)
    return {label: counts.get(label, 0) for label in INTENT_LABELS}


def ner_recall(mentions: list[dict]) -> dict:
    n_total = len(mentions)
    n_missed = sum(1 for m in mentions if m["missed_by_system"])
    n_detected = n_total - n_missed
    recall = round(n_detected / n_total, 3) if n_total else 0.0
    return {
        "n_total_mentions": n_total,
        "n_missed_by_ner": n_missed,
        "n_detected": n_detected,
        "ner_recall": recall,
    }


def empty_matrix() -> dict[str, dict[str, int]]:
    return {gold: {pred: 0 for pred in INTENT_LABELS} for gold in INTENT_LABELS}


def build_confusion_matrix_from_run(
    mentions: list[dict], run_path: Path
) -> dict | None:
    """If a run JSON with per-mention system intent labels exists, build the
    full 5x5 matrix. Returns None if predictions aren't recorded."""
    try:
        run = json.loads(run_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    sys_preds: dict[tuple[str, str], str] = {}
    for form in run.get("per_form", []):
        for m in form.get("system_full_output", []):
            mid = m.get("mention_id")
            intent = _norm_intent(m.get("intent", ""))
            if mid:
                sys_preds[(form.get("form_id"), mid)] = intent
    if not sys_preds:
        return None

    matrix = empty_matrix()
    matched = 0
    for m in mentions:
        if m["missed_by_system"]:
            continue
        key = (m["form_id"], m["mention_id"])
        pred = sys_preds.get(key)
        if pred is None:
            continue
        matrix[m["intent_gold"]][pred] += 1
        matched += 1
    return {"matrix": matrix, "n_matched_mentions": matched, "source": run_path.name}


def write_markdown(out_path: Path, payload: dict) -> None:
    lines = [
        "# SUT Intent — Confusion Matrix & NER Recall",
        "",
        f"**Tarih:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**Veri kaynağı:** {payload['n_forms']} manuel-incelenmiş form, "
        f"{payload['ner_recall']['n_total_mentions']} mention",
        "",
        "## NER Recall (tek sayı)",
        "",
        "| Metrik | Değer |",
        "|---|---:|",
        f"| Toplam mention | {payload['ner_recall']['n_total_mentions']} |",
        f"| NER tarafından bulunan | {payload['ner_recall']['n_detected']} |",
        f"| Kaçırılan | {payload['ner_recall']['n_missed_by_ner']} |",
        f"| **NER Recall** | **{payload['ner_recall']['ner_recall']:.3f}** |",
        "",
        "## Gold Intent Dağılımı",
        "",
        "| Intent | Adet |",
        "|---|---:|",
    ]
    for label in INTENT_LABELS:
        lines.append(f"| {label} | {payload['gold_distribution'][label]} |")
    total = sum(payload['gold_distribution'].values())
    lines.append(f"| **Toplam** | **{total}** |")
    lines.append("")

    cm = payload.get("confusion_matrix")
    lines.append("## Intent Confusion Matrix (Gold satır × System sütun)")
    lines.append("")
    if cm is None:
        lines.append("> Sistem per-mention intent tahminleri kaydedilmediği için "
                     "tam confusion matrix üretilemedi. `eval_sut_intent.py` çıktısı "
                     "her mention için `mention_id` + `intent` kaydederse otomatik "
                     "doldurulur.")
        lines.append("")
        lines.append("Şu an için elde olan: gold dağılımı + NER recall + intent "
                     "accuracy yaklaşımı (gold_summary.json'da dokümante edilmiş "
                     "13 intent hatası ile).")
    else:
        header = "| Gold \\\\ Pred | " + " | ".join(INTENT_LABELS) + " |"
        sep = "|---|" + "---|" * len(INTENT_LABELS)
        lines.append(header)
        lines.append(sep)
        for gold in INTENT_LABELS:
            row = [str(cm["matrix"][gold][pred]) for pred in INTENT_LABELS]
            lines.append(f"| **{gold}** | " + " | ".join(row) + " |")
        lines.append("")
        lines.append(f"_n_matched_mentions = {cm['n_matched_mentions']}, "
                     f"source = {cm['source']}_")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def main(eval_dir: Path) -> None:
    mentions = load_gold_mentions(eval_dir)
    if not mentions:
        logger.error("Hiç gold mention bulunamadı: %s", eval_dir)
        return

    forms = sorted({m["form_id"] for m in mentions})
    payload = {
        "n_forms": len(forms),
        "form_ids": forms,
        "ner_recall": ner_recall(mentions),
        "gold_distribution": gold_distribution(mentions),
    }

    # Try to build confusion matrix from latest run JSON
    runs = sorted(eval_dir.glob("run_*.json"), reverse=True)
    cm = None
    if runs:
        cm = build_confusion_matrix_from_run(mentions, runs[0])
    payload["confusion_matrix"] = cm

    logger.info("=== SUMMARY ===\n%s",
                json.dumps({k: v for k, v in payload.items() if k != "form_ids"},
                           indent=2, ensure_ascii=False))

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = eval_dir / f"confusion_matrix_{ts}.json"
    md_path = eval_dir / f"confusion_matrix_{ts}.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_markdown(md_path, payload)
    logger.info("Wrote %s", json_path)
    logger.info("Wrote %s", md_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-dir", type=Path, default=DEFAULT_EVAL_DIR)
    args = parser.parse_args()
    main(args.eval_dir)
