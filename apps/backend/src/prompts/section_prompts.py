"""Section-specific prompts for the 12 anamnesis report sections."""

from __future__ import annotations

from typing import Any

from apps.backend.src.services.ner_service import MedicalEntity
from apps.backend.src.services.rag_service import RAGResult

# Ordered dictionary of all 12 anamnesis sections
ANAMNESIS_SECTIONS: dict[str, dict[str, str]] = {
    "chief_complaint": {
        "title": "Basvuru Sikayeti",
        "prompt": (
            "Transkriptten hastanin ana basvuru sikayetini cikar.\n"
            "Format: Kisa ve oz (1-2 cumle). Hastanin kendi kelimeleriyle.\n"
            "Ornek: '3 gundur devam eden siddetli bas agrisi ve bulanti.'"
        ),
    },
    "history_present": {
        "title": "Simdiki Hastalik Hikayesi",
        "prompt": (
            "Mevcut hastalik oykusunu kronolojik sirala.\n"
            "Icermeli: baslangic tarihi, sure, siddet, lokalizasyon, "
            "artiran/azaltan faktorler, eslik eden semptomlar.\n"
            "Her bilgiyi transkriptteki sirasina gore yaz."
        ),
    },
    "past_medical": {
        "title": "Gecmis Tibbi Ozgecmis",
        "prompt": (
            "Hastanin gecmis tibbi oykusunu cikar.\n"
            "Icermeli: onceki hastaliklar, ameliyatlar, hastane yatislari, "
            "kronik hastaliklar.\n"
            "Eger bilgi yoksa 'Belirtilmedi' yaz."
        ),
    },
    "medications": {
        "title": "Kullanilan Ilaclar",
        "prompt": (
            "Hastanin kullandigi ilaclari listele.\n"
            "Her ilac icin: ilac adi, dozaj, kullanim sikligi (varsa).\n"
            "Liste halinde yaz. Bilgi yoksa 'Belirtilmedi' yaz."
        ),
    },
    "allergies": {
        "title": "Alerjiler",
        "prompt": (
            "Hastanin alerjilerini cikar.\n"
            "Ilac alerjileri, gida alerjileri ve diger alerjiler.\n"
            "Bilgi yoksa 'Belirtilmedi' yaz."
        ),
    },
    "family_history": {
        "title": "Aile Oykusu",
        "prompt": (
            "Aile oykusunu cikar.\n"
            "Anne, baba, kardesler ve diger yakin akrabalarin bilinen hastaliklari.\n"
            "Bilgi yoksa 'Belirtilmedi' yaz."
        ),
    },
    "social_history": {
        "title": "Sosyal Oyku",
        "prompt": (
            "Sosyal oykuyu cikar.\n"
            "Icermeli: meslek, sigara kullanimi (miktar, sure), alkol kullanimi, "
            "egzersiz aliskanliklari, yasam kosullari.\n"
            "Bilgi yoksa 'Belirtilmedi' yaz."
        ),
    },
    "review_systems": {
        "title": "Sistemlerin Gozden Gecirilmesi",
        "prompt": (
            "Sistem sorgusunu cikar.\n"
            "Transkriptte bahsedilen diger sistem yakinmalarini listele.\n"
            "Kardiyovaskuler, solunum, gastrointestinal, norolojik vb.\n"
            "Sadece transkriptte gecen bilgileri yaz. Bilgi yoksa 'Belirtilmedi' yaz."
        ),
    },
    "physical_exam": {
        "title": "Fizik Muayene",
        "prompt": (
            "Fizik muayene bulgularini cikar.\n"
            "Doktorun muayene sirasinda soyledigi bulgulari yaz.\n"
            "Bilgi yoksa 'Belirtilmedi' yaz."
        ),
    },
    "assessment": {
        "title": "Degerlendirme",
        "prompt": (
            "Doktorun degerlendirmesini cikar.\n"
            "On tani, ayirici tani veya kesin tani bilgilerini yaz.\n"
            "Sadece doktorun soylediklerini kullan. Bilgi yoksa 'Belirtilmedi' yaz."
        ),
    },
    "plan": {
        "title": "Tedavi Plani",
        "prompt": (
            "Tedavi planini cikar.\n"
            "Istenen tetkikler, recelenen ilaclar, yapilacak islemler, "
            "kontrol randevusu, sevk bilgileri.\n"
            "Bilgi yoksa 'Belirtilmedi' yaz."
        ),
    },
    "notes": {
        "title": "Ek Notlar",
        "prompt": (
            "Diger bolumlere uymayan ek bilgileri yaz.\n"
            "Doktorun veya hastanin belirttigi onemli ek notlar.\n"
            "Bilgi yoksa 'Belirtilmedi' yaz."
        ),
    },
}


def _format_entities(entities: list[MedicalEntity]) -> str:
    if not entities:
        return "Tespit edilen tibbi bilgi yok."
    lines: list[str] = []
    for e in entities:
        lines.append(f"- [{e.label}] {e.text} (guven: {e.score:.2f})")
    return "\n".join(lines)


def _format_rag_context(results: list[RAGResult]) -> str:
    if not results:
        return "Ek referans bilgisi yok."
    lines: list[str] = []
    for r in results:
        source = r.metadata.get("source", "")
        lines.append(f"- {r.content}" + (f" [{source}]" if source else ""))
    return "\n".join(lines)


def build_section_prompt(
    section_key: str,
    transcript: str,
    entities: list[MedicalEntity],
    rag_context: list[RAGResult],
) -> str:
    """Build the full prompt for a single report section."""
    meta = ANAMNESIS_SECTIONS[section_key]
    return (
        f"TRANSKRIPT:\n{transcript}\n\n"
        f"TESPIT EDILEN TIBBI BILGILER:\n{_format_entities(entities)}\n\n"
        f"REFERANS BILGI:\n{_format_rag_context(rag_context)}\n\n"
        f"GOREV: {meta['prompt']}\n\n"
        f"BOLUM: {meta['title']}\n"
        f"Sadece bu bolumun icerigini yaz. Bolum basligi ekleme."
    )
