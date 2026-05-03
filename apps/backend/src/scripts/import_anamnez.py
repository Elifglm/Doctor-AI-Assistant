"""Import IcAnemnez.xlsx and Tetkik.xlsx into SQLite (data/anamnez.db).

Tables:
- ic_anamnez   (38K rows, key=FORM_ID, 48 cols from IcAnemnez.xlsx)
- tetkik       (51K rows, FK FORM_ID -> ic_anamnez)

Column names are kept verbatim (Turkish, with spaces). Access via quoted
identifiers in SQL or via DataFrame columns when reading with pandas.
"""

from __future__ import annotations

import datetime as _dt
import sqlite3
import sys
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_XLSX_DIR = _PROJECT_ROOT / "data" / "Anemnez_tetkik"
_DB_PATH = _PROJECT_ROOT / "data" / "anamnez.db"

_IC_XLSX = _XLSX_DIR / "IcAnemnez.xlsx"
_TETKIK_XLSX = _XLSX_DIR / "Tetkik.xlsx"


def load_excel(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    print(f"[read] {path.name}", flush=True)
    df = pd.read_excel(path, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]

    for col in df.columns:
        if pd.api.types.is_timedelta64_dtype(df[col]):
            df[col] = df[col].astype(str).where(df[col].notna(), None)
        elif df[col].dtype == object:
            def _coerce(v):
                if isinstance(v, _dt.timedelta):
                    return str(v)
                if isinstance(v, _dt.time):
                    return v.isoformat()
                return v
            df[col] = df[col].map(_coerce)

    print(f"  -> {len(df):,} rows, {len(df.columns)} cols", flush=True)
    return df


def write_table(conn: sqlite3.Connection, df: pd.DataFrame, table: str) -> None:
    print(f"[write] {table}", flush=True)
    df.to_sql(table, conn, if_exists="replace", index=False)
    cur = conn.cursor()
    cur.execute(f'CREATE INDEX IF NOT EXISTS idx_{table}_form_id ON "{table}"("FORM_ID")')
    conn.commit()


def main() -> int:
    if not _IC_XLSX.exists() or not _TETKIK_XLSX.exists():
        print(f"Excel files not found in {_XLSX_DIR}", file=sys.stderr)
        return 1

    ic_df = load_excel(_IC_XLSX)
    tk_df = load_excel(_TETKIK_XLSX)

    if "FORM_ID" not in ic_df.columns or "FORM_ID" not in tk_df.columns:
        print("FORM_ID column missing in one of the files", file=sys.stderr)
        return 1

    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _DB_PATH.exists():
        _DB_PATH.unlink()

    with sqlite3.connect(_DB_PATH) as conn:
        write_table(conn, ic_df, "ic_anamnez")
        write_table(conn, tk_df, "tetkik")

        cur = conn.cursor()
        n_ic = cur.execute("SELECT COUNT(*) FROM ic_anamnez").fetchone()[0]
        n_tk = cur.execute("SELECT COUNT(*) FROM tetkik").fetchone()[0]
        n_join = cur.execute(
            "SELECT COUNT(DISTINCT t.FORM_ID) FROM tetkik t "
            "INNER JOIN ic_anamnez a ON a.FORM_ID = t.FORM_ID"
        ).fetchone()[0]

    size_mb = _DB_PATH.stat().st_size / (1024 * 1024)
    print(
        f"\n[done] {_DB_PATH.relative_to(_PROJECT_ROOT)} ({size_mb:.1f} MB)\n"
        f"  ic_anamnez : {n_ic:,} rows\n"
        f"  tetkik     : {n_tk:,} rows\n"
        f"  joined ids : {n_join:,} forms have at least one tetkik",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
