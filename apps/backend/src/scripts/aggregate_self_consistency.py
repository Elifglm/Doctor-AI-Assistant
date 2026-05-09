"""Self-consistency aggregator — Phase 3.1.

Reads N rounds of sub-agent outputs for the same form, applies majority vote
(threshold ≥k) and writes the consensus output.

Usage:
  python -m apps.backend.src.scripts.aggregate_self_consistency \
      --rounds data/subagent_outputs_synonym data/subagent_outputs_synonym_r2 data/subagent_outputs_synonym_r3 \
      --out data/subagent_outputs_sc_t2 \
      --threshold 2

A code is included in the consensus if it appears in ≥threshold rounds.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
FORM_IDS = [f"T{i:02d}" for i in range(1, 21)]


def _extract_codes(payload, key="icd_kodu") -> list[dict]:
    """Return list of dicts with at least {key, ...} from sub-agent output.

    Handles both schemas: top-level array OR {"selected_codes": [...]}/{"mentions": [...]}.
    """
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("selected_codes") or payload.get("mentions") or payload.get("codes") or []
    else:
        return []
    return [it for it in items if isinstance(it, dict) and it.get(key)]


def aggregate_form(form_id: str, layer: str, round_dirs: list[Path], threshold: int) -> list[dict]:
    """Majority-vote aggregate one form across N rounds. Returns consensus codes."""
    suffix = "_icd_opus_output.json" if layer == "icd" else "_sut_opus_output.json"
    key = "icd_kodu" if layer == "icd" else "kodu"

    code_counter: Counter = Counter()
    code_first_seen: dict[str, dict] = {}
    rounds_loaded = 0

    for rd in round_dirs:
        path = rd / f"{form_id}{suffix}"
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        rounds_loaded += 1
        items = _extract_codes(payload, key=key)
        seen_in_this_round = set()
        for it in items:
            c = (it.get(key) or "").strip()
            if not c or c in seen_in_this_round:
                continue
            seen_in_this_round.add(c)
            code_counter[c] += 1
            if c not in code_first_seen:
                code_first_seen[c] = it

    if rounds_loaded == 0:
        return []

    consensus = []
    for code, n_votes in code_counter.most_common():
        if n_votes >= threshold:
            entry = dict(code_first_seen[code])
            entry["sc_votes"] = n_votes
            entry["sc_rounds"] = rounds_loaded
            consensus.append(entry)

    return consensus


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", nargs="+", required=True,
                    help="Round output directories (relative to project root)")
    ap.add_argument("--out", required=True, help="Consensus output dir")
    ap.add_argument("--threshold", type=int, default=2, help="Min votes for inclusion")
    ap.add_argument("--layer", default="icd", choices=["icd", "sut", "both"])
    args = ap.parse_args()

    round_dirs = [PROJECT_ROOT / r for r in args.rounds]
    out_dir = PROJECT_ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    layers = ["icd", "sut"] if args.layer == "both" else [args.layer]

    summary = {}
    for layer in layers:
        suffix = "_icd_opus_output.json" if layer == "icd" else "_sut_opus_output.json"
        summary[layer] = {}
        for fid in FORM_IDS:
            consensus = aggregate_form(fid, layer, round_dirs, args.threshold)
            out_path = out_dir / f"{fid}{suffix}"
            out_path.write_text(json.dumps(consensus, ensure_ascii=False, indent=2), encoding="utf-8")
            key = "icd_kodu" if layer == "icd" else "kodu"
            summary[layer][fid] = [c.get(key) for c in consensus]

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nWritten {out_dir} (threshold={args.threshold}, rounds={len(round_dirs)})")


if __name__ == "__main__":
    if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
