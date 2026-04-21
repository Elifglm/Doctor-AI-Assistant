"""Prepare 100 random anamnesis reports for ICD-10 backfill via claude.ai.

Reads IcAnemnez.xlsx + Tetkik.xlsx (joined on FORM_ID), concatenates the
clinically relevant fields into a single 'anamnez' string per report, and
writes a JSON array ready to paste into claude.ai.
"""

import json
import pandas as pd

RANDOM_SEED = 42
SAMPLE_SIZE = 100

# Field -> label shown in the concatenated text
FIELD_LABELS = {
    "HASTANIN YAKINMASI":        "YAKINMA",
    "HASTANIN ÖYKÜSÜ":           "OYKU",
    "Şikayet Başlangıç Tarihi :": "SIKAYET BASLANGIC",
    "ÖZ GEÇMİŞİ\\SOY GEÇMİŞİ":   "OZGECMIS",
    "SOYGEÇMİŞİ":                "SOYGECMIS",
    "Sigara":                    "SIGARA",
    "Alkol":                     "ALKOL",
    "Alerji":                    "ALERJI",
    "MUAYENE BULGULARI":         "MUAYENE",
    "TEDAVİ":                    "TEDAVI",
    "TEDAVİ\\SONUÇ":             "SONUC",
    "Öneri":                     "ONERI",
    "Uyarı":                     "UYARI",
}

VITAL_LABELS = {
    "Sistolik Kan Basıncı":   "SISTOLIK",
    "Diyastolik Kan Basıncı": "DIYASTOLIK",
    "Nabız":                  "NABIZ",
    "Ateş":                   "ATES",
    "SO2":                    "SO2",
    "BOY":                    "BOY",
    "KİLO":                   "KILO",
    "Ağrı skalası":           "AGRI",
}


def clean(val) -> str:
    if pd.isna(val):
        return ""
    s = str(val).strip()
    if s.lower() in ("nan", "nat", "none", ""):
        return ""
    return s


def main() -> None:
    anemnez = pd.read_excel("data/Anemnez_tetkik/IcAnemnez.xlsx")
    tetkik = pd.read_excel("data/Anemnez_tetkik/Tetkik.xlsx")

    print(f"IcAnemnez: {len(anemnez)} rows, Tetkik: {len(tetkik)} rows")

    # Only sample rows that have at least the core narrative fields
    has_core = anemnez["HASTANIN YAKINMASI"].notna() | anemnez["HASTANIN ÖYKÜSÜ"].notna()
    pool = anemnez[has_core]
    print(f"Rows with at least YAKINMA or OYKU: {len(pool)}")

    sample = pool.sample(SAMPLE_SIZE, random_state=RANDOM_SEED).reset_index(drop=True)

    # Pre-group Tetkik by FORM_ID for fast lookup
    tetkik_by_form = tetkik.groupby("FORM_ID")

    reports = []
    for idx, row in sample.iterrows():
        form_id = row["FORM_ID"]
        parts = []

        # Narrative fields
        for col, label in FIELD_LABELS.items():
            v = clean(row.get(col))
            if v:
                parts.append(f"[{label}] {v}")

        # Vitals inline (only if any value is present)
        vital_parts = []
        for col, label in VITAL_LABELS.items():
            v = clean(row.get(col))
            if v:
                vital_parts.append(f"{label}={v}")
        if vital_parts:
            parts.append("[VITAL] " + ", ".join(vital_parts))

        # Tetkikler (joined services/tests)
        if form_id in tetkik_by_form.groups:
            tetk = tetkik_by_form.get_group(form_id)
            tetkik_names = []
            for _, t in tetk.iterrows():
                ad = clean(t.get("ADI"))
                sayi = clean(t.get("SAYI"))
                if ad:
                    if sayi and sayi != "1":
                        tetkik_names.append(f"{ad} x{sayi}")
                    else:
                        tetkik_names.append(ad)
            if tetkik_names:
                parts.append("[TETKIK/HIZMET] " + ", ".join(tetkik_names))

        anamnez_text = "\n".join(parts)
        reports.append({
            "id": f"r{idx+1:03d}",
            "form_id": int(form_id),
            "anamnez": anamnez_text,
        })

    # Dump full JSON
    with open("reports_for_claude.json", "w", encoding="utf-8") as f:
        json.dump(reports, f, ensure_ascii=False, indent=2)

    # Also split into batches of 20
    for i in range(0, len(reports), 20):
        batch = reports[i:i + 20]
        with open(f"batch_{i // 20 + 1}.json", "w", encoding="utf-8") as f:
            json.dump(batch, f, ensure_ascii=False, indent=2)

    # Stats
    total_chars = sum(len(r["anamnez"]) for r in reports)
    avg = total_chars / len(reports)
    max_len = max(len(r["anamnez"]) for r in reports)
    print(f"Wrote {len(reports)} reports -> reports_for_claude.json")
    print(f"  Total chars: {total_chars}, avg={avg:.0f}, max={max_len}")
    print(f"  Split into 5 batches of 20 (batch_1.json ... batch_5.json)")

    # Print first report as preview
    print()
    print("=" * 80)
    print("PREVIEW (1st report):")
    print("=" * 80)
    print(json.dumps(reports[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
