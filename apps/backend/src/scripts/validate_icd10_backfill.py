"""Merge claude.ai ICD-10 backfill outputs and validate against icd10.db.

Usage:
    .venv/Scripts/python.exe -m apps.backend.src.scripts.validate_icd10_backfill

Inputs:
    data/icd10_backfill_output/claude_output_batch_{1..5}.json

Outputs:
    data/icd10_backfill_output/merged.json
    data/icd10_backfill_output/validation_report.md
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT_DIR = ROOT / "data" / "icd10_backfill_output"
DB_PATH = ROOT / "data" / "icd10.db"
BATCH_GLOB = "claude_output_batch_*.json"
VALID_GUVEN = {"yuksek", "orta", "dusuk"}


def normalize_code(kod: str) -> str:
    return kod.replace("†", "").replace("*", "").strip()


def load_valid_codes() -> dict[str, str]:
    if not DB_PATH.exists():
        sys.exit(f"icd10.db not found: {DB_PATH}")
    query = """
        SELECT icd_kodu, tani FROM icd10 WHERE seviye = 2
        UNION ALL
        SELECT p.icd_kodu, p.tani FROM icd10 p
        WHERE p.seviye = 1
          AND NOT EXISTS (
            SELECT 1 FROM icd10 ch
            WHERE ch.ust_kod = p.icd_kodu AND ch.seviye = 2
          )
    """
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(query).fetchall()
    return {normalize_code(kod): tani for kod, tani in rows}


def load_batches() -> list[tuple[Path, list[dict]]]:
    files = sorted(OUT_DIR.glob(BATCH_GLOB))
    if not files:
        sys.exit(f"No batch outputs in {OUT_DIR}")
    out = []
    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            sys.exit(f"{fp.name}: invalid JSON — {e}")
        if not isinstance(data, list):
            sys.exit(f"{fp.name}: top-level must be a list")
        out.append((fp, data))
    return out


def validate(
    batches: list[tuple[Path, list[dict]]],
    valid_codes: dict[str, str],
) -> dict:
    merged: list[dict] = []
    seen_ids: dict[str, str] = {}
    duplicates: list[tuple[str, str, str]] = []
    invalid_codes: list[dict] = []
    bad_guven: list[dict] = []
    malformed: list[dict] = []
    guven_counter: Counter[str] = Counter()
    code_counter: Counter[str] = Counter()
    codes_per_report: list[int] = []

    for fp, reports in batches:
        for report in reports:
            rid = report.get("id")
            codes = report.get("codes")
            if not rid or not isinstance(codes, list):
                malformed.append({"file": fp.name, "report": report})
                continue
            if rid in seen_ids:
                duplicates.append((rid, seen_ids[rid], fp.name))
                continue
            seen_ids[rid] = fp.name

            codes_per_report.append(len(codes))
            for entry in codes:
                kod_raw = entry.get("kod")
                guven = entry.get("guven")
                if not kod_raw:
                    malformed.append({"file": fp.name, "id": rid, "entry": entry})
                    continue
                kod = normalize_code(kod_raw)
                entry["kod"] = kod
                code_counter[kod] += 1
                if guven in VALID_GUVEN:
                    guven_counter[guven] += 1
                else:
                    bad_guven.append({"id": rid, "kod": kod, "guven": guven})
                if kod not in valid_codes:
                    invalid_codes.append(
                        {
                            "id": rid,
                            "kod": kod,
                            "tani_claimed": entry.get("tani"),
                            "file": fp.name,
                        }
                    )
            merged.append(report)

    return {
        "merged": merged,
        "total_reports": len(merged),
        "total_codes": sum(code_counter.values()),
        "duplicates": duplicates,
        "invalid_codes": invalid_codes,
        "bad_guven": bad_guven,
        "malformed": malformed,
        "guven_dist": dict(guven_counter),
        "top_codes": code_counter.most_common(20),
        "codes_per_report": codes_per_report,
    }


def codes_histogram(vals: list[int]) -> dict[int, int]:
    c: Counter[int] = Counter(vals)
    return {k: c[k] for k in sorted(c)}


def write_report(res: dict, valid_codes: dict[str, str]) -> str:
    lines: list[str] = []
    w = lines.append
    w("# ICD-10 Backfill — Validation Report\n")
    w(f"- Toplam rapor: **{res['total_reports']}**")
    w(f"- Toplam kod: **{res['total_codes']}**")
    w(
        f"- Invalid kod (DB dışı): **{len(res['invalid_codes'])}**"
        f"  |  bozuk guven: **{len(res['bad_guven'])}**"
        f"  |  malformed entry: **{len(res['malformed'])}**"
        f"  |  duplicate id: **{len(res['duplicates'])}**"
    )
    w("")
    w("## Güven dağılımı")
    for k in ("yuksek", "orta", "dusuk"):
        w(f"- {k}: {res['guven_dist'].get(k, 0)}")
    w("")
    w("## Rapor başına kod sayısı")
    for n, cnt in codes_histogram(res["codes_per_report"]).items():
        w(f"- {n} kod: {cnt} rapor")
    w("")
    w("## En sık 20 kod")
    for kod, cnt in res["top_codes"]:
        tani = valid_codes.get(kod, "(DB'de yok)")
        w(f"- `{kod}` ×{cnt} — {tani}")
    w("")
    if res["invalid_codes"]:
        w("## Invalid kodlar (DB'de yok — halüsinasyon adayları)")
        for item in res["invalid_codes"]:
            w(
                f"- `{item['kod']}` (rapor {item['id']}, {item['file']}) "
                f"— Claude dedi: {item['tani_claimed']!r}"
            )
        w("")
    if res["bad_guven"]:
        w("## Geçersiz güven değerleri")
        for item in res["bad_guven"]:
            w(f"- rapor {item['id']} / `{item['kod']}` → {item['guven']!r}")
        w("")
    if res["duplicates"]:
        w("## Duplicate rapor id'leri")
        for rid, first_file, second_file in res["duplicates"]:
            w(f"- {rid}: ilk {first_file}, tekrar {second_file}")
        w("")
    if res["malformed"]:
        w(f"## Malformed entry sayısı: {len(res['malformed'])}")
        w("")
    return "\n".join(lines)


def main() -> None:
    valid_codes = load_valid_codes()
    batches = load_batches()
    res = validate(batches, valid_codes)

    (OUT_DIR / "merged.json").write_text(
        json.dumps(res["merged"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report_md = write_report(res, valid_codes)
    (OUT_DIR / "validation_report.md").write_text(report_md, encoding="utf-8")

    # Console summary (Turkish OK, but keep ASCII-safe to avoid cp1252 crash)
    print(f"Reports: {res['total_reports']}  Codes: {res['total_codes']}")
    print(
        f"Invalid: {len(res['invalid_codes'])}  "
        f"BadGuven: {len(res['bad_guven'])}  "
        f"Malformed: {len(res['malformed'])}  "
        f"Duplicates: {len(res['duplicates'])}"
    )
    print(f"Guven: {res['guven_dist']}")
    print(f"Wrote: {OUT_DIR/'merged.json'}")
    print(f"Wrote: {OUT_DIR/'validation_report.md'}")


if __name__ == "__main__":
    main()
