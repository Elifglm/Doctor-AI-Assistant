"""Seed the RAG database with medical knowledge.

Run this script to populate ChromaDB with:
- ICD-10 TR codes (starter set)
- Common Turkish clinical guidelines
- Common medications in Turkey

Usage:
    python -m apps.backend.src.rag.seed_data
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure project root on path
_PROJECT_ROOT = str(Path(__file__).resolve().parents[4])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from apps.backend.src.services.rag_service import RAGService


# ---------------------------------------------------------------------------
# Starter ICD-10 TR data (most common outpatient codes)
# ---------------------------------------------------------------------------

ICD10_TR_STARTER: list[dict[str, str]] = [
    {"code": "I10", "description": "Esansiyel (primer) hipertansiyon", "category": "icd10"},
    {"code": "E11", "description": "Tip 2 diabetes mellitus", "category": "icd10"},
    {"code": "J06.9", "description": "Akut ust solunum yolu enfeksiyonu, tanimsiz", "category": "icd10"},
    {"code": "M54.5", "description": "Bel agrisi", "category": "icd10"},
    {"code": "J20.9", "description": "Akut bronsit, tanimsiz", "category": "icd10"},
    {"code": "K29.7", "description": "Gastrit, tanimsiz", "category": "icd10"},
    {"code": "N39.0", "description": "Uriner sistem enfeksiyonu, lokalizasyonu belirtilmemis", "category": "icd10"},
    {"code": "R51", "description": "Bas agrisi", "category": "icd10"},
    {"code": "E78.5", "description": "Hiperlipidemi, tanimsiz", "category": "icd10"},
    {"code": "I25.1", "description": "Aterosklerotik kalp hastaligi", "category": "icd10"},
    {"code": "J45.9", "description": "Astim, tanimsiz", "category": "icd10"},
    {"code": "F41.1", "description": "Yaygin anksiyete bozuklugu", "category": "icd10"},
    {"code": "F32.9", "description": "Depresif epizod, tanimsiz", "category": "icd10"},
    {"code": "K21.0", "description": "Ozofajit ile gastro-ozofageal reflu hastaligi", "category": "icd10"},
    {"code": "E03.9", "description": "Hipotiroidizm, tanimsiz", "category": "icd10"},
    {"code": "M79.3", "description": "Pannikulit, tanimsiz", "category": "icd10"},
    {"code": "G43.9", "description": "Migren, tanimsiz", "category": "icd10"},
    {"code": "L30.9", "description": "Dermatit, tanimsiz", "category": "icd10"},
    {"code": "J02.9", "description": "Akut farenjit, tanimsiz", "category": "icd10"},
    {"code": "R10.4", "description": "Diger ve tanimsiz karin agrisi", "category": "icd10"},
    {"code": "I48", "description": "Atriyal fibrilasyon ve flutter", "category": "icd10"},
    {"code": "N18.9", "description": "Kronik bobrek hastaligi, tanimsiz", "category": "icd10"},
    {"code": "E66.9", "description": "Obezite, tanimsiz", "category": "icd10"},
    {"code": "I50.9", "description": "Kalp yetersizligi, tanimsiz", "category": "icd10"},
    {"code": "J44.1", "description": "Akut alevlenme ile KOAH", "category": "icd10"},
]


# ---------------------------------------------------------------------------
# Common medications in Turkey
# ---------------------------------------------------------------------------

MEDICATIONS_TR: list[dict[str, str]] = [
    {"name": "Amlodipin", "group": "Kalsiyum kanal blokoru", "indication": "Hipertansiyon, anjina pektoris", "category": "medication"},
    {"name": "Metformin", "group": "Biguanid", "indication": "Tip 2 diabetes mellitus", "category": "medication"},
    {"name": "Atorvastatin", "group": "Statin", "indication": "Hiperlipidemi", "category": "medication"},
    {"name": "Ramipril", "group": "ACE inhibitoru", "indication": "Hipertansiyon, kalp yetersizligi", "category": "medication"},
    {"name": "Asetilsalisilik asit", "group": "Antitrombotik", "indication": "Kardiyovaskuler profilaksi", "category": "medication"},
    {"name": "Omeprazol", "group": "Proton pompa inhibitoru", "indication": "GORH, peptik ulser", "category": "medication"},
    {"name": "Parasetamol", "group": "Analjezik/antipiretik", "indication": "Agri, ates", "category": "medication"},
    {"name": "Ibuprofen", "group": "NSAID", "indication": "Agri, inflamasyon", "category": "medication"},
    {"name": "Amoksisilin", "group": "Penisilin grubu antibiyotik", "indication": "Bakteriyel enfeksiyonlar", "category": "medication"},
    {"name": "Levotiroksin", "group": "Tiroid hormonu", "indication": "Hipotiroidizm", "category": "medication"},
    {"name": "Sertralin", "group": "SSRI", "indication": "Depresyon, anksiyete bozuklugu", "category": "medication"},
    {"name": "Salbutamol", "group": "Beta-2 agonist", "indication": "Astim, KOAH", "category": "medication"},
    {"name": "Losartan", "group": "ARB", "indication": "Hipertansiyon", "category": "medication"},
    {"name": "Metoprolol", "group": "Beta blokor", "indication": "Hipertansiyon, aritmi, anjina", "category": "medication"},
    {"name": "Klaritromisin", "group": "Makrolid antibiyotik", "indication": "Solunum yolu enfeksiyonlari", "category": "medication"},
]


# ---------------------------------------------------------------------------
# Clinical guidelines (starter)
# ---------------------------------------------------------------------------

CLINICAL_GUIDELINES: list[dict[str, str]] = [
    {
        "content": "Hipertansiyon tani kriterleri: Ofis tansiyonu >= 140/90 mmHg. "
                   "Evre 1: 140-159/90-99. Evre 2: 160-179/100-109. Evre 3: >= 180/110. "
                   "Hedef tansiyon: < 140/90 mmHg (genel), < 130/80 mmHg (diyabet, KBH).",
        "source": "Turk Kardiyoloji Dernegi Hipertansiyon Kilavuzu",
        "category": "guideline",
        "section_relevance": "assessment,plan",
    },
    {
        "content": "Tip 2 DM tani kriterleri: Aclik kan sekeri >= 126 mg/dL, "
                   "HbA1c >= %6.5, OGTT 2. saat >= 200 mg/dL, "
                   "veya semptomlar + rastgele kan sekeri >= 200 mg/dL. "
                   "Tedavi hedefi: HbA1c < %7 (genel).",
        "source": "TEMD Diabetes Mellitus Kilavuzu",
        "category": "guideline",
        "section_relevance": "assessment,plan",
    },
    {
        "content": "Anamnez sirasinda sigara oykusu: Paket-yil hesaplama = "
                   "(gunde icilen paket sayisi) x (yil sayisi). "
                   "Ornek: Gunde 1 paket, 20 yildir = 20 paket-yil.",
        "source": "Genel Anamnez Kilavuzu",
        "category": "guideline",
        "section_relevance": "social_history",
    },
    {
        "content": "Bas agrisi red bayraklari (acil degerlendirme gerektiren durumlar): "
                   "Ani baslangiçli siddetli bas agrisi, ates esliginde bas agrisi, "
                   "norolojik defisit, papil odemi, 50 yas ustu yeni baslangicli, "
                   "progresif kotulesen bas agrisi, kanser/HIV oykusu olan hastada.",
        "source": "Noroloji Kilavuzu",
        "category": "guideline",
        "section_relevance": "assessment,history_present",
    },
    {
        "content": "Genel fizik muayene sirasi: Vital bulgular (tansiyon, nabiz, ates, "
                   "solunum sayisi, SpO2), genel gorunum, bas-boyun, toraks, "
                   "kardiyovaskuler, abdomen, ekstremiteler, norolojik.",
        "source": "Klinik Beceriler Kilavuzu",
        "category": "guideline",
        "section_relevance": "physical_exam",
    },
    {
        "content": "Ilac alerjisi sorgulama: Alerji tipi (urtiker, anafilaksi, deri dokuntusu), "
                   "alerjik reaksiyon olan ilac, reaksiyonun zamani ve siddeti. "
                   "Penisilin alerjisi olan hastalarda sefalosporin capraz alerjisi %1-10.",
        "source": "Farmakoloji Kilavuzu",
        "category": "guideline",
        "section_relevance": "allergies",
    },
    {
        "content": "Aile oykusu onemli hastaliklar: Koroner arter hastaligi (<55 yas erkek, "
                   "<65 yas kadin birinci derece akrabada), hipertansiyon, diabetes mellitus, "
                   "kanser (meme, kolon, over), inme, hematolojik hastaliklar.",
        "source": "Aile Hekimligi Kilavuzu",
        "category": "guideline",
        "section_relevance": "family_history",
    },
]


# ---------------------------------------------------------------------------
# Anamnesis section templates
# ---------------------------------------------------------------------------

SECTION_TEMPLATES: list[dict[str, str]] = [
    {
        "content": "Basvuru sikayeti: Hastanin ana yakinmasi, kendi kelimeleriyle, "
                   "1-2 cumle ile ozetlenir. Sure ve siddet bilgisi eklenir.",
        "source": "Anamnez Sablonu",
        "category": "template",
        "section_relevance": "chief_complaint",
    },
    {
        "content": "Simdiki hastalik hikayesi: Kronolojik sira ile baslangic, "
                   "ilerleme, lokalizasyon, karakter, siddet, artiran/azaltan faktorler, "
                   "eslik eden semptomlar, onceki tedaviler ve sonuclari.",
        "source": "Anamnez Sablonu",
        "category": "template",
        "section_relevance": "history_present",
    },
]


def seed_rag_database() -> None:
    """Populate the RAG collection with starter medical data."""
    import asyncio

    async def _seed() -> None:
        rag = RAGService()
        await rag.initialize()

        existing = rag.doc_count
        if existing > 0:
            logger.info("RAG database already has %d documents. Skipping seed.", existing)
            return

        documents: list[str] = []
        metadatas: list[dict[str, str]] = []
        ids: list[str] = []

        # ICD-10 codes
        for item in ICD10_TR_STARTER:
            doc = f"ICD-10 {item['code']}: {item['description']}"
            documents.append(doc)
            metadatas.append({"source": "ICD-10-TR", "category": item["category"], "code": item["code"]})
            ids.append(f"icd10_{item['code']}")

        # Medications
        for item in MEDICATIONS_TR:
            doc = f"{item['name']} ({item['group']}): {item['indication']}"
            documents.append(doc)
            metadatas.append({"source": "Ilac Veritabani", "category": item["category"], "name": item["name"]})
            ids.append(f"med_{item['name'].lower().replace(' ', '_')}")

        # Clinical guidelines
        for i, item in enumerate(CLINICAL_GUIDELINES):
            documents.append(item["content"])
            metadatas.append({
                "source": item["source"],
                "category": item["category"],
                "section_relevance": item["section_relevance"],
            })
            ids.append(f"guide_{i}")

        # Section templates
        for i, item in enumerate(SECTION_TEMPLATES):
            documents.append(item["content"])
            metadatas.append({
                "source": item["source"],
                "category": item["category"],
                "section_relevance": item["section_relevance"],
            })
            ids.append(f"template_{i}")

        rag.add_documents(documents, metadatas, ids)
        logger.info("Seeded RAG database with %d documents.", len(documents))

    asyncio.run(_seed())


if __name__ == "__main__":
    seed_rag_database()
