"""Build cleaned ICD-10 CSV export for 3-LLM backfill pilot (Faz 0).

Reads data/icd10.db and writes data/icd10_backfill_output/icd10_export.csv
containing all codes that are the most specific available in the Turkish
ICD-10 hierarchy:

  - every seviye-2 code, AND
  - seviye-1 codes that have no seviye-2 children (leaves like J00, R14)

Dagger (†) and asterisk (*) cross-reference symbols are stripped from the
`kod` column only; the `tani` column is left untouched (cross-references
inside the description can still help the LLM). No duplicates arise after
stripping — verified.

Run:
  python -m apps.backend.src.scripts.build_icd10_export_csv
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
DB_PATH = REPO_ROOT / "data" / "icd10.db"
OUT_PATH = REPO_ROOT / "data" / "icd10_backfill_output" / "icd10_export.csv"


def strip_refs(code: str) -> str:
    return code.replace("†", "").replace("*", "").strip()


def fetch_rows(conn: sqlite3.Connection) -> list[tuple[str, str]]:
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
    return [(strip_refs(kod), tani) for kod, tani in conn.execute(query)]


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"ICD-10 DB not found: {DB_PATH}")

    with sqlite3.connect(DB_PATH) as conn:
        rows = fetch_rows(conn)

    rows.sort(key=lambda r: r[0])

    seen: set[str] = set()
    for kod, _ in rows:
        if kod in seen:
            raise SystemExit(f"Duplicate code after strip: {kod}")
        seen.add(kod)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        w.writerow(["kod", "tani"])
        w.writerows(rows)

    print(f"Wrote {len(rows)} codes -> {OUT_PATH}")
    print(f"  J00 present: {'J00' in seen}")
    print(f"  R14 present: {'R14' in seen}")


if __name__ == "__main__":
    main()
