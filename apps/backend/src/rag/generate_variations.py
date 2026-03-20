"""Generate 500+ anamnesis variations from core scenarios (Hospital HBYS format).

Reads anamnez_core_scenarios.json and produces anamnez_variations.json
by varying patient demographics, severity, comorbidities, and medication details.

Usage:
    python -m apps.backend.src.rag.generate_variations

Output:
    data/rag/anamnez_variations.json
"""

from __future__ import annotations

import copy
import json
import random
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parents[3]
_CORE_FILE = _SCRIPT_DIR / "anamnez_core_scenarios.json"
_OUTPUT_FILE = _PROJECT_ROOT / "data" / "rag" / "anamnez_variations.json"

# ---------------------------------------------------------------------------
# Variation pools
# ---------------------------------------------------------------------------

OCCUPATIONS_MALE = [
    "Muhasebeci", "Mühendis", "Şoför", "Esnaf", "Memur", "İşçi",
    "Öğretmen", "Çiftçi", "Teknisyen", "Avukat", "Emekli", "Berber",
    "Garson", "Güvenlik görevlisi", "Satış elemanı", "Depo görevlisi",
]

OCCUPATIONS_FEMALE = [
    "Öğretmen", "Hemşire", "Ev hanımı", "Sekreter", "Eczacı",
    "Muhasebeci", "Avukat", "Satış elemanı", "Kuaför", "Diyetisyen",
    "Emekli", "Bankacı", "Akademisyen", "Sosyal hizmet uzmanı",
]

SMOKING_STATUSES = [
    "KULLANMIYOR",
    "KULLANIYOR ({amount}, {years} YILDIR)",
    "BIRAKMIŞ ({quit_years} YIL ÖNCE, {years} YIL {amount} İÇMİŞ)",
]

SMOKING_AMOUNTS = [
    "5-6 ADET/GÜN", "YARIM PAKET/GÜN", "1 PAKET/GÜN", "1.5 PAKET/GÜN",
]

ALCOHOL_STATUSES = [
    "KULLANMIYOR",
    "SOSYAL DÜZEYDE",
    "NADİR",
    "KULLANIYOR (HAFTADA 2-3 KEZ BİRA)",
    "KULLANIYOR (HAFTADA 1-2 KADEH ŞARAP)",
]

ALLERGY_OPTIONS = [
    "",
    "PENİSİLİN (ÜRTİKER)",
    "SULFONAMİD (DÖKÜNTÜ)",
    "NSAID (İBUPROFEN)",
    "POLEN",
    "POLEN + NİKEL",
    "EV TOZU AKARI",
]

COMORBIDITIES = [
    {"name": "HT", "detail": "HT ({years} YILDIR)", "med": "AMLODİPİN 5 MG 1X1"},
    {"name": "DM", "detail": "DM ({years} YILDIR)", "med": "METFORMİN 1000 MG 2X1"},
    {"name": "HİPERLİPİDEMİ", "detail": "HİPERLİPİDEMİ ({years} YILDIR)", "med": "ATORVASTATİN 20 MG GECE"},
    {"name": "HİPOTİROİDİ", "detail": "HİPOTİROİDİ ({years} YILDIR)", "med": "LEVOTİROKSİN 50 MCG 1X1"},
    {"name": "ASTIM", "detail": "ASTIM ({years} YILDIR)", "med": "SALBUTAMOL İNH SOS"},
    {"name": "GÖRH", "detail": "GÖRH ({years} YILDIR)", "med": "OMEPRAZOL 20 MG 1X1"},
]

FAMILY_MEMBERS = ["ANNE", "BABA", "KARDEŞ", "AMCA", "DAYI", "TEYZE"]
FAMILY_DISEASES = [
    "HT", "DM", "KAH", "İNME", "ASTIM", "KANSER", "KBH", "HİPERLİPİDEMİ",
    "KOAH", "MİGREN", "OBEZİTE",
]

DURATION_REPLACEMENTS = {
    "1 HAFTADIR": {"mild": "3 GÜNDÜR", "severe": "2 HAFTADIR"},
    "2 HAFTADIR": {"mild": "1 HAFTADIR", "severe": "3 HAFTADIR"},
    "1 AYDIR": {"mild": "2 HAFTADIR", "severe": "2 AYDIR"},
    "2 AYDIR": {"mild": "1 AYDIR", "severe": "3 AYDIR"},
    "3 AYDIR": {"mild": "1 AYDIR", "severe": "6 AYDIR"},
    "3 GÜNDÜR": {"mild": "2 GÜNDÜR", "severe": "5 GÜNDÜR"},
    "5 GÜNDÜR": {"mild": "3 GÜNDÜR", "severe": "1 HAFTADIR"},
    "1 HAFTA ÖNCE": {"mild": "3 GÜN ÖNCE", "severe": "2 HAFTA ÖNCE"},
    "2 HAFTA ÖNCE": {"mild": "1 HAFTA ÖNCE", "severe": "3 HAFTA ÖNCE"},
    "1 AY ÖNCE": {"mild": "2 HAFTA ÖNCE", "severe": "2 AY ÖNCE"},
    "2 AY ÖNCE": {"mild": "1 AY ÖNCE", "severe": "3 AY ÖNCE"},
    "3 AY ÖNCE": {"mild": "1 AY ÖNCE", "severe": "6 AY ÖNCE"},
    "3 GÜN ÖNCE": {"mild": "2 GÜN ÖNCE", "severe": "5 GÜN ÖNCE"},
    "5 GÜN ÖNCE": {"mild": "3 GÜN ÖNCE", "severe": "1 HAFTA ÖNCE"},
    "10 GÜN ÖNCE": {"mild": "5 GÜN ÖNCE", "severe": "2 HAFTA ÖNCE"},
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _random_age(base_age: int) -> int:
    delta = random.randint(-15, 15)
    return max(18, min(90, base_age + delta))


def _vary_weight_height(base_kilo: str, base_boy: str, new_age: int, gender: str) -> tuple[str, str]:
    try:
        k = int(base_kilo)
        b = int(base_boy)
    except (ValueError, TypeError):
        return base_kilo, base_boy
    k_delta = random.randint(-10, 10)
    b_delta = random.randint(-8, 8)
    new_k = max(40, min(130, k + k_delta))
    new_b = max(148, min(195, b + b_delta))
    return str(new_k), str(new_b)


def _vary_vitals(sections: dict, severity: str) -> dict:
    """Slightly modify vital signs based on severity."""
    vital_keys = ["sistolik", "diyastolik", "nabiz"]
    for key in vital_keys:
        if key in sections and sections[key]:
            try:
                val = int(sections[key])
                if severity == "mild":
                    val = int(val * random.uniform(0.92, 0.98))
                elif severity == "severe":
                    val = int(val * random.uniform(1.03, 1.10))
                else:
                    val = int(val * random.uniform(0.96, 1.04))
                sections[key] = str(val)
            except ValueError:
                pass
    return sections


def _vary_smoking(gender: str, age: int) -> str:
    template = random.choice(SMOKING_STATUSES)
    if "KULLANIYOR" in template and "{" in template:
        amount = random.choice(SMOKING_AMOUNTS)
        years = random.randint(3, max(4, age - 18))
        return template.format(amount=amount, years=years)
    elif "BIRAKMIŞ" in template:
        amount = random.choice(SMOKING_AMOUNTS)
        years = random.randint(5, max(6, age - 20))
        quit_years = random.randint(1, 10)
        return template.format(amount=amount, years=years, quit_years=quit_years)
    return template


def _vary_alcohol() -> str:
    return random.choice(ALCOHOL_STATUSES)


def _vary_allergy() -> str:
    return random.choice(ALLERGY_OPTIONS)


def _vary_family_history() -> str:
    n = random.randint(0, 3)
    if n == 0:
        return "ÖZELLİK YOK"
    members = random.sample(FAMILY_MEMBERS, min(n, len(FAMILY_MEMBERS)))
    diseases = random.sample(FAMILY_DISEASES, min(n, len(FAMILY_DISEASES)))
    parts = [f"{m} {d}" for m, d in zip(members, diseases)]
    return " ---- ".join(parts)


def _add_comorbidity(oz_gecmisi: str, n: int = 1) -> str:
    selected = random.sample(COMORBIDITIES, min(n, len(COMORBIDITIES)))
    additions = []
    for c in selected:
        if c["name"] not in oz_gecmisi.upper():
            years = random.randint(2, 15)
            detail = c["detail"].format(years=years)
            additions.append(detail)
    if not additions:
        return oz_gecmisi
    if "///" in oz_gecmisi:
        parts = oz_gecmisi.split("///")
        med_parts = []
        for c in selected:
            if c["name"] not in oz_gecmisi.upper():
                med_parts.append(c["med"])
        new_oz = parts[0].rstrip() + " ---- " + " ---- ".join(additions)
        new_med = parts[1].strip()
        if med_parts:
            new_med += " + " + " + ".join(med_parts)
        return f"{new_oz} /// {new_med}"
    else:
        return oz_gecmisi.rstrip() + " ---- " + " ---- ".join(additions)


def _modify_duration(text: str, severity: str) -> str:
    if not text:
        return text
    for original, variants in DURATION_REPLACEMENTS.items():
        if original in text and severity in variants:
            text = text.replace(original, variants[severity], 1)
    return text


def generate_variation(base: dict, variation_idx: int, severity: str = "moderate") -> dict:
    var = copy.deepcopy(base)
    base_age = var["patient"]["age"]
    base_gender = var["patient"]["gender"]

    # Gender flip (30% chance, skip gender-specific scenarios)
    gender_specific = {"dahiliye_006"}  # anemi + menometroraji
    if random.random() < 0.3 and var["id"] not in gender_specific:
        new_gender = "kadın" if base_gender == "erkek" else "erkek"
    else:
        new_gender = base_gender

    new_age = _random_age(base_age)
    var["patient"]["age"] = new_age
    var["patient"]["gender"] = new_gender
    var["id"] = f"{base['id']}_v{variation_idx:03d}"

    sections = var["sections"]

    # Modify durations
    sections["hastanin_oykusu"] = _modify_duration(sections["hastanin_oykusu"], severity)
    sections["sikayet_baslangic_tarihi"] = _modify_duration(
        sections.get("sikayet_baslangic_tarihi", ""), severity
    )

    # Vary vitals
    sections = _vary_vitals(sections, severity)

    # Vary weight/height
    sections["kilo"], sections["boy"] = _vary_weight_height(
        sections.get("kilo", ""), sections.get("boy", ""),
        new_age, new_gender,
    )

    # Vary smoking (50% chance)
    if random.random() < 0.5:
        sections["sigara"] = _vary_smoking(new_gender, new_age)

    # Vary alcohol (40% chance)
    if random.random() < 0.4:
        sections["alkol"] = _vary_alcohol()

    # Vary allergy (30% chance)
    if random.random() < 0.3:
        sections["alerji"] = _vary_allergy()

    # Vary family history (50% chance)
    if random.random() < 0.5:
        sections["soy_gecmisi"] = _vary_family_history()

    # Add comorbidity (35% chance)
    if random.random() < 0.35:
        n_extra = random.randint(1, 2)
        sections["oz_gecmisi_soy_gecmisi"] = _add_comorbidity(
            sections["oz_gecmisi_soy_gecmisi"], n_extra
        )

    var["sections"] = sections
    var["severity"] = severity
    return var


def generate_all_variations(core_scenarios: list[dict], target_count: int = 500) -> list[dict]:
    all_scenarios: list[dict] = []

    # Include originals
    for s in core_scenarios:
        sc = copy.deepcopy(s)
        sc["severity"] = "moderate"
        all_scenarios.append(sc)

    remaining = target_count - len(core_scenarios)
    per_scenario = remaining // len(core_scenarios)
    extra = remaining % len(core_scenarios)
    severities = ["mild", "moderate", "severe"]

    for i, base in enumerate(core_scenarios):
        n_vars = per_scenario + (1 if i < extra else 0)
        for v in range(n_vars):
            severity = severities[v % len(severities)]
            variation = generate_variation(base, v + 1, severity)
            all_scenarios.append(variation)

    random.shuffle(all_scenarios)
    logger.info(
        "Generated %d total scenarios (%d core + %d variations)",
        len(all_scenarios), len(core_scenarios),
        len(all_scenarios) - len(core_scenarios),
    )
    return all_scenarios


def main() -> None:
    random.seed(42)

    if not _CORE_FILE.exists():
        logger.error("Core scenarios file not found: %s", _CORE_FILE)
        return

    with open(_CORE_FILE, encoding="utf-8") as f:
        core = json.load(f)

    logger.info("Loaded %d core scenarios from %s", len(core), _CORE_FILE.name)

    all_scenarios = generate_all_variations(core, target_count=500)

    _OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_scenarios, f, ensure_ascii=False, indent=2)

    logger.info("Wrote %d scenarios to %s", len(all_scenarios), _OUTPUT_FILE)


if __name__ == "__main__":
    main()
