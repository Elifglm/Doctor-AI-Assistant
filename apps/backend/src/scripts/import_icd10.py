"""Import ICD-10 codes from MySQL dump into SQLite database."""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DB_DIR = _PROJECT_ROOT / "data"
_ICD10_DB_PATH = _DB_DIR / "icd10.db"

_TR_MAP = str.maketrans("ıİöÖüÜçÇşŞğĞ", "iIoOuUcCsSgG")


def normalize_turkish(text: str) -> str:
    """Normalize Turkish characters to ASCII equivalents for search."""
    return text.lower().translate(_TR_MAP)


def parse_mysql_dump(sql_path: str) -> list[tuple[str, str, str | None, int]]:
    """Parse the MySQL dump and extract ICD-10 rows."""
    with open(sql_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Find the INSERT INTO statement
    match = re.search(r"INSERT INTO `icd10_tablo` VALUES\s*(.*);", content, re.DOTALL)
    if not match:
        raise ValueError("INSERT INTO icd10_tablo VALUES not found in SQL file")

    values_str = match.group(1)

    # Parse individual tuples: ('code','desc','parent',level) or ('code','desc',NULL,level)
    rows: list[tuple[str, str, str | None, int]] = []
    pattern = re.compile(
        r"\("
        r"'((?:[^'\\]|\\.|'')*)',"    # icd_kodu
        r"'((?:[^'\\]|\\.|'')*)',"    # tani
        r"(?:'((?:[^'\\]|\\.|'')*)'|NULL),"  # ust_kod or NULL
        r"(\d+)"                        # seviye
        r"\)"
    )

    for m in pattern.finditer(values_str):
        icd_kodu = m.group(1).replace("''", "'")
        tani = m.group(2).replace("''", "'")
        ust_kod = m.group(3).replace("''", "'") if m.group(3) is not None else None
        seviye = int(m.group(4))
        rows.append((icd_kodu, tani, ust_kod, seviye))

    return rows


def create_icd10_db(rows: list[tuple[str, str, str | None, int]]) -> None:
    """Create the ICD-10 SQLite database with indexes."""
    _DB_DIR.mkdir(parents=True, exist_ok=True)

    if _ICD10_DB_PATH.exists():
        _ICD10_DB_PATH.unlink()

    conn = sqlite3.connect(str(_ICD10_DB_PATH))
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE icd10 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            icd_kodu TEXT NOT NULL,
            tani TEXT NOT NULL,
            tani_normalized TEXT NOT NULL,
            ust_kod TEXT,
            seviye INTEGER NOT NULL
        )
    """)

    for icd_kodu, tani, ust_kod, seviye in rows:
        tani_normalized = normalize_turkish(tani)
        cur.execute(
            "INSERT INTO icd10 (icd_kodu, tani, tani_normalized, ust_kod, seviye) VALUES (?, ?, ?, ?, ?)",
            (icd_kodu, tani, tani_normalized, ust_kod, seviye),
        )

    # Indexes for fast search
    cur.execute("CREATE INDEX idx_icd10_kodu ON icd10(icd_kodu)")
    cur.execute("CREATE INDEX idx_icd10_tani_normalized ON icd10(tani_normalized)")
    cur.execute("CREATE INDEX idx_icd10_seviye ON icd10(seviye)")

    conn.commit()
    conn.close()


def main(sql_path: str | None = None) -> None:
    if sql_path is None:
        if len(sys.argv) < 2:
            print("Kullanim: python -m apps.backend.src.scripts.import_icd10 <icd10.sql>")
            sys.exit(1)
        sql_path = sys.argv[1]

    print(f"SQL dosyasi okunuyor: {sql_path}")
    rows = parse_mysql_dump(sql_path)
    print(f"{len(rows)} ICD-10 kodu bulundu")

    print(f"Veritabani olusturuluyor: {_ICD10_DB_PATH}")
    create_icd10_db(rows)
    print("Tamamlandi!")

    # Quick verification
    conn = sqlite3.connect(str(_ICD10_DB_PATH))
    count = conn.execute("SELECT COUNT(*) FROM icd10").fetchone()[0]
    sample = conn.execute("SELECT icd_kodu, tani FROM icd10 LIMIT 5").fetchall()
    conn.close()

    print(f"\nDogrulama: {count} kayit")
    print("Ornek kayitlar:")
    for code, desc in sample:
        print(f"  {code}: {desc}")


if __name__ == "__main__":
    main()
