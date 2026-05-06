"""JSON schema for the 26-field HBYS anamnesis report.

Used as `format` parameter in Ollama API calls (structured output) so the local
LLM (Gemma 4 etc.) cannot drift from the schema. Anthropic/Gemini providers
ignore this — their schema compliance is enforced via the system prompt.
"""

ANAMNEZ_FIELDS = [
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

ANAMNEZ_JSON_SCHEMA = {
    "type": "object",
    "properties": {field: {"type": "string"} for field in ANAMNEZ_FIELDS},
    "required": ANAMNEZ_FIELDS,
    "additionalProperties": False,
}
