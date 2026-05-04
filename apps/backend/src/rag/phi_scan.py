"""Defense-in-depth PHI bulk scan over data/anamnez.db ic_anamnez table.

Reuses regex patterns from `deid_service.DeIDService` (TC kimlik, telefon,
e-mail) plus Pascal-case Turkish name bigram. Counts matches per field;
NEVER logs match contents (PHI safety rule from CLAUDE.md). Writes only
aggregated counts to console and to DAHILIYE_RAG_PLAN.md log section.

Expected outcome based on prior 500-row scan: 0 hits across all fields.
Anomalies (any non-zero count) require user decision before embedding.
"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

from apps.backend.src.services.deid_service import (
    DeIdentificationService as DeIDService,
    _valid_tc_kimlik,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DB_PATH = _PROJECT_ROOT / "data" / "anamnez.db"

_TEXT_FIELDS: tuple[str, ...] = (
    "HASTANIN YAKINMASI",
    "HASTANIN ÖYKÜSÜ",
    "MUAYENE BULGULARI",
    "ÖZ GEÇMİŞİ\\SOY GEÇMİŞİ",
    "SOYGEÇMİŞİ",
    "Sigara",
    "Alkol",
    "Alerji",
    "TEDAVİ",
    "ÖN TANI",
    "TEDAVİ\\SONUÇ",
    "Öneri",
    "Konsültasyon muayene",
    "Konsültasyon sonuç",
    "Konsültasyon öneri",
    "Hastanın Şikayeti :",
    "Uyarı",
)

_RE_NAME_BIGRAM = re.compile(
    r"\b[A-ZÇĞİÖŞÜ][a-zçğışöü]{2,}\s+[A-ZÇĞİÖŞÜ][a-zçğışöü]{2,}\b"
)


def scan_field(values, re_tc, re_phone, re_email) -> dict[str, int]:
    counts = {"tc": 0, "tc_valid": 0, "phone": 0, "email": 0, "name_bigram": 0}
    for v in values:
        if v is None:
            continue
        text = str(v)
        for m in re_tc.findall(text):
            counts["tc"] += 1
            if _valid_tc_kimlik(m):
                counts["tc_valid"] += 1
        counts["phone"] += len(re_phone.findall(text))
        counts["email"] += len(re_email.findall(text))
        counts["name_bigram"] += len(_RE_NAME_BIGRAM.findall(text))
    return counts


def main() -> int:
    if not _DB_PATH.exists():
        print(f"DB not found: {_DB_PATH}", file=sys.stderr)
        return 1

    re_tc = DeIDService._RE_TC
    re_phone = DeIDService._RE_PHONE
    re_email = DeIDService._RE_EMAIL

    print(f"[scan] {_DB_PATH.relative_to(_PROJECT_ROOT)} | ic_anamnez", flush=True)
    print(f"[scan] regex: TC={re_tc.pattern!r}", flush=True)
    print(f"[scan] regex: PHONE={re_phone.pattern!r}", flush=True)
    print(f"[scan] regex: EMAIL={re_email.pattern!r}", flush=True)
    print(f"[scan] regex: NAME_BIGRAM={_RE_NAME_BIGRAM.pattern!r}", flush=True)
    print(f"[scan] fields: {len(_TEXT_FIELDS)}", flush=True)
    print()

    totals: dict[str, int] = {"tc": 0, "tc_valid": 0, "phone": 0, "email": 0, "name_bigram": 0}
    per_field: dict[str, dict[str, int]] = {}

    with sqlite3.connect(_DB_PATH) as conn:
        n_rows = conn.execute("SELECT COUNT(*) FROM ic_anamnez").fetchone()[0]
        print(f"[scan] rows: {n_rows:,}\n", flush=True)

        for field in _TEXT_FIELDS:
            cur = conn.execute(f'SELECT "{field}" FROM ic_anamnez')
            values = [r[0] for r in cur.fetchall()]
            counts = scan_field(values, re_tc, re_phone, re_email)
            per_field[field] = counts
            for k, v in counts.items():
                totals[k] += v
            non_null = sum(1 for v in values if v is not None and str(v).strip())
            print(
                f"  {field[:40]:<40s}  "
                f"non_null={non_null:>6,d}  "
                f"tc={counts['tc']:>3d}(valid={counts['tc_valid']:>2d})  "
                f"phone={counts['phone']:>3d}  "
                f"email={counts['email']:>3d}  "
                f"name_bigram={counts['name_bigram']:>5d}",
                flush=True,
            )

    print()
    print("=" * 70)
    print(
        f"TOTALS  tc={totals['tc']} (checksum-valid={totals['tc_valid']})  "
        f"phone={totals['phone']}  email={totals['email']}  "
        f"name_bigram={totals['name_bigram']}"
    )
    print("=" * 70)

    if totals["tc_valid"] or totals["phone"] or totals["email"]:
        print("\n[ALERT] PHI hits detected — review needed before embedding.")
        return 2
    if totals["name_bigram"] > 0:
        print(
            f"\n[INFO] {totals['name_bigram']} Pascal-case bigrams found. "
            "Most are medical terminology (e.g. 'Diabetes Mellitus'), not names. "
            "Review a sample before treating as PHI."
        )
    print("\n[ok] no TC/phone/email matches.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
