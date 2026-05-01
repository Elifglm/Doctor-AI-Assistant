"""Find SUT tetkik codes present in the hospital Excel but missing from
``data/sut_tetkik.db``, and write them to a CSV ready for import.

Usage:
    python -m apps.backend.src.scripts.find_missing_sut_codes \\
        /Users/elif/Downloads/Anemnez_tetkik/Tetkik.xlsx
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DB_PATH = PROJECT_ROOT / "data" / "sut_tetkik.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "missing_sut_codes.csv"

# Maps the hospital's HIZMET_TURU labels to the canonical SUT ana_kategori
# values already present in the project DB. Unknown service types fall back to
# "9. LABORATUVAR İŞLEMLERİ" (the broadest existing bucket).
HIZMET_TO_KATEGORI = {
    "LAB": "9.1. BİYOKİMYA LABORATUVAR İŞLEMLERİ",
    "LAB (DIŞ)": "9.1. BİYOKİMYA LABORATUVAR İŞLEMLERİ",
    "LAB-PATOLOJI": "9.B. PATOLOJI LABORATUVARI",
    "RAD-USG": "8.3. RADYOLOJİK GÖRÜNTÜLEME VE TEDAVİ",
    "RAD-RN": "8.3. RADYOLOJİK GÖRÜNTÜLEME VE TEDAVİ",
    "RAD-TOMO": "8.3.1. BİLGİSAYARLI TOMOGRAFİ (BT)",
    "RAD-MAMG": "8.3. RADYOLOJİK GÖRÜNTÜLEME VE TEDAVİ",
    "RAD-DOPPLER": "8.3. RADYOLOJİK GÖRÜNTÜLEME VE TEDAVİ",
    "RAD-MR": "8.3.2. MANYETİK REZONANS GÖRÜNTÜLEME (MRG)",
    "POL-KARDİYOLOJİ": "8.3. RADYOLOJİK GÖRÜNTÜLEME VE TEDAVİ",
    "GENEL İŞLEMLER": "GENEL TIBBI İŞLEMLER",
}

_TR_MAP = str.maketrans("ıİöÖüÜçÇşŞğĞ", "iIoOuUcCsSgG")


def normalize_tr(s: str) -> str:
    return s.lower().translate(_TR_MAP).strip() if s else ""


def load_existing_codes(db_path: Path) -> set[str]:
    if not db_path.exists():
        sys.exit(f"SUT DB not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("SELECT kodu FROM sut_tetkik").fetchall()
    conn.close()
    return {r[0].strip() for r in rows if r[0]}


def load_hospital_codes(xlsx_path: Path) -> pd.DataFrame:
    df = pd.read_excel(xlsx_path, sheet_name=0)
    # Defensive: some HBYS exports use slightly different column names.
    expected = {"KOD_TEXT", "ADI", "HIZMET_TURU"}
    missing_cols = expected - set(df.columns)
    if missing_cols:
        sys.exit(f"Hospital Excel missing columns: {missing_cols}")
    df = df[["KOD_TEXT", "ADI", "HIZMET_TURU"]].copy()
    df["KOD_TEXT"] = df["KOD_TEXT"].astype(str).str.strip()
    df["ADI"] = df["ADI"].astype(str).str.strip()
    df["HIZMET_TURU"] = df["HIZMET_TURU"].fillna("").astype(str).str.strip()
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xlsx", type=Path, help="Path to Tetkik.xlsx")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--brans",
        default="dahiliye",
        help="Branş tag for new codes (default: dahiliye)",
    )
    args = parser.parse_args()

    existing = load_existing_codes(DB_PATH)
    hospital = load_hospital_codes(args.xlsx)

    # Pick the most-frequent name per code (in case of typos / variants).
    hospital["count"] = 1
    grouped = (
        hospital.groupby("KOD_TEXT", dropna=False)
        .agg(
            adi=("ADI", lambda s: s.value_counts().index[0]),
            hizmet=("HIZMET_TURU", lambda s: s.value_counts().index[0]),
            frekans=("count", "sum"),
        )
        .reset_index()
        .rename(columns={"KOD_TEXT": "kodu"})
    )

    grouped = grouped[~grouped["kodu"].isin(existing)].copy()
    if grouped.empty:
        print("Hic eksik kod yok — projedeki SUT DB hastanenin tum kodlarini iceriyor.")
        return

    grouped = grouped.sort_values("frekans", ascending=False).reset_index(drop=True)
    grouped["adi_normalized"] = grouped["adi"].map(normalize_tr)
    grouped["brans"] = args.brans
    grouped["ana_kategori"] = grouped["hizmet"].map(
        lambda h: HIZMET_TO_KATEGORI.get(h, "9. LABORATUVAR İŞLEMLERİ")
    )
    grouped["alt_kategori"] = ""
    grouped["aciklama"] = ""
    grouped["puan"] = 0.0

    out = grouped[
        [
            "kodu",
            "adi",
            "adi_normalized",
            "brans",
            "ana_kategori",
            "alt_kategori",
            "aciklama",
            "puan",
            "hizmet",
            "frekans",
        ]
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)

    total_hospital = hospital["KOD_TEXT"].nunique()
    overlap = total_hospital - len(grouped)
    print("=" * 70)
    print(f"  Hastane unique kod sayisi : {total_hospital}")
    print(f"  Projedeki ortusen kodlar  : {overlap} (%{overlap/total_hospital*100:.1f})")
    print(f"  Eksik (eklenecek) kodlar  : {len(grouped)} (%{len(grouped)/total_hospital*100:.1f})")
    print(f"  CSV yazildi               : {args.output}")
    print("=" * 70)
    print("\nEksik kodlarin HIZMET_TURU dagilimi:")
    print(grouped["hizmet"].value_counts().to_string())
    print("\nEn sik 10 eksik kod:")
    print(out.head(10)[["kodu", "adi", "hizmet", "frekans"]].to_string(index=False))


if __name__ == "__main__":
    main()
