"""Apply ordered SQL filters under apps/backend/src/rag/filters/ to anamnez.db.

Each .sql file is idempotent (DROP TABLE + CREATE + DELETE dedup). Reports
row counts before and after each filter so we can log them in the plan
document. v3 (MinHash dedup) is applied separately by dedup_anamnez.py.
"""

from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DB_PATH = _PROJECT_ROOT / "data" / "anamnez.db"
_FILTERS_DIR = Path(__file__).parent / "filters"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _table_for_sql(sql_text: str) -> str | None:
    for line in sql_text.splitlines():
        line = line.strip()
        if line.upper().startswith("CREATE TABLE "):
            parts = line.split()
            if len(parts) >= 3:
                return parts[2].strip("\"'`;")
    return None


def main() -> int:
    if not _DB_PATH.exists():
        print(f"DB not found: {_DB_PATH}", file=sys.stderr)
        return 1

    sql_files = sorted(_FILTERS_DIR.glob("[0-9][0-9]_*.sql"))
    if not sql_files:
        print(f"No SQL files in {_FILTERS_DIR}", file=sys.stderr)
        return 1

    with sqlite3.connect(_DB_PATH) as conn:
        n_ham = conn.execute("SELECT COUNT(*) FROM ic_anamnez").fetchone()[0]
        print(f"[ham] ic_anamnez: {n_ham:,} rows\n", flush=True)

        for f in sql_files:
            sql = f.read_text(encoding="utf-8")
            table = _table_for_sql(sql)
            t0 = time.perf_counter()
            print(f"[apply] {f.name} -> table {table}", flush=True)
            conn.executescript(sql)
            conn.commit()
            elapsed = time.perf_counter() - t0
            if table and _table_exists(conn, table):
                n = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                pct = 100 * n / n_ham
                print(f"  -> {n:,} rows  ({pct:.1f}% of ham)  [{elapsed:.2f}s]", flush=True)
            else:
                print(f"  -> [WARN] table {table!r} not detected", flush=True)
            print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
