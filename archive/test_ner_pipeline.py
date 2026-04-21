"""NER + De-ID + LLM prompt test script.

Runs the full pipeline on a mock dahiliye transcript and prints:
  1. NER entities extracted
  2. De-identified text
  3. Exact batch prompt that would be sent to the LLM
"""

import asyncio
import json
import sys
import os

# Ensure project root is on path (script lives in archive/, so go up one level)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apps.backend.src.services.ner_service import NERService, MedicalEntity
from apps.backend.src.services.deid_service import (
    DeIdentificationService,
    PHIContext,
)
from apps.backend.src.services.report_generator import ReportGenerator, _merge_segments
from apps.backend.src.prompts.section_prompts import ANAMNESIS_SECTIONS

# -------------------------------------------------------------------
# 1. Mock transcript -- dahiliye (internal medicine)
#    Patient: Furkan Kapusuz, TC: 10000000214, DOB: 01/01/2024, Anne: Ayse
#    All 13 NER labels covered:
#      semptom, hastalik, ilac, dozaj, alerji, ameliyat,
#      tibbi_test, vucud_bolumu, sure, aile_hastaligi,
#      sigara, alkol, meslek
# -------------------------------------------------------------------

SEGMENTS = [
    {
        "speaker": "doctor",
        "speaker_label": "Doktor",
        "text": "Buyurun Furkan Bey, hos geldiniz. Kimliginizi teyit edelim: soyadiniz Kapuksuz, TC kimlik numaraniz 10000000214, dogum tarihiniz 01/01/2024 dogru mu?",
        "start_time": 0.0,
        "end_time": 8.0,
    },
    {
        "speaker": "patient",
        "speaker_label": "Hasta",
        "text": "Soyadim Kapusuz efendim, duzeltmek isterim. TC ve dogum tarihim dogru.",
        "start_time": 8.0,
        "end_time": 12.0,
    },
    {
        "speaker": "doctor",
        "speaker_label": "Doktor",
        "text": "Ozur dilerim, not aldim. Sikayetleriniz neler?",
        "start_time": 12.0,
        "end_time": 14.0,
    },
    {
        "speaker": "patient",
        "speaker_label": "Hasta",
        "text": "Hocam iki haftadir karin agrisi var, ozellikle ust karin bolgesinde. Mide bulantisi da eslik ediyor. Bazen kusma da oluyor.",
        "start_time": 14.0,
        "end_time": 22.0,
    },
    {
        "speaker": "doctor",
        "speaker_label": "Doktor",
        "text": "Ne is yapiyorsunuz?",
        "start_time": 12.0,
        "end_time": 14.0,
    },
    {
        "speaker": "patient",
        "speaker_label": "Hasta",
        "text": "Muhasebeciyim, ofiste calisiyorum. Stresli bir donem geciriyorum.",
        "start_time": 14.0,
        "end_time": 18.0,
    },
    {
        "speaker": "doctor",
        "speaker_label": "Doktor",
        "text": "Sigara kullaniyor musunuz?",
        "start_time": 18.0,
        "end_time": 20.0,
    },
    {
        "speaker": "patient",
        "speaker_label": "Hasta",
        "text": "Evet gunde yarim paket sigara iciyorum, on yildir kullaniyorum.",
        "start_time": 20.0,
        "end_time": 24.0,
    },
    {
        "speaker": "doctor",
        "speaker_label": "Doktor",
        "text": "Alkol kullaniyor musunuz?",
        "start_time": 24.0,
        "end_time": 26.0,
    },
    {
        "speaker": "patient",
        "speaker_label": "Hasta",
        "text": "Haftada bir iki bira iciyorum, sosyal duzeyde.",
        "start_time": 26.0,
        "end_time": 30.0,
    },
    {
        "speaker": "doctor",
        "speaker_label": "Doktor",
        "text": "Bilinen alerjiniz var mi?",
        "start_time": 30.0,
        "end_time": 32.0,
    },
    {
        "speaker": "patient",
        "speaker_label": "Hasta",
        "text": "Penisiline alerjim var, dokuntuler cikiyor.",
        "start_time": 32.0,
        "end_time": 36.0,
    },
    {
        "speaker": "doctor",
        "speaker_label": "Doktor",
        "text": "Daha once gecirdiginiz bir ameliyat veya bilinen hastalik var mi?",
        "start_time": 36.0,
        "end_time": 40.0,
    },
    {
        "speaker": "patient",
        "speaker_label": "Hasta",
        "text": "Uc yil once apandisit ameliyati gecirdim. Ayrica tip iki diyabetim var, iki yildir metformin sekiz yuz elli miligram gunde iki kere kullaniyorum.",
        "start_time": 40.0,
        "end_time": 50.0,
    },
    {
        "speaker": "doctor",
        "speaker_label": "Doktor",
        "text": "Ailede bilinen hastalik var mi?",
        "start_time": 50.0,
        "end_time": 52.0,
    },
    {
        "speaker": "patient",
        "speaker_label": "Hasta",
        "text": "Annem Ayse'de hipertansiyon var, babamda koroner arter hastaligi varmis.",
        "start_time": 52.0,
        "end_time": 58.0,
    },
    {
        "speaker": "doctor",
        "speaker_label": "Doktor",
        "text": "Simdi sizi muayene edecegim. Tansiyonunuz yuz otuz uzeri seksen bes, nabiz yetmis sekiz, ates otuz alti nokta bes, saturasyon yuzde doksan sekiz. Kilonuz seksen iki, boyunuz yuz yetmis dort. Karin muayenesinde epigastrik hassasiyet mevcut, defans yok, barsak sesleri dogal.",
        "start_time": 58.0,
        "end_time": 72.0,
    },
    {
        "speaker": "doctor",
        "speaker_label": "Doktor",
        "text": "Tam kan sayimi, karaciger fonksiyon testleri ve lipid paneli istiyorum. Tedavi olarak omeprazol yirmi miligram gunde bir basliyoruz. Tuz kisitlamasi yapmanizi oneriyorum. Bir hafta sonra kontrole gelin.",
        "start_time": 72.0,
        "end_time": 85.0,
    },
]

PHI = PHIContext(
    patient_first_name="Furkan",
    patient_last_name="Kapusuz",
    patient_tc_kimlik="10000000214",
    patient_phone="",
    patient_email="",
    patient_birth_date="01/01/2024",
    patient_address="",
    patient_city="",
    patient_emergency_contact_name="Ayse",
    patient_emergency_contact_phone="",
    patient_insurance_number="",
    doctor_display_name="",
    doctor_username="",
    session_patient_name="Furkan Kapusuz",
)


async def main():
    print("=" * 80)
    print("STEP 0: MERGED TRANSCRIPT")
    print("=" * 80)
    full_text = _merge_segments(SEGMENTS)
    print(full_text)
    print()

    # -------------------------------------------------------------------
    # NER
    # -------------------------------------------------------------------
    print("=" * 80)
    print("STEP 1: NER EXTRACTION (loading model, may take a minute...)")
    print("=" * 80)
    ner = NERService()
    await ner.initialize()

    entities = await ner.extract(full_text)
    print(f"\nToplam {len(entities)} entity bulundu:\n")

    # Group by label for readability
    label_groups: dict[str, list[MedicalEntity]] = {}
    for e in entities:
        label_groups.setdefault(e.label, []).append(e)

    ALL_LABELS = NERService.MEDICAL_LABELS
    found_labels = set(label_groups.keys())
    missing_labels = set(ALL_LABELS) - found_labels

    for label in ALL_LABELS:
        ents = label_groups.get(label, [])
        marker = "OK" if ents else "MISSING"
        print(f"  [{marker}] {label}:")
        for e in ents:
            print(f"        \"{e.text}\" (score={e.score:.3f}, pos={e.start}-{e.end})")
        if not ents:
            print(f"        (hicbir entity bulunamadi)")
        print()

    if missing_labels:
        print(f"  *** EKSIK ETIKETLER: {', '.join(sorted(missing_labels))} ***\n")
    else:
        print(f"  >>> TUM 13 ETIKET BASARIYLA TESPIT EDILDI <<<\n")

    grouped = NERService.group_by_section(entities)

    # -------------------------------------------------------------------
    # De-Identification
    # -------------------------------------------------------------------
    print("=" * 80)
    print("STEP 2: DE-IDENTIFICATION")
    print("=" * 80)
    deid = DeIdentificationService(enabled=True, use_ner_layer=False)  # skip PII NER for speed
    masked_text, pmap = await deid.deidentify(full_text, PHI)
    print(f"\nPlaceholder map: {pmap}")
    print(f"All placeholders: {json.dumps(pmap.all_placeholders, ensure_ascii=False, indent=2)}")
    print(f"\nMasked text:\n{masked_text}\n")

    # -------------------------------------------------------------------
    # Batch prompt (what goes to LLM)
    # -------------------------------------------------------------------
    print("=" * 80)
    print("STEP 3: BATCH PROMPT (LLM'E GIDECEK PROMPT)")
    print("=" * 80)

    # We need a ReportGenerator instance just for the prompt builder
    # (won't actually call LLM)
    class FakeLLM:
        async def generate(self, prompt, system): return ""
        async def generate_stream(self, prompt, system): yield ""

    class FakeRAG:
        is_ready = False
        doc_count = 0

    rg = ReportGenerator(ner=ner, rag=FakeRAG(), llm=FakeLLM(), deid_service=deid)
    batch_prompt = rg._build_batch_prompt(masked_text, entities, grouped)
    print(f"\n{batch_prompt}\n")

    print("=" * 80)
    print("STEP 4: SECTION MAPPING (NER -> HBYS ALANLARI)")
    print("=" * 80)
    for section_key, section_entities in sorted(grouped.items()):
        title = ANAMNESIS_SECTIONS.get(section_key, {}).get("title", section_key)
        print(f"\n  {title} ({section_key}):")
        for e in section_entities:
            print(f"    - [{e.label}] \"{e.text}\" ({e.score:.3f})")

    print("\n" + "=" * 80)
    print("TEST TAMAMLANDI")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
