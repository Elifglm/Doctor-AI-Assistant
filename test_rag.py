"""RAG Test Script v3 - n_results=50 + diversity filter.

Usage:
    python test_rag.py
"""

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from apps.backend.src.services.rag_service import RAGService


TEST_QUERIES = [
    {
        "name": "Hipertansiyon vakasi",
        "query": "Hasta bas agrisi ve bas donmesi sikayetiyle basvurdu. Tansiyonu 160/100 olarak olculdu. Ense bolgesinde zonklayici agri var.",
        "expected_icd10": "I10",
        "expected_diagnosis": "hipertansiyon",
    },
    {
        "name": "Diyabet vakasi",
        "query": "Hasta susuzluk, sik idrara cikma ve halsizlik sikayetiyle geldi. Aclik kan sekeri 210 mg/dL. Son zamanlarda kilo kaybi var.",
        "expected_icd10": "E11",
        "expected_diagnosis": "diabetes mellitus",
    },
    {
        "name": "KOAH alevlenme",
        "query": "KOAH tanili hasta nefes darligi ve balgamli oksuruk ile basvurdu. Sari-yesil balgam var. SpO2 %89.",
        "expected_icd10": "J44",
        "expected_diagnosis": "KOAH",
    },
    {
        "name": "Gastrit / GORH",
        "query": "Hasta mide yanmasi ve agiza aci su gelmesi sikayetiyle geldi. Yemeklerden sonra artiyor. Gece yatinca belirginlesiyor.",
        "expected_icd10": "K21",
        "expected_diagnosis": "reflu",
    },
    {
        "name": "Demir eksikligi anemisi",
        "query": "Hasta halsizlik, cabuk yorulma ve sac dokulmesi tarif ediyor. Konjunktivalar soluk. Adet kanamasi miktari artmis.",
        "expected_icd10": "D50",
        "expected_diagnosis": "anemi",
    },
]


def _diverse_results(results, top_k=5):
    """Pick top_k results ensuring different diagnoses are represented."""
    seen_diag: set[str] = set()
    diverse: list = []

    for r in results:
        diag = r.metadata.get("diagnosis", "")
        if diag not in seen_diag:
            diverse.append(r)
            seen_diag.add(diag)
            if len(diverse) >= top_k:
                break

    # Fill remaining if needed
    if len(diverse) < top_k:
        for r in results:
            if r not in diverse:
                diverse.append(r)
                if len(diverse) >= top_k:
                    break

    return diverse


async def run_tests():
    print("=" * 70)
    print("  RAG TEST v3 - n_results=50 + Cesitlilik Filtreli")
    print("=" * 70)

    rag = RAGService()
    await rag.initialize()

    print(f"\nChromaDB'de toplam dokuman sayisi: {rag.doc_count}")
    print()

    if rag.doc_count == 0:
        print("HATA: ChromaDB bos!")
        return

    passed = 0
    failed = 0

    for test in TEST_QUERIES:
        print("-" * 70)
        print(f"TEST: {test['name']}")
        print(f"Sorgu: {test['query'][:80]}...")
        print()

        # TOP 50 cek, cesitlilik filtresi ile 5'e indir
        raw_results = await rag.query(test["query"], n_results=50)
        results = _diverse_results(raw_results, top_k=5)

        if not results:
            print("  SONUC: Hic sonuc donmedi! BASARISIZ")
            failed += 1
            continue

        found_match = False
        for i, r in enumerate(results):
            icd10 = r.metadata.get("icd10", "?")
            diagnosis = r.metadata.get("diagnosis", "?")
            field = r.metadata.get("field_title", r.metadata.get("section_title", "?"))
            distance = r.distance
            similarity = 1 - distance

            content_preview = r.content[:120].replace("\n", " ")

            marker = ""
            if test["expected_icd10"] in icd10 or test["expected_diagnosis"].lower() in diagnosis.lower():
                marker = " <-- ESLESTI!"
                found_match = True

            print(f"  [{i+1}] Benzerlik: {similarity:.3f} | ICD-10: {icd10} | {diagnosis}")
            print(f"      Alan: {field}")
            print(f"      Icerik: {content_preview}...{marker}")
            print()

        if found_match:
            print(f"  SONUC: BASARILI - Beklenen tani ({test['expected_diagnosis']}) bulundu!")
            passed += 1
        else:
            print(f"  SONUC: BASARISIZ - Beklenen tani ({test['expected_diagnosis']}) bulunamadi!")
            failed += 1

    print("=" * 70)
    print(f"  OZET: {passed} basarili, {failed} basarisiz / toplam {len(TEST_QUERIES)} test")
    print("=" * 70)

    if failed == 0:
        print("\n  TEBRIKLER! Tum testler gecti. RAG dogru calisiyor!")
    elif failed <= 1:
        print(f"\n  IYI! {passed}/{len(TEST_QUERIES)} test gecti. Kabul edilebilir seviye.")
    else:
        print(f"\n  {failed} test basarisiz. Verileri kontrol edin.")


if __name__ == "__main__":
    asyncio.run(run_tests())
