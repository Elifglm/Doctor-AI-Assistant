"""Few-shot examples for anamnesis report generation.

These examples help the LLM understand the expected output format and style.
They can be prepended to the system prompt for better quality.
"""

# Example 1: Basic outpatient visit
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
    "chief_complaint": "Bir haftadir devam eden bas agrisi, ozellikle sabahlari.",
    "history_present": (
        "Hasta bir haftadir devam eden bas agrisindan yakinmaktadir. "
        "Agri ozellikle ense bolgesinde ve sakaklarda yogunlasmaktadir. "
        "Sabah kaldiginda daha belirgin olmaktadir. Hafif bulanti eslik "
        "etmektedir, kusma yok. Eczanede olculen tansiyon degeri 150/95 mmHg."
    ),
    "past_medical": "Belirtilmedi",
    "medications": "Hicbir ilac kullanmiyor.",
    "allergies": "Belirtilmedi",
    "family_history": "Anne: hipertansiyon. Baba: diabetes mellitus.",
    "social_history": "Sigara: gunde 1 paket, 10 yildir.",
    "review_systems": "Bas agrisi ve hafif bulanti mevcut. Kusma yok.",
    "physical_exam": "Tansiyon: 155/98 mmHg.",
    "assessment": "Hipertansiyon (yeni tani).",
    "plan": (
        "1. Amlodipin 5 mg, gunde 1 kez baslandi.\n"
        "2. Kan tahlili istendi.\n"
        "3. EKG istendi.\n"
        "4. Goz dibi muayenesi istendi.\n"
        "5. Bir hafta sonra kontrol randevusu."
    ),
    "notes": "Belirtilmedi",
}


def get_few_shot_prompt() -> str:
    """Return a formatted few-shot example for the system prompt."""
    sections_text = "\n\n".join(
        f"**{key}**: {value}" for key, value in EXAMPLE_SECTIONS_1.items()
    )
    return (
        f"ORNEK TRANSKRIPT:\n{EXAMPLE_TRANSCRIPT_1}\n\n"
        f"BEKLENEN RAPOR CIKTISI:\n{sections_text}"
    )
