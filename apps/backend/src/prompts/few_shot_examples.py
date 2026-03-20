"""Few-shot examples for HBYS-format anamnesis report generation.

These examples help the LLM understand the expected HBYS output format.
They can be prepended to the system prompt for better quality.
"""

# Example 1: Basic outpatient visit — hypertension
EXAMPLE_TRANSCRIPT_1 = """\
Doktor: Hosgeldiniz, nasilsiniz?
Hasta: Merhaba doktor bey. Son bir haftadir basim cok agriyor, ozellikle sabah kaldigimda.
Doktor: Bas agriniz nerede yogunlasiyor?
Hasta: Daha cok ense bolgesinde ve bazen sakaklarda.
Doktor: Bulanti, kusma var mi?
Hasta: Bazen hafif bulantim oluyor ama kusmadim.
Doktor: Tansiyonunuz olculmus mu son zamanlarda?
Hasta: Eczanede olcturdum, 150/95 cikti.
Doktor: Baska bir ilac kullaniyor musunuz?
Hasta: Hayir, hicbir ilac kullanmiyorum.
Doktor: Ailede tansiyon hastasi var mi?
Hasta: Annem tansiyon hastasi, babam da seker hastasi.
Doktor: Sigara kullaniyor musunuz?
Hasta: Evet, gunde bir paket iciyorum, 10 yildir.
Doktor: Tansiyonunuzu olcelim. 155/98 cikti. Kan tahlili ve EKG istiyorum. \
Bir de goz dibi baktiracagiz. Su an icin amlodipin 5 mg baslayalim, gunde bir kez.
Hasta: Tamam doktor bey.
Doktor: Bir hafta sonra kontrole gelin, tahlil sonuclariyla birlikte.
"""

EXAMPLE_SECTIONS_1 = {
    "hastanin_yakinmasi": "BAS AGRISI",
    "hastanin_oykusu": (
        "1 HAFTADIR BAS AGRISI MEVCUT ---- ENSE BOLGESINDE VE SAKAKLARDA "
        "YOGUNLASIYOR ---- SABAHLARI BELIRGIN ---- HAFIF BULANTI ESLIK "
        "EDIYOR KUSMA YOK ---- ECZANEDE TANSIYON 150/95 OLCULMUS"
    ),
    "oz_gecmisi_soy_gecmisi": "BILINEN KRONIK HASTALIK YOK ---- ILAC KULLANMIYOR",
    "soy_gecmisi": "ANNE HT ---- BABA DM",
    "sigara": "KULLANIYOR (1 PAKET/GUN, 10 YILDIR)",
    "alkol": "BELIRTILMEDI",
    "alerji": "",
    "muayene_bulgulari": "BELIRTILMEDI",
    "sistolik": "155",
    "diyastolik": "98",
    "so2": "",
    "nabiz": "",
    "ates": "",
    "tedavi": (
        "AMLODIPIN 5 MG 1X1 BASLANDI ---- KAN TAHLILI ISTENDI "
        "---- EKG ISTENDI ---- GOZ DIBI MUAYENESI ISTENDI"
    ),
    "oneri": "",
    "uyari": "",
    "kontrol_zamani": "1 HAFTA SONRA KONTROL",
    "agri_skalasi": "",
    "kilo": "",
    "boy": "",
    "sikayet_baslangic_tarihi": "1 HAFTA ONCE",
    "konsultasyon_muayene": "GOZ DIBI MUAYENESI ISTENDI",
    "konsultasyon_sonuc": "",
    "konsultasyon_oneri": "",
    "icd10_list": "(I10) - Esansiyel (primer) hipertansiyon (On Tani)",
}


def get_few_shot_prompt() -> str:
    """Return a formatted few-shot example for the system prompt."""
    sections_text = "\n\n".join(
        f"**{key}**: {value}" for key, value in EXAMPLE_SECTIONS_1.items()
    )
    return (
        f"ORNEK TRANSKRIPT:\n{EXAMPLE_TRANSCRIPT_1}\n\n"
        f"BEKLENEN HBYS CIKTISI:\n{sections_text}"
    )
