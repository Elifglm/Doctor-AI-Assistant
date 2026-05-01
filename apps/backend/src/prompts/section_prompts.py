"""Section-specific prompts for HBYS (Hastane Bilgi Yonetim Sistemi) anamnesis fields."""

from __future__ import annotations

from typing import Any

from apps.backend.src.services.ner_service import MedicalEntity
from apps.backend.src.services.rag_service import RAGResult

# ---------------------------------------------------------------------------
# HBYS field definitions — ordered as they appear in hospital system
# ---------------------------------------------------------------------------

ANAMNESIS_SECTIONS: dict[str, dict[str, str]] = {
    "hastanin_yakinmasi": {
        "title": "HASTANIN YAKINMASI",
        "prompt": (
            "Transkriptten hastanin ana sikayetini/sikayetlerini cikar.\n"
            "Format: BUYUK HARF ile yaz.\n"
            "Birden fazla sikayet varsa '+' ile ayir.\n"
            "Ornek: BAS AGRISI + BAS DONMESI"
        ),
    },
    "hastanin_oykusu": {
        "title": "HASTANIN OYKUSU",
        "prompt": (
            "Mevcut hastalik oykusunu kronolojik olarak cikar.\n"
            "Format: BUYUK HARF, her bilgiyi '----' ile ayir.\n"
            "Icermeli: baslangic tarihi, sure, siddet, lokalizasyon, "
            "artiran/azaltan faktorler, eslik eden semptomlar.\n"
            "Ornek: 2 HAFTADIR BAS AGRISI MEVCUT ---- ENSE BOLGESINDE "
            "ZONKLAYICI TARZDA ---- SABAHLARI BELIRGIN"
        ),
    },
    "oz_gecmisi_soy_gecmisi": {
        "title": "OZ GECMISI/SOY GECMISI",
        "prompt": (
            "Hastanin gecmis tibbi oykusunu cikar.\n"
            "Format: BUYUK HARF, her bilgiyi '----' ile ayir.\n"
            "Kullandigi ilaclar varsa '///' ile ayir.\n"
            "Icermeli: kronik hastaliklar, ameliyatlar, hastane yatislari.\n"
            "Ornek: KOAH (GOLD EVRE 2, 5 YILDIR) ---- HT (10 YILDIR) "
            "/// TIOTROPIUM 18 MCG INH 1X1 + RAMIPRIL 5 MG 1X1\n"
            "Bilgi yoksa 'BELIRTILMEDI' yaz."
        ),
    },
    "soy_gecmisi": {
        "title": "SOY GECMISI",
        "prompt": (
            "Aile oykusunu cikar.\n"
            "Format: BUYUK HARF, her aile bireyini '----' ile ayir.\n"
            "Birden fazla hastalik varsa '+' ile ayir.\n"
            "Ornek: ANNE HT + DM ---- BABA KAH ---- KARDES SAGLIKLI\n"
            "Bilgi yoksa 'BELIRTILMEDI' yaz."
        ),
    },
    "sigara": {
        "title": "SIGARA",
        "prompt": (
            "Sigara kullanim durumunu cikar.\n"
            "Format: BUYUK HARF.\n"
            "Ornek: KULLANIYOR (1 PAKET/GUN, 25 YILDIR) veya KULLANMIYOR "
            "veya BIRAKMIS (5 YIL ONCE)\n"
            "Bilgi yoksa 'BELIRTILMEDI' yaz."
        ),
    },
    "alkol": {
        "title": "ALKOL",
        "prompt": (
            "Alkol kullanim durumunu cikar.\n"
            "Format: BUYUK HARF.\n"
            "Ornek: SOSYAL DUZEYDE veya KULLANMIYOR\n"
            "Bilgi yoksa 'BELIRTILMEDI' yaz."
        ),
    },
    "alerji": {
        "title": "ALERJI",
        "prompt": (
            "Alerji bilgisini cikar.\n"
            "Format: BUYUK HARF. Reaksiyon tipini parantez icinde belirt.\n"
            "Ornek: PENISILIN (URTIKER) veya BILINEN ALERJISI YOK\n"
            "Bilgi yoksa bos birak."
        ),
    },
    "muayene_bulgulari": {
        "title": "MUAYENE BULGULARI",
        "prompt": (
            "Fizik muayene bulgularini cikar.\n"
            "Format: BUYUK HARF, virgul ile ayir.\n"
            "Ornek: GD IYI , KOOPERE , ORYANTE , BAS-BOYUN DOGAL , "
            "KVS S1-S2 DOGAL EK SES YOK , AC BILATERAL DOGAL , "
            "BATIN RAHAT DEFANS YOK , EKSTREMITE ODEM YOK\n"
            "Bilgi yoksa 'BELIRTILMEDI' yaz."
        ),
    },
    "sistolik": {
        "title": "SISTOLIK",
        "prompt": (
            "Sistolik kan basinci degerini cikar.\n"
            "Format: SADECE SAYI yaz (mmHg birimi ekleme).\n"
            "Ornek: 165\n"
            "Bilgi yoksa bos birak."
        ),
    },
    "diyastolik": {
        "title": "DIYASTOLIK",
        "prompt": (
            "Diyastolik kan basinci degerini cikar.\n"
            "Format: SADECE SAYI yaz (mmHg birimi ekleme).\n"
            "Ornek: 102\n"
            "Bilgi yoksa bos birak."
        ),
    },
    "so2": {
        "title": "SO2",
        "prompt": (
            "Oksijen saturasyonu degerini cikar.\n"
            "Format: SADECE SAYI yaz (% birimi ekleme).\n"
            "Ornek: 98\n"
            "Bilgi yoksa bos birak."
        ),
    },
    "nabiz": {
        "title": "NABIZ",
        "prompt": (
            "Nabiz degerini cikar.\n"
            "Format: SADECE SAYI yaz (/dk birimi ekleme).\n"
            "Ornek: 82\n"
            "Bilgi yoksa bos birak."
        ),
    },
    "ates": {
        "title": "ATES",
        "prompt": (
            "Ates degerini cikar.\n"
            "Format: SADECE SAYI yaz (derece birimi ekleme).\n"
            "Ornek: 36.4\n"
            "Bilgi yoksa bos birak."
        ),
    },
    "tedavi": {
        "title": "TEDAVI",
        "prompt": (
            "Tedavi planini cikar.\n"
            "Format: BUYUK HARF, her kalemi '----' ile ayir.\n"
            "Ilac adlari, dozajlar ve kullanim sekli yazilmali.\n"
            "Ornek: AMLODIPIN 5 MG 1X1 BASLANDI ---- TUZ KISITLAMASI "
            "ONERILDI ---- 1 HAFTA SONRA KONTROL\n"
            "Bilgi yoksa 'BELIRTILMEDI' yaz."
        ),
    },
    "oneri": {
        "title": "ONERI",
        "prompt": (
            "Doktorun hastaya verdigi onerileri cikar.\n"
            "Format: BUYUK HARF, her oneriyi '----' ile ayir.\n"
            "Ornek: TUZ KISITLAMASI ---- DUZENLI EGZERSIZ ---- KILO KONTROLU\n"
            "Bilgi yoksa bos birak."
        ),
    },
    "uyari": {
        "title": "UYARI",
        "prompt": (
            "Onemli uyarilari cikar (alerji uyarisi, ilac etkilesimi vb.).\n"
            "Format: BUYUK HARF.\n"
            "Ornek: PENISILIN ALERJISI MEVCUT TEDAVI SECIMINDE DIKKAT\n"
            "Bilgi yoksa bos birak."
        ),
    },
    "kontrol_zamani": {
        "title": "KONTROL ZAMANI",
        "prompt": (
            "Kontrol randevu zamanini cikar.\n"
            "Format: BUYUK HARF.\n"
            "Ornek: 1 HAFTA SONRA TANSIYON KONTROLU\n"
            "Bilgi yoksa bos birak."
        ),
    },
    "agri_skalasi": {
        "title": "AGRI SKALASI",
        "prompt": (
            "Agri skalasi degerini cikar (VAS 0-10).\n"
            "Format: SADECE SAYI veya aciklama.\n"
            "Ornek: 7/10 veya VAS 7\n"
            "Bilgi yoksa bos birak."
        ),
    },
    "kilo": {
        "title": "KILO",
        "prompt": (
            "Hastanin kilosunu cikar.\n"
            "Format: SADECE SAYI yaz (kg birimi ekleme).\n"
            "Ornek: 86\n"
            "Bilgi yoksa bos birak."
        ),
    },
    "boy": {
        "title": "BOY",
        "prompt": (
            "Hastanin boyunu cikar.\n"
            "Format: SADECE SAYI yaz (cm birimi ekleme).\n"
            "Ornek: 174\n"
            "Bilgi yoksa bos birak."
        ),
    },
    "sikayet_baslangic_tarihi": {
        "title": "SIKAYET BASLANGIC TARIHI",
        "prompt": (
            "Sikayetin baslangic tarihini cikar.\n"
            "Format: BUYUK HARF.\n"
            "Ornek: 2 HAFTA ONCE veya 3 GUN ONCE\n"
            "Bilgi yoksa bos birak."
        ),
    },
    "konsultasyon_muayene": {
        "title": "KONSULTASYON MUAYENE",
        "prompt": (
            "Istenen konsultasyonlari cikar.\n"
            "Format: BUYUK HARF.\n"
            "Ornek: DIYETISYEN KONSULTASYONU ISTENDI\n"
            "Bilgi yoksa bos birak."
        ),
    },
    "konsultasyon_sonuc": {
        "title": "KONSULTASYON SONUC",
        "prompt": (
            "Konsultasyon sonuclarini cikar.\n"
            "Format: BUYUK HARF.\n"
            "Bilgi yoksa bos birak."
        ),
    },
    "konsultasyon_oneri": {
        "title": "KONSULTASYON ONERI",
        "prompt": (
            "Konsultasyon onerilerini cikar.\n"
            "Format: BUYUK HARF.\n"
            "Bilgi yoksa bos birak."
        ),
    },
    "icd10_list": {
        "title": "OLASI ICD10 TANI LISTESI",
        "prompt": (
            "Doktorun koydugu tani veya on tanilari ICD-10 koduyla cikar.\n"
            "Format: (KOD) - TANI ADI (On Tani/Kesin Tani)\n"
            "Ornek: (I10) - Esansiyel (primer) hipertansiyon (On Tani)\n"
            "Bilgi yoksa bos birak."
        ),
    },
    "sut_tetkik_list": {
        "title": "OLASI ISTENEN TETKIK VE TAHLILLER",
        "prompt": (
            "Doktorun istedigi tetkik ve tahlilleri cikar.\n"
            "Format: (SUT_KODU) - TETKIK ADI [brans]\n"
            "Bilgi yoksa bos birak."
        ),
    },
    # ----- Ortopedi-specific fields -----
    "hastalik_egitimi": {
        "title": "HASTALIK EGITIMI VERILDI MI",
        "prompt": (
            "Hastaya hastaligi hakkinda egitim verilip verilmedigini cikar.\n"
            "Format: BUYUK HARF.\n"
            "Ornek: EVET veya HAYIR\n"
            "Bilgi yoksa bos birak."
        ),
    },
    "hastanede_kullanilan_ilaclar": {
        "title": "HASTANEDE KULLANILAN ILACLAR",
        "prompt": (
            "Hastanede uygulanan/kullanilan ilaclari cikar.\n"
            "Format: BUYUK HARF, her ilaci '----' ile ayir.\n"
            "Ilac adi, dozaj ve uygulama yolu yazilmali.\n"
            "Ornek: PARASETAMOL 1 GR IV ---- DICLOFENAC 75 MG IM\n"
            "Bilgi yoksa bos birak."
        ),
    },
    "kullanmakta_oldugu_ilaclar": {
        "title": "KULLANMAKTA OLDUGU ILACLAR",
        "prompt": (
            "Hastanin halen kullanmakta oldugu ilaclari cikar.\n"
            "Format: BUYUK HARF, her ilaci '----' ile ayir.\n"
            "Ilac adi, dozaj ve kullanim sikligi yazilmali.\n"
            "Ornek: ARCOXIA 90 MG 1X1 ---- MYOLAX 1X1\n"
            "Bilgi yoksa bos birak."
        ),
    },
    "on_tani": {
        "title": "ON TANI",
        "prompt": (
            "Doktorun koydugu on taniyi cikar.\n"
            "Format: BUYUK HARF.\n"
            "Ornek: SERVIKAL MIYALJI veya LOMBER DISK HERNISI\n"
            "Bilgi yoksa bos birak."
        ),
    },
    "kesin_tani": {
        "title": "KESIN TANI",
        "prompt": (
            "Doktorun koydugu kesin taniyi cikar.\n"
            "Format: BUYUK HARF.\n"
            "Ornek: SERVIKAL MIYALJI veya OSTEOARTRIT\n"
            "Bilgi yoksa bos birak."
        ),
    },
}

# Fields where empty string is acceptable (not "BELIRTILMEDI")
OPTIONAL_FIELDS: set[str] = {
    "alerji", "uyari", "oneri", "agri_skalasi",
    "konsultasyon_muayene", "konsultasyon_sonuc", "konsultasyon_oneri",
    "sikayet_baslangic_tarihi", "kontrol_zamani", "icd10_list",
    "sut_tetkik_list",
    # ortopedi
    "hastalik_egitimi", "hastanede_kullanilan_ilaclar",
    "kullanmakta_oldugu_ilaclar", "on_tani", "kesin_tani",
}

# Fields that expect only numeric values
NUMERIC_FIELDS: set[str] = {
    "sistolik", "diyastolik", "so2", "nabiz", "ates", "kilo", "boy",
}

# ---------------------------------------------------------------------------
# Branch-specific section ordering — defines which fields appear (and order)
# ---------------------------------------------------------------------------

DAHILIYE_SECTION_KEYS: list[str] = [
    "hastanin_yakinmasi",
    "hastanin_oykusu",
    "oz_gecmisi_soy_gecmisi",
    "soy_gecmisi",
    "sigara",
    "alkol",
    "alerji",
    "muayene_bulgulari",
    "sistolik",
    "diyastolik",
    "so2",
    "nabiz",
    "ates",
    "tedavi",
    "oneri",
    "uyari",
    "kontrol_zamani",
    "agri_skalasi",
    "kilo",
    "boy",
    "sikayet_baslangic_tarihi",
    "konsultasyon_muayene",
    "konsultasyon_sonuc",
    "konsultasyon_oneri",
    "icd10_list",
    "sut_tetkik_list",
]

ORTOPEDI_SECTION_KEYS: list[str] = [
    "hastalik_egitimi",
    "sikayet_baslangic_tarihi",
    "hastanede_kullanilan_ilaclar",
    "hastanin_oykusu",
    "hastanin_yakinmasi",
    "kesin_tani",
    "kontrol_zamani",
    "kullanmakta_oldugu_ilaclar",
    "muayene_bulgulari",
    "on_tani",
    "tedavi",
    "icd10_list",
    "sut_tetkik_list",
]


def get_anamnesis_sections(brans: str | None = None) -> dict[str, dict[str, str]]:
    """Return ordered section definitions for a given specialty (brans).

    Defaults to dahiliye when brans is unknown or empty.
    """
    normalized = (brans or "").strip().lower()
    keys = ORTOPEDI_SECTION_KEYS if normalized == "ortopedi" else DAHILIYE_SECTION_KEYS
    return {k: ANAMNESIS_SECTIONS[k] for k in keys}


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
        diagnosis = r.metadata.get("diagnosis", "")
        field_title = r.metadata.get("field_title", "")
        prefix = ""
        if field_title and diagnosis:
            prefix = f"[{field_title} | {diagnosis}] "
        elif field_title:
            prefix = f"[{field_title}] "
        elif diagnosis:
            prefix = f"[{diagnosis}] "
        lines.append(f"- {prefix}{r.content}")
    return "\n".join(lines)


def build_section_prompt(
    section_key: str,
    transcript: str,
    entities: list[MedicalEntity],
    rag_context: list[RAGResult],
) -> str:
    """Build the full prompt for a single HBYS report field."""
    meta = ANAMNESIS_SECTIONS[section_key]

    # Determine empty-field behavior based on whether field is optional
    if section_key in OPTIONAL_FIELDS or section_key in NUMERIC_FIELDS:
        empty_instruction = (
            "Bu alan opsiyoneldir. Transkriptte bilgi yoksa SADECE bos string don. "
            "'BELIRTILMEDI' yazma, hicbir sey yazma."
        )
    else:
        empty_instruction = (
            "Transkriptte bu alan icin bilgi yoksa 'BELIRTILMEDI' yaz."
        )

    return (
        f"<TRANSKRIPT>\n{transcript}\n</TRANSKRIPT>\n\n"
        f"<TIBBI_BILGILER>\n{_format_entities(entities)}\n"
        f"UYARI: Yukaridaki tibbi bilgiler otomatik cikarilmistir. "
        f"Her birini transkriptte dogrula. Transkriptte gecmeyeni KULLANMA.\n"
        f"</TIBBI_BILGILER>\n\n"
        f"<REFERANS>\n"
        f"Asagidaki referanslar SADECE format ornegi icindir. "
        f"Referanstaki hastaliklari, semptomlari veya bulgulari KOPYALAMA. "
        f"ICERIK olarak sadece transkripti kullan.\n\n"
        f"{_format_rag_context(rag_context)}\n"
        f"</REFERANS>\n\n"
        f"GOREV: {meta['prompt']}\n\n"
        f"{empty_instruction}\n\n"
        f"ALAN: {meta['title']}\n"
        f"Sadece bu alanin icerigini yaz. Alan basligi ekleme. "
        f"Transkriptte gecmeyen hicbir tibbi terim ekleme."
    )
