"""Import SUT tetkik/tahlil codes from CSV into SQLite database."""

from __future__ import annotations

import csv
import sqlite3
import sys
import unicodedata
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DB_DIR = _PROJECT_ROOT / "data"
_SUT_DB_PATH = _DB_DIR / "sut_tetkik.db"

_TR_MAP = str.maketrans("ıİöÖüÜçÇşŞğĞ", "iIoOuUcCsSgG")


def normalize_turkish(text: str) -> str:
    """Normalize Turkish characters to ASCII equivalents for search.

    NFKD + combining-mark strip is required because Python's default
    ``"İ".lower()`` yields ``"i" + U+0307`` (combining dot), not a plain
    ``"i"``. Without this strip, queries like "idrar" (5 chars) miss DB
    rows whose adi_normalized was written as "i̇drar" (6 chars).
    """
    s = unicodedata.normalize("NFKD", text.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.translate(_TR_MAP)


def parse_csv(csv_path: str) -> list[dict]:
    """Parse the SUT tetkik CSV file."""
    rows: list[dict] = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "kodu": row["KODU"].strip(),
                "adi": row["ADI"].strip(),
                "brans": row["BRANS"].strip().lower(),
                "ana_kategori": row.get("ANA_KATEGORI", "").strip(),
                "alt_kategori": row.get("ALT_KATEGORI", "").strip(),
                "aciklama": row.get("ACIKLAMA", "").strip(),
                "puan": float(row.get("PUAN", 0) or 0),
            })
    return rows


def create_sut_db(rows: list[dict]) -> None:
    """Create the SUT tetkik SQLite database with indexes."""
    _DB_DIR.mkdir(parents=True, exist_ok=True)

    if _SUT_DB_PATH.exists():
        _SUT_DB_PATH.unlink()

    conn = sqlite3.connect(str(_SUT_DB_PATH))
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE sut_tetkik (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kodu TEXT NOT NULL,
            adi TEXT NOT NULL,
            adi_normalized TEXT NOT NULL,
            brans TEXT NOT NULL,
            ana_kategori TEXT,
            alt_kategori TEXT,
            aciklama TEXT,
            puan REAL
        )
    """)

    for row in rows:
        adi_normalized = normalize_turkish(row["adi"])
        cur.execute(
            "INSERT INTO sut_tetkik (kodu, adi, adi_normalized, brans, ana_kategori, alt_kategori, aciklama, puan) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (row["kodu"], row["adi"], adi_normalized, row["brans"],
             row["ana_kategori"], row["alt_kategori"], row["aciklama"], row["puan"]),
        )

    cur.execute("CREATE INDEX idx_sut_kodu ON sut_tetkik(kodu)")
    cur.execute("CREATE INDEX idx_sut_adi_normalized ON sut_tetkik(adi_normalized)")
    cur.execute("CREATE INDEX idx_sut_brans ON sut_tetkik(brans)")

    conn.commit()
    conn.close()


def main(csv_path: str | None = None) -> None:
    if csv_path is None:
        if len(sys.argv) < 2:
            print("Kullanim: python -m apps.backend.src.scripts.import_sut_tetkik <sut_tetkik.csv>")
            sys.exit(1)
        csv_path = sys.argv[1]

    print(f"CSV dosyasi okunuyor: {csv_path}")
    rows = parse_csv(csv_path)
    print(f"{len(rows)} SUT tetkik kodu bulundu")

    print(f"Veritabani olusturuluyor: {_SUT_DB_PATH}")
    create_sut_db(rows)
    print("Tamamlandi!")

    # Quick verification
    conn = sqlite3.connect(str(_SUT_DB_PATH))
    count = conn.execute("SELECT COUNT(*) FROM sut_tetkik").fetchone()[0]
    brans_counts = conn.execute(
        "SELECT brans, COUNT(*) FROM sut_tetkik GROUP BY brans"
    ).fetchall()
    sample = conn.execute("SELECT kodu, adi, brans FROM sut_tetkik LIMIT 5").fetchall()
    conn.close()

    print(f"\nDogrulama: {count} kayit")
    for brans, cnt in brans_counts:
        print(f"  {brans}: {cnt} tetkik")
    print("Ornek kayitlar:")
    for code, name, brans in sample:
        print(f"  [{brans}] {code}: {name}")


if __name__ == "__main__":
    main()
