"""Seed the RAG database with anamnesis scenarios (Hospital HBYS format).

Loads anamnesis data from JSON and indexes into ChromaDB.
Adapted for the actual hospital template fields.

Usage:
    python -m apps.backend.src.rag.anamnez_seed_data
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parents[3]

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from apps.backend.src.services.rag_service import RAGService

_VARIATIONS_FILE = _PROJECT_ROOT / "data" / "rag" / "anamnez_variations.json"
_CORE_FILE = _SCRIPT_DIR / "anamnez_core_scenarios.json"


def _load_scenarios() -> list[dict]:
    if _VARIATIONS_FILE.exists():
        logger.info("Loading from %s", _VARIATIONS_FILE.name)
        with open(_VARIATIONS_FILE, encoding="utf-8") as f:
            return json.load(f)
    if _CORE_FILE.exists():
        logger.info("Falling back to %s", _CORE_FILE.name)
        with open(_CORE_FILE, encoding="utf-8") as f:
            return json.load(f)
    logger.error("No scenario files found!")
    return []


# ---------------------------------------------------------------------------
# Symptom keywords for symptom index documents
# ---------------------------------------------------------------------------

SYMPTOM_KEYWORDS: dict[str, list[str]] = {
    "I10": ["bas agrisi", "bas donmesi", "tansiyon yuksekligi", "hipertansiyon",
            "ense agrisi", "bulanik gorme", "zonklayici agri"],
    "E11": ["susuzluk", "sik idrara cikma", "poliuri", "polidipsi", "kilo kaybi",
            "halsizlik", "aclik kan sekeri yuksek", "diyabet", "seker hastaligi"],
    "J44.1": ["nefes darligi", "balgamli oksuruk", "KOAH", "wheezing", "dispne",
              "oksijen saturasyonu dusuk", "balgam"],
    "K21.0": ["mide yanmasi", "pirozis", "reflu", "agiza aci su", "regurjitasyon",
              "goguste yanma", "retrosternal yanma", "yemekten sonra artan"],
    "K29.7": ["gastrit", "mide agrisi", "epigastrik agri", "bulanti", "hazimsizlik",
              "mide sikintisi", "siskinlik"],
    "N39.0": ["idrar yanmasi", "dizuri", "sik idrara cikma", "pollakuri",
              "suprapubik agri", "idrar yolu enfeksiyonu"],
    "D50.9": ["halsizlik", "yorgunluk", "sac dokulmesi", "soluk gorunum",
              "anemi", "kansizlik", "tirnak kirilmasi", "konjunktiva soluk"],
    "E03.9": ["kilo alimi", "usume", "kabizlik", "hipotiroidi", "tiroid",
              "halsizlik", "sac dokulmesi", "cilt kurulugu"],
    "J45.9": ["nefes darligi", "oksuruk", "hisiltili solunum", "wheezing",
              "astim", "gece oksurugu", "alerjik"],
    "E78.5": ["kolesterol yuksekligi", "hiperlipidemi", "trigliserit",
              "LDL yuksek", "kolesterol"],
    "J18.9": ["ates", "oksuruk", "nefes darligi", "balgam", "pnomoni",
              "gogus agrisi", "zaturre"],
    "I25.1": ["gogus agrisi", "eforla agri", "angina", "sol kola yayilim",
              "baskinc tarzinda agri", "nefes darligi"],
    "I48": ["carpinti", "duzensiz kalp atisi", "atriyal fibrilasyon",
            "hizli kalp", "bas donmesi"],
    "E05.0": ["kilo kaybi", "carpinti", "titreme", "sicak intoleransi",
              "terleme", "hipertiroidi", "tiroid", "goz buyumesi"],
    "N18.3": ["bobrek hastaligi", "kreatinin yuksekligi", "bobrek yetersizligi",
              "bacaklarda sislik", "odem"],
    "J06.9": ["bogaz agrisi", "ates", "burun akintisi", "oksuruk",
              "ust solunum yolu", "grip", "nezle"],
    "F41.1": ["carpinti", "goguste sikisma", "uyku bozuklugu", "endise",
              "anksiyete", "panik atak", "korku"],
    "B18.1": ["hepatit B", "karaciger", "HBsAg pozitif", "sarilik"],
    "E11.65": ["diyabetik ayak", "ayakta yara", "iyilesmeyen yara",
               "enfekte ulser", "diyabet"],
    "G43.9": ["bas agrisi", "migren", "zonklayici", "bulanti", "isik hassasiyeti",
              "ses hassasiyeti", "aura", "tek tarafli agri"],
    "I50.9": ["nefes darligi", "bacaklarda sislik", "ortopne", "kalp yetersizligi",
              "odem", "yorgunluk"],
    "M54.5": ["bel agrisi", "bacaga yayilim", "lombalji", "siyatik",
              "uyusma", "karincalanma", "agir kaldirma"],
    "E66.9": ["kilo alma", "obezite", "yorgunluk", "eklem agrisi",
              "horlama", "metabolik sendrom"],
    "L30.9": ["kasinti", "kizariklik", "dokuntu", "dermatit", "cilt alerjisi",
              "egzama"],
    "E87.6": ["kas gucsuzlugu", "kramp", "hipokalemi", "potasyum dusuk",
              "halsizlik", "kabizlik", "carpinti"],
}

# Hospital HBYS field names mapped to readable titles
FIELD_TITLES: dict[str, str] = {
    "hastanin_yakinmasi": "HASTANIN YAKINMASI",
    "hastanin_oykusu": "HASTANIN ÖYKÜSÜ",
    "oz_gecmisi_soy_gecmisi": "ÖZ GEÇMİŞİ/SOY GEÇMİŞİ",
    "soy_gecmisi": "SOYGEÇMİŞİ",
    "sigara": "Sigara",
    "alkol": "Alkol",
    "alerji": "Alerji",
    "muayene_bulgulari": "MUAYENE BULGULARI",
    "tedavi": "TEDAVİ",
    "oneri": "Öneri",
    "uyari": "Uyarı",
    "kontrol_zamani": "Kontrol Zamanı",
    "icd10_list": "ICD10",
}

# Fields that should be indexed as documents (main content fields)
INDEXABLE_FIELDS = [
    "hastanin_yakinmasi",
    "hastanin_oykusu",
    "oz_gecmisi_soy_gecmisi",
    "soy_gecmisi",
    "muayene_bulgulari",
    "tedavi",
    "oneri",
    "uyari",
    "icd10_list",
]


def _build_documents(
    scenarios: list[dict],
) -> tuple[list[str], list[dict], list[str]]:
    documents: list[str] = []
    metadatas: list[dict] = []
    ids: list[str] = []
    seen_symptom_docs: set[str] = set()

    for scenario in scenarios:
        sid = scenario["id"]
        icd10_codes = scenario.get("icd10_codes", [])
        primary_icd10 = icd10_codes[0] if icd10_codes else ""
        diagnosis = scenario.get("diagnosis", "")
        department = scenario.get("department", "dahiliye")
        severity = scenario.get("severity", "moderate")
        age = scenario.get("patient", {}).get("age", 0)
        gender = scenario.get("patient", {}).get("gender", "")
        sections = scenario.get("sections", {})

        # --- Per-field documents ---
        for field_key in INDEXABLE_FIELDS:
            content = sections.get(field_key, "")
            if not content or content.strip() in ("", "BİLGİ YOK"):
                continue

            field_title = FIELD_TITLES.get(field_key, field_key)

            documents.append(content)
            metadatas.append({
                "scenario_id": sid,
                "field": field_key,
                "field_title": field_title,
                "icd10": primary_icd10,
                "diagnosis": diagnosis,
                "department": department,
                "severity": severity,
                "patient_age": str(age),
                "patient_gender": gender,
                "category": "anamnesis_field",
            })
            ids.append(f"anamnez_{sid}_{field_key}")

        # --- Vitals composite document ---
        vital_parts = []
        for vk in ["sistolik", "diyastolik", "so2", "nabiz", "ates"]:
            val = sections.get(vk, "")
            if val:
                label = {
                    "sistolik": "TA SİSTOLİK",
                    "diyastolik": "TA DİYASTOLİK",
                    "so2": "SO2",
                    "nabiz": "NABIZ",
                    "ates": "ATEŞ",
                }.get(vk, vk)
                vital_parts.append(f"{label}: {val}")
        if vital_parts:
            vital_text = " , ".join(vital_parts)
            kilo = sections.get("kilo", "")
            boy = sections.get("boy", "")
            if kilo:
                vital_text += f" , KİLO: {kilo}"
            if boy:
                vital_text += f" , BOY: {boy}"
            documents.append(vital_text)
            metadatas.append({
                "scenario_id": sid,
                "field": "vitals",
                "field_title": "VİTAL BULGULAR",
                "icd10": primary_icd10,
                "diagnosis": diagnosis,
                "department": department,
                "severity": severity,
                "patient_age": str(age),
                "patient_gender": gender,
                "category": "anamnesis_field",
            })
            ids.append(f"anamnez_{sid}_vitals")

        # --- Full case summary ---
        summary_fields = ["hastanin_yakinmasi", "hastanin_oykusu", "muayene_bulgulari", "tedavi"]
        summary_parts = [sections.get(f, "") for f in summary_fields if sections.get(f, "").strip()]
        if summary_parts:
            documents.append(" ---- ".join(summary_parts))
            metadatas.append({
                "scenario_id": sid,
                "field": "full_summary",
                "field_title": "TAM VAKA ÖZETİ",
                "icd10": primary_icd10,
                "diagnosis": diagnosis,
                "department": department,
                "severity": severity,
                "patient_age": str(age),
                "patient_gender": gender,
                "category": "anamnesis_summary",
            })
            ids.append(f"anamnez_{sid}_summary")

        # --- Symptom index (one per ICD-10) ---
        for code in icd10_codes:
            if code and code not in seen_symptom_docs:
                symptoms = SYMPTOM_KEYWORDS.get(code, [])
                if symptoms:
                    symptom_text = (
                        f"{diagnosis}: {', '.join(symptoms)}. "
                        f"Bu belirtiler {diagnosis} tanisi ile iliskilidir."
                    )
                    documents.append(symptom_text)
                    metadatas.append({
                        "scenario_id": "symptom_index",
                        "field": "symptom_index",
                        "field_title": "SEMPTOM İNDEKSİ",
                        "icd10": code,
                        "diagnosis": diagnosis,
                        "department": department,
                        "severity": "all",
                        "patient_age": "all",
                        "patient_gender": "all",
                        "category": "symptom_index",
                    })
                    ids.append(f"symptom_idx_{code}")
                    seen_symptom_docs.add(code)

    return documents, metadatas, ids


def seed_anamnez_database(force: bool = False) -> None:
    import asyncio

    async def _seed() -> None:
        rag = RAGService()
        await rag.initialize()

        if not force and rag.doc_count > 100:
            logger.info(
                "RAG DB has %d docs. Clearing for re-seed.", rag.doc_count
            )

        # Clear and recreate collection
        if rag._client is not None:
            try:
                rag._client.delete_collection(name="medical_knowledge")
            except Exception:
                pass
            rag._collection = rag._client.get_or_create_collection(
                name="medical_knowledge",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("Cleared existing collection.")

        scenarios = _load_scenarios()
        if not scenarios:
            logger.error("No scenarios to seed.")
            return

        logger.info("Building documents from %d scenarios...", len(scenarios))
        documents, metadatas, ids = _build_documents(scenarios)
        logger.info("Prepared %d documents for indexing.", len(documents))

        batch_size = 500
        total = len(documents)
        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            rag.add_documents(
                documents[start:end],
                metadatas[start:end],
                ids[start:end],
            )
            logger.info("Indexed %d-%d of %d", start + 1, end, total)

        logger.info("Seeding complete. Total: %d", rag.doc_count)

    asyncio.run(_seed())


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    seed_anamnez_database(force=args.force)
