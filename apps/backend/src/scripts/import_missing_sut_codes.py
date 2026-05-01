"""Insert the missing-codes CSV produced by ``find_missing_sut_codes.py`` into:

  1. ``data/sut_tetkik.db`` (project SQLite — drives KlinikAsistan retrieval)
  2. OpenEMR's ``procedure_type`` table (MariaDB — drives lab-order export)

The ChromaDB vector index is rebuilt by ``build_sut_vectors.py`` afterwards.

Usage:
    python -m apps.backend.src.scripts.import_missing_sut_codes \\
        data/missing_sut_codes.csv
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SQLITE_DB = PROJECT_ROOT / "data" / "sut_tetkik.db"
DEFAULT_CSV = PROJECT_ROOT / "data" / "missing_sut_codes.csv"

OPENEMR_CONTAINER = "klinikasistan-mysql-1"
OPENEMR_DB = "openemr"
OPENEMR_USER = "openemr"
OPENEMR_PASS = "openemr"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def insert_into_sqlite(rows: list[dict[str, str]]) -> tuple[int, int]:
    """Return (inserted, skipped) counts."""
    conn = sqlite3.connect(str(SQLITE_DB))
    cur = conn.cursor()
    inserted = skipped = 0
    for r in rows:
        cur.execute("SELECT 1 FROM sut_tetkik WHERE kodu = ?", (r["kodu"],))
        if cur.fetchone():
            skipped += 1
            continue
        cur.execute(
            "INSERT INTO sut_tetkik "
            "(kodu, adi, adi_normalized, brans, ana_kategori, alt_kategori, aciklama, puan) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                r["kodu"],
                r["adi"],
                r["adi_normalized"],
                r["brans"],
                r["ana_kategori"],
                r.get("alt_kategori", ""),
                r.get("aciklama", ""),
                float(r.get("puan") or 0.0),
            ),
        )
        inserted += 1
    conn.commit()
    conn.close()
    return inserted, skipped


def insert_into_openemr(rows: list[dict[str, str]]) -> tuple[int, int]:
    """Return (inserted, skipped) counts. Uses docker exec to talk to MariaDB."""
    inserted = skipped = 0
    # Build a single SQL transaction with INSERT IGNORE to skip duplicates
    # cleanly (procedure_code has a unique implication via standard_code in
    # practice).
    statements: list[str] = ["START TRANSACTION;"]
    for r in rows:
        kodu = r["kodu"].replace("'", "''")
        adi = r["adi"].replace("'", "''")
        # description format mirrors the existing seed: "brans - kategori"
        desc = f"{r['brans']} - {r['ana_kategori']}".replace("'", "''")
        statements.append(
            "INSERT INTO procedure_type "
            "(name, lab_id, procedure_code, procedure_type, description, standard_code, activity) "
            "SELECT '{name}', 0, '{code}', 'ord', '{desc}', '{code}', 1 "
            "WHERE NOT EXISTS (SELECT 1 FROM procedure_type WHERE procedure_code='{code}');".format(
                name=adi, code=kodu, desc=desc,
            )
        )
    statements.append("COMMIT;")
    sql = "\n".join(statements)

    # Capture row counts: query before/after.
    before = _openemr_count()
    proc = subprocess.run(
        [
            "docker", "exec", "-i", OPENEMR_CONTAINER,
            "mariadb", f"-u{OPENEMR_USER}", f"-p{OPENEMR_PASS}", OPENEMR_DB,
        ],
        input=sql.encode("utf-8"),
        capture_output=True,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr.decode(errors="replace"))
        sys.exit("OpenEMR insert hatasi (yukariya bak).")
    after = _openemr_count()
    inserted = after - before
    skipped = len(rows) - inserted
    return inserted, skipped


def _openemr_count() -> int:
    proc = subprocess.run(
        [
            "docker", "exec", OPENEMR_CONTAINER,
            "mariadb", f"-u{OPENEMR_USER}", f"-p{OPENEMR_PASS}", OPENEMR_DB,
            "-sN", "-e", "SELECT COUNT(*) FROM procedure_type",
        ],
        capture_output=True,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr.decode(errors="replace"))
        sys.exit("OpenEMR sayim hatasi.")
    return int(proc.stdout.decode().strip() or 0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, nargs="?", default=DEFAULT_CSV)
    parser.add_argument(
        "--skip-openemr",
        action="store_true",
        help="OpenEMR'a yazma (sadece SQLite guncelle)",
    )
    args = parser.parse_args()

    if not args.csv.exists():
        sys.exit(f"CSV bulunamadi: {args.csv}")

    rows = _read_csv(args.csv)
    print(f"CSV'de {len(rows)} kod bulundu.")

    print("\n[1/2] SQLite (data/sut_tetkik.db)'ye yaziliyor...")
    s_in, s_sk = insert_into_sqlite(rows)
    print(f"   eklendi: {s_in}, atlandi (zaten vardi): {s_sk}")

    if args.skip_openemr:
        print("\n[2/2] OpenEMR atlandi (--skip-openemr).")
    else:
        print("\n[2/2] OpenEMR (procedure_type)'a yaziliyor...")
        try:
            o_in, o_sk = insert_into_openemr(rows)
            print(f"   eklendi: {o_in}, atlandi: {o_sk}")
        except FileNotFoundError:
            print("   docker bulunamadi — OpenEMR guncellemesi atlandi.")

    print("\nBittikten sonra vector index'i yeniden olustur:")
    print("   python -m apps.backend.src.scripts.build_sut_vectors")


if __name__ == "__main__":
    main()
