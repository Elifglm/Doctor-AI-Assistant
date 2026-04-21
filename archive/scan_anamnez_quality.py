"""Quality scan on the 38K Turkish anamnesis dataset.

Reports per-field completeness and length distribution, then counts how
many reports pass progressively stricter quality thresholds so we can
pick a sensible cut for the 'gold' subset before 3-LLM ICD labeling.

Run:
  .venv/Scripts/python.exe scan_anamnez_quality.py
"""

from __future__ import annotations

import pandas as pd

XLS = "data/Anemnez_tetkik/IcAnemnez.xlsx"

CORE_FIELDS = {
    "YAKINMA": "HASTANIN YAKINMASI",
    "OYKU": "HASTANIN ÖYKÜSÜ",
    "MUAYENE": "MUAYENE BULGULARI",
    "TEDAVI": "TEDAVİ",
    "SONUC": "TEDAVİ\\SONUÇ",
    "OZGECMIS": "ÖZ GEÇMİŞİ\\SOY GEÇMİŞİ",
}


def clean(v) -> str:
    if pd.isna(v):
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("nan", "nat", "none") else s


def pct(n: int, total: int) -> str:
    return f"{n / total * 100:5.1f}%"


def main() -> None:
    print(f"Loading {XLS} ...")
    df = pd.read_excel(XLS)
    total = len(df)
    print(f"Total rows: {total}\n")

    # Per-field char-length stats
    lengths: dict[str, pd.Series] = {}
    for alias, col in CORE_FIELDS.items():
        if col not in df.columns:
            print(f"  [!] column missing: {col!r}")
            continue
        lengths[alias] = df[col].map(clean).str.len()

    print("=" * 72)
    print("FIELD-LENGTH DISTRIBUTION (chars)")
    print("=" * 72)
    hdr = f"{'alias':10} {'non-empty':>12} {'mean':>6} {'p25':>5} {'p50':>5} {'p75':>5} {'p90':>5} {'p99':>6}"
    print(hdr)
    for alias, s in lengths.items():
        nz = s[s > 0]
        n = len(nz)
        if n == 0:
            print(f"{alias:10} {0:>12}  (all empty)")
            continue
        print(
            f"{alias:10} {n:>6} ({pct(n,total)}) "
            f"{nz.mean():>6.0f} {nz.quantile(0.25):>5.0f} "
            f"{nz.quantile(0.50):>5.0f} {nz.quantile(0.75):>5.0f} "
            f"{nz.quantile(0.90):>5.0f} {nz.quantile(0.99):>6.0f}"
        )

    # Threshold sweeps — how many reports pass stricter gold criteria?
    print()
    print("=" * 72)
    print("GOLD-SUBSET FILTERS (stricter each row)")
    print("=" * 72)

    narrative = lengths["YAKINMA"] + lengths["OYKU"]
    filters = [
        ("narrative (YAKINMA+OYKU) >= 50",
         narrative >= 50),
        ("narrative >=50 AND MUAYENE >=30",
         (narrative >= 50) & (lengths["MUAYENE"] >= 30)),
        ("narrative >=60 AND MUAYENE >=30",
         (narrative >= 60) & (lengths["MUAYENE"] >= 30)),
        ("narrative >=60 AND MUAYENE >=30 AND TEDAVI>=10",
         (narrative >= 60) & (lengths["MUAYENE"] >= 30)
         & (lengths["TEDAVI"] >= 10)),
        ("narrative >=80 AND MUAYENE >=40",
         (narrative >= 80) & (lengths["MUAYENE"] >= 40)),
        ("narrative >=80 AND MUAYENE >=40 AND TEDAVI>=10",
         (narrative >= 80) & (lengths["MUAYENE"] >= 40)
         & (lengths["TEDAVI"] >= 10)),
        ("narrative >=100 AND MUAYENE >=50 AND TEDAVI>=10",
         (narrative >= 100) & (lengths["MUAYENE"] >= 50)
         & (lengths["TEDAVI"] >= 10)),
    ]
    for label, mask in filters:
        n = int(mask.sum())
        print(f"  {label:<55} -> {n:>6} ({pct(n, total)})")

    # Sample rows: one from each tier so we can sanity-check
    print()
    print("=" * 72)
    print("SAMPLES")
    print("=" * 72)

    def show(title: str, mask: pd.Series, n: int = 1) -> None:
        sub = df[mask]
        if sub.empty:
            print(f"\n--- {title}: (0 rows) ---")
            return
        sample = sub.sample(min(n, len(sub)), random_state=7)
        for _, row in sample.iterrows():
            print(f"\n--- {title} (FORM_ID={row.get('FORM_ID')}) ---")
            for alias, col in CORE_FIELDS.items():
                v = clean(row.get(col))
                shown = v[:180] + ("..." if len(v) > 180 else "") if v else "(bos)"
                print(f"  [{alias}] {shown}")

    gold_mask = (
        (narrative >= 80) & (lengths["MUAYENE"] >= 40)
        & (lengths["TEDAVI"] >= 10)
    )
    mid_mask = (
        (narrative >= 50) & (lengths["MUAYENE"] >= 30)
        & (~gold_mask)
    )
    weak_mask = (narrative > 0) & (~gold_mask) & (~mid_mask)

    show("GOLD (narr>=80, MUAYENE>=40, TEDAVI>=10)", gold_mask, n=3)
    show("MID-QUALITY", mid_mask, n=2)
    show("WEAK", weak_mask, n=2)


if __name__ == "__main__":
    main()
