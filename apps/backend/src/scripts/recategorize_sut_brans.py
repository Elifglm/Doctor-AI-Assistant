"""Re-tag the 124 hospital-imported SUT codes by clinical applicability:

  * Imaging, EKG, basic blood-work, urinalysis, inflammation/coagulation,
    pre-op routine → ``her ikisi`` (relevant to both dahiliye and ortopedi)
  * Endocrine hormones, specific markers, hepatitis serology, vitamins
    → keep as ``dahiliye`` (more specialty-specific)

This runs as a follow-up to ``import_missing_sut_codes.py``. It is idempotent —
codes already tagged ``her ikisi`` or ``ortopedi`` are not touched.
"""

from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SQLITE_DB = PROJECT_ROOT / "data" / "sut_tetkik.db"
DEFAULT_CSV = PROJECT_ROOT / "data" / "missing_sut_codes.csv"

# Keywords (already-normalized: lowercase + Turkish chars folded) that flag
# a test as broadly relevant. Match against ``adi_normalized``.
SHARED_NAME_PATTERNS = re.compile(
    r"\b("
    # imaging
    r"usg|ultrason|grafi|grafisi|mamogr|doppler|tomograf|"
    r"manyetik\s+rezonans|mrg|mr|bt|"
    # cardiology / pre-op clinical
    r"ekg|eko|holter|efor|"
    # basic blood / chemistry / preoperative
    r"hemogram|tam\s+kan|kreatinin|bun|ure\s|glukoz|aclik\s+kan|"
    r"alt|ast|sgpt|sgot|alkalen|albumin|total\s+protein|"
    r"sodyum|potasyum|kalsiyum|magnezyum|fosfor|klor|elektrolit|"
    # urinalysis
    r"idrar|tam\s+idrar|"
    # inflammation / coagulation
    r"sedimantasyon|crp|sedim|protrombin|aptt|inr|d-dimer|"
    # GFR (kidney)
    r"gfr|glomerul|"
    # iron / general
    r"demir|hemoglobin|"
    r")\b",
    re.IGNORECASE,
)

# Code-prefix shortcut: anything imaging-formatted (R..., 80xxxx, 803xxx) is
# imaging and shared. The project's existing categorisation already labels
# these as RAD-* in the source data.
SHARED_CODE_PATTERNS = (
    re.compile(r"^R\d"),  # all R-prefixed imaging codes
    re.compile(r"^80[0-9]"),  # 80xxxx grafileri
    re.compile(r"^803"),  # 803xxx USG / Doppler
    re.compile(r"^530"),  # 530xxx EKG / kardiyo
    re.compile(r"^700"),  # 700xxx general işlemler
)

# Hormone / marker / serology keywords that we DELIBERATELY KEEP as dahiliye
# (over-rides the broad pattern above when both match).
DAHILIYE_ONLY_PATTERNS = re.compile(
    r"\b("
    r"tsh|t3|t4|fsh|lh|prolaktin|kortizol|insulin|c-peptid|"
    r"hba1c|hemoglobin\s+a1c|"
    r"hbsag|hbs\s|anti-hbs|anti-hcv|anti-hav|hbv|hcv|hiv|sifiliz|"
    r"vitamin\s*b12|25-hidroksi|folat|"
    r"ferritin|trans?ferin|tibc|"
    r"trigliserid|kolestrol|hdl|ldl|vldl|"
    r"ana\b|anti-ccp|ra\s+faktor|romatoid|"
    r"tumor\s+marker|cea|psa|ca\s*125|ca\s*15|ca\s*19|afp|"
    r"helikobakter|h\.\s*pylori"
    r")\b",
    re.IGNORECASE,
)


def classify(kodu: str, adi_normalized: str) -> str:
    """Return the new brans label."""
    # Specific dahiliye markers win over broad shared patterns.
    if DAHILIYE_ONLY_PATTERNS.search(adi_normalized):
        return "dahiliye"
    # Imaging by code prefix.
    for pat in SHARED_CODE_PATTERNS:
        if pat.match(kodu):
            return "her ikisi"
    # Broad shared keywords.
    if SHARED_NAME_PATTERNS.search(adi_normalized):
        return "her ikisi"
    return "dahiliye"


def update_sqlite(codes: list[str]) -> dict[str, int]:
    """Apply the classification in place. Returns counts per brans."""
    conn = sqlite3.connect(str(SQLITE_DB))
    cur = conn.cursor()
    counts: dict[str, int] = {"her ikisi": 0, "dahiliye": 0}
    for kodu in codes:
        row = cur.execute(
            "SELECT adi_normalized, brans FROM sut_tetkik WHERE kodu = ?",
            (kodu,),
        ).fetchone()
        if row is None:
            continue
        adi_norm, current = row
        # Skip if already broader (manual edits should win).
        if current == "her ikisi" or current == "ortopedi":
            counts.setdefault(current, 0)
            counts[current] += 1
            continue
        new = classify(kodu, adi_norm or "")
        if new != current:
            cur.execute("UPDATE sut_tetkik SET brans = ? WHERE kodu = ?", (new, kodu))
        counts[new] += 1
    conn.commit()
    conn.close()
    return counts


def update_openemr(codes_with_brans: list[tuple[str, str, str]]) -> int:
    """Update OpenEMR description prefix to reflect the new brans."""
    if not codes_with_brans:
        return 0
    statements = ["START TRANSACTION;"]
    for kodu, brans, kategori in codes_with_brans:
        statements.append(
            "UPDATE procedure_type SET description = '{}' "
            "WHERE procedure_code = '{}';".format(
                f"{brans} - {kategori}".replace("'", "''"),
                kodu.replace("'", "''"),
            )
        )
    statements.append("COMMIT;")
    sql = "\n".join(statements)
    proc = subprocess.run(
        [
            "docker", "exec", "-i", "klinikasistan-mysql-1",
            "mariadb", "-uopenemr", "-popenemr", "openemr",
        ],
        input=sql.encode("utf-8"),
        capture_output=True,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr.decode(errors="replace"))
        sys.exit("OpenEMR update hatasi.")
    return len(codes_with_brans)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, nargs="?", default=DEFAULT_CSV)
    parser.add_argument("--skip-openemr", action="store_true")
    args = parser.parse_args()

    if not args.csv.exists():
        sys.exit(f"CSV bulunamadi: {args.csv}")

    with args.csv.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    codes = [r["kodu"] for r in rows]
    print(f"Yeniden siniflandirilacak kod sayisi: {len(codes)}\n")

    counts = update_sqlite(codes)
    print("[1/2] SQLite guncellendi:")
    for brans, n in sorted(counts.items()):
        print(f"   {brans}: {n}")

    if args.skip_openemr:
        print("\n[2/2] OpenEMR atlandi.")
        return

    # Re-read from SQLite to get the post-update brans for OpenEMR sync.
    conn = sqlite3.connect(str(SQLITE_DB))
    rows_db = conn.execute(
        "SELECT kodu, brans, ana_kategori FROM sut_tetkik WHERE kodu IN ({})".format(
            ",".join("?" * len(codes))
        ),
        codes,
    ).fetchall()
    conn.close()
    n = update_openemr(rows_db)
    print(f"\n[2/2] OpenEMR description guncellendi: {n} kod\n")
    print("Vector index'i tekrar olustur:")
    print("   python -m apps.backend.src.scripts.build_sut_vectors")


if __name__ == "__main__":
    main()
