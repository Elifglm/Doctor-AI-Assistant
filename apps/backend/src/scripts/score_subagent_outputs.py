"""Score sub-agent outputs against gold standards (ICD-10 + SUT).

Compares two configurations side-by-side and reports P/R/F1 deltas.

Usage:
  python -m apps.backend.src.scripts.score_subagent_outputs \
      --baseline data/subagent_outputs_baseline_v1 \
      --target   data/subagent_outputs_hyde \
      --gold     data/eval_synthetic
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[4]
FORM_IDS = [f"T{i:02d}" for i in range(1, 21)]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_icd(code: str) -> str:
    """Strip whitespace, uppercase."""
    return (code or "").strip().upper()


def _icd_prefix3(code: str) -> str:
    """E11.9 → E11; D50 → D50."""
    code = _normalize_icd(code)
    return code.split(".")[0]


def _extract_system_icd(payload: Any) -> set[str]:
    """Handle multiple sub-agent output schemas."""
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("selected_codes") or payload.get("codes") or []
    else:
        return set()
    return {_normalize_icd(it.get("icd_kodu", "")) for it in items if it.get("icd_kodu")}


def _extract_system_sut(payload: Any) -> set[str]:
    """Handle multiple sub-agent output schemas."""
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("mentions") or payload.get("selected_codes") or []
    else:
        return set()
    return {(it.get("kodu") or "").strip() for it in items if it.get("kodu")}


def _extract_gold_icd(form_id: str, gold_dir: Path) -> set[str]:
    p = gold_dir / f"gold_{form_id}_icd10.json"
    if not p.exists():
        return set()
    data = _load_json(p)
    codes = data.get("expected_codes") or data.get("icd10_list") or []
    return {_normalize_icd(c.get("icd_kodu", "")) for c in codes if isinstance(c, dict) and c.get("icd_kodu")}


def _extract_gold_sut(form_id: str, gold_dir: Path) -> set[str]:
    p = gold_dir / f"gold_{form_id}_intent.json"
    if not p.exists():
        return set()
    data = _load_json(p)
    mentions = data.get("mentions") or []
    return {
        (m.get("sut_kodu") or "").strip()
        for m in mentions
        if m.get("include") is True and m.get("sut_kodu")
    }


def _prf(predicted: set, expected: set) -> tuple[float, float, float]:
    if not predicted and not expected:
        return 1.0, 1.0, 1.0
    tp = len(predicted & expected)
    p = tp / len(predicted) if predicted else 0.0
    r = tp / len(expected) if expected else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    return p, r, f1


def _score_dir(out_dir: Path, gold_dir: Path) -> dict:
    """Return per-form scores + aggregate (micro+macro)."""
    icd_exact = []
    icd_pre3 = []
    sut = []

    icd_tp_exact = icd_fp_exact = icd_fn_exact = 0
    icd_tp_pre3 = icd_fp_pre3 = icd_fn_pre3 = 0
    sut_tp = sut_fp = sut_fn = 0

    per_form = {}

    for fid in FORM_IDS:
        # ICD
        gold = _extract_gold_icd(fid, gold_dir)
        sys_path = out_dir / f"{fid}_icd_opus_output.json"
        sys_codes = _extract_system_icd(_load_json(sys_path)) if sys_path.exists() else set()
        p, r, f1 = _prf(sys_codes, gold)
        icd_exact.append((p, r, f1))
        icd_tp_exact += len(sys_codes & gold)
        icd_fp_exact += len(sys_codes - gold)
        icd_fn_exact += len(gold - sys_codes)

        # ICD prefix-3
        gold_p3 = {_icd_prefix3(c) for c in gold}
        sys_p3 = {_icd_prefix3(c) for c in sys_codes}
        p3, r3, f3 = _prf(sys_p3, gold_p3)
        icd_pre3.append((p3, r3, f3))
        icd_tp_pre3 += len(sys_p3 & gold_p3)
        icd_fp_pre3 += len(sys_p3 - gold_p3)
        icd_fn_pre3 += len(gold_p3 - sys_p3)

        # SUT
        gold_s = _extract_gold_sut(fid, gold_dir)
        sys_path_s = out_dir / f"{fid}_sut_opus_output.json"
        sys_s = _extract_system_sut(_load_json(sys_path_s)) if sys_path_s.exists() else set()
        ps, rs, fs = _prf(sys_s, gold_s)
        sut.append((ps, rs, fs))
        sut_tp += len(sys_s & gold_s)
        sut_fp += len(sys_s - gold_s)
        sut_fn += len(gold_s - sys_s)

        per_form[fid] = {
            "icd_exact": {"p": round(p, 3), "r": round(r, 3), "f1": round(f1, 3),
                          "gold": sorted(gold), "system": sorted(sys_codes)},
            "icd_prefix3": {"p": round(p3, 3), "r": round(r3, 3), "f1": round(f3, 3)},
            "sut": {"p": round(ps, 3), "r": round(rs, 3), "f1": round(fs, 3),
                    "gold": sorted(gold_s), "system": sorted(sys_s)},
        }

    def _macro(triples: list) -> dict:
        if not triples:
            return {"p": 0.0, "r": 0.0, "f1": 0.0}
        n = len(triples)
        return {
            "p": round(sum(p for p, _, _ in triples) / n, 4),
            "r": round(sum(r for _, r, _ in triples) / n, 4),
            "f1": round(sum(f for _, _, f in triples) / n, 4),
        }

    def _micro(tp: int, fp: int, fn: int) -> dict:
        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        return {"p": round(p, 4), "r": round(r, 4), "f1": round(f1, 4),
                "tp": tp, "fp": fp, "fn": fn}

    return {
        "per_form": per_form,
        "aggregate": {
            "icd_exact_macro": _macro(icd_exact),
            "icd_exact_micro": _micro(icd_tp_exact, icd_fp_exact, icd_fn_exact),
            "icd_prefix3_macro": _macro(icd_pre3),
            "icd_prefix3_micro": _micro(icd_tp_pre3, icd_fp_pre3, icd_fn_pre3),
            "sut_macro": _macro(sut),
            "sut_micro": _micro(sut_tp, sut_fp, sut_fn),
        },
    }


def _compare(baseline: dict, target: dict) -> None:
    print("\n" + "=" * 80)
    print("AGGREGATE COMPARISON: baseline vs target")
    print("=" * 80)
    keys = ["icd_exact_macro", "icd_exact_micro", "icd_prefix3_macro",
            "icd_prefix3_micro", "sut_macro", "sut_micro"]
    print(f"{'metric':<24} {'baseline':<28} {'target':<28} {'delta_F1':>10}")
    print("-" * 90)
    for k in keys:
        b = baseline["aggregate"][k]
        t = target["aggregate"][k]
        delta = t["f1"] - b["f1"]
        sign = "+" if delta >= 0 else ""
        b_str = f"P={b['p']} R={b['r']} F1={b['f1']}"
        t_str = f"P={t['p']} R={t['r']} F1={t['f1']}"
        print(f"{k:<24} {b_str:<28} {t_str:<28} {sign}{delta:.4f}")

    print("\n" + "=" * 80)
    print("PER-FORM DELTA (F1 only)")
    print("=" * 80)
    print(f"{'form':<6} {'icd_exact_b':>11} {'icd_exact_t':>11} {'Δ':>8} | "
          f"{'icd_p3_b':>9} {'icd_p3_t':>9} {'Δ':>8} | "
          f"{'sut_b':>7} {'sut_t':>7} {'Δ':>8}")
    print("-" * 110)
    for fid in FORM_IDS:
        b = baseline["per_form"].get(fid, {})
        t = target["per_form"].get(fid, {})
        b_ie = b.get("icd_exact", {}).get("f1", 0)
        t_ie = t.get("icd_exact", {}).get("f1", 0)
        b_ip = b.get("icd_prefix3", {}).get("f1", 0)
        t_ip = t.get("icd_prefix3", {}).get("f1", 0)
        b_s = b.get("sut", {}).get("f1", 0)
        t_s = t.get("sut", {}).get("f1", 0)
        d_ie = t_ie - b_ie
        d_ip = t_ip - b_ip
        d_s = t_s - b_s
        print(f"{fid:<6} {b_ie:>11.3f} {t_ie:>11.3f} {d_ie:>+8.3f} | "
              f"{b_ip:>9.3f} {t_ip:>9.3f} {d_ip:>+8.3f} | "
              f"{b_s:>7.3f} {t_s:>7.3f} {d_s:>+8.3f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", default="data/subagent_outputs_baseline_v1")
    ap.add_argument("--target", default="data/subagent_outputs_hyde")
    ap.add_argument("--gold", default="data/eval_synthetic")
    ap.add_argument("--save", default=None, help="Optional output JSON path")
    args = ap.parse_args()

    base_dir = PROJECT_ROOT / args.baseline
    targ_dir = PROJECT_ROOT / args.target
    gold_dir = PROJECT_ROOT / args.gold

    print(f"Baseline: {base_dir}")
    print(f"Target:   {targ_dir}")
    print(f"Gold:     {gold_dir}")

    baseline = _score_dir(base_dir, gold_dir)
    target = _score_dir(targ_dir, gold_dir)

    print("\n--- BASELINE AGGREGATE ---")
    print(json.dumps(baseline["aggregate"], indent=2, ensure_ascii=False))
    print("\n--- TARGET AGGREGATE ---")
    print(json.dumps(target["aggregate"], indent=2, ensure_ascii=False))

    _compare(baseline, target)

    if args.save:
        out = {"baseline": baseline, "target": target,
               "baseline_dir": str(base_dir), "target_dir": str(targ_dir)}
        Path(args.save).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nSaved full results to: {args.save}")


if __name__ == "__main__":
    if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
