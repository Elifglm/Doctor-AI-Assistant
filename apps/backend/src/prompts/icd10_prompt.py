"""LLM prompts for ICD-10 code extraction from transcripts."""

# Step 1: Extract diagnoses/symptoms from transcript (grounded extraction)
DIAGNOSIS_EXTRACTION_PROMPT = """\
Sen bir Turkce tibbi transkript analiz uzmanisin. Asagidaki doktor-hasta gorusme \
transkriptini analiz ederek SADECE transkriptte ACIKCA bahsedilen tani, semptom ve \
klinik bulgulari cikar.

KRITIK KURALLAR:
- SADECE transkriptte gercekten gecen bilgileri cikar.
- Transkriptte bahsedilmeyen HICBIR tani veya semptom ekleme.
- Tahmin yapma, varsayimda bulunma, cikarimda bulunma.
- Eger bir ilac bahsediliyorsa, SADECE doktor o ilacin ne icin verildiyse onu yaz. \
  Ilacin kullanilabilecegi diger hastaliklari EKLEME.
- Eger transkriptte hicbir tani veya semptom yoksa bos liste don: []

HER BULGU ICIN BELIRT:
- "metin": Transkriptte gecen orijinal ifade (alinti)
- "tip": "kesin_tani" (doktor acikca tani koydu), "on_tani" (doktor supheleniyor), \
  "semptom" (hasta bildirdi), "bulgu" (muayene bulgulari)
- "kaynak": "doktor" veya "hasta" (kim soyledi)

TRANSKRIPT:
{transcript}

Yanit (sadece JSON listesi, baska bir sey yazma):
"""

# Step 2: Map extracted diagnoses to ICD-10 codes
ICD10_CODING_PROMPT = """\
Sen bir Turkce ICD-10 kodlama uzmanisin. Asagida bir doktor-hasta gorusmesinden \
cikarilmis tani ve semptom listesi verilmistir. Bu bulgulari ICD-10 kodlarina esle.

KRITIK KURALLAR:
- SADECE asagidaki listede verilen bulgulari kodla. Listeye EKLEME YAPMA.
- Listede olmayan HICBIR tani veya semptom icin kod onerme.
- Doktor kesin tani belirttiyse, semptom kodu (R grubu) yerine hastalik kodunu tercih et.
- Gercekte var olmayan ICD-10 kodlari UYDURMA. Emin olmadigin kodlarda genel kodu kullan.
- Her oneri icin guven skoru (0.0-1.0) belirt.
- Maksimum 5 oneri sun, en yuksek guvenden dusuge sirala.
- Eger liste bos ise bos liste don: []

CIKARILMIS BULGULAR:
{findings}

ORNEK YANIT:
[
  {{"tani_adi": "Esansiyel (primer) hipertansiyon", "icd_kodu_tahmini": "I10", \
"confidence": 0.95, "reasoning": "Doktor acikca hipertansiyon tanisi koydu", \
"kaynak_metin": "Hipertansiyon tanisi koyuyorum"}}
]

Yanit (sadece JSON listesi, baska bir sey yazma):
"""

# Legacy single-step prompt (kept for fallback but improved with stronger guardrails)
ICD10_EXTRACTION_PROMPT = """\
Sen bir Turkce tibbi kodlama uzmanisin. Asagidaki doktor-hasta gorusme transkriptini \
analiz ederek olasi ICD-10 tani kodlarini belirle.

!!! KRITIK UYARI !!!
- SADECE transkriptte ACIKCA bahsedilen tani ve semptomlari kodla.
- Transkriptte gecmeyen HICBIR hastalik, tani veya semptom icin kod ONERME.
- Ilaclardan hastalik CIKARIMI YAPMA (ornek: metformin gordugun icin diyabet ekleme, \
  SADECE doktor veya hasta diyabetten bahsettiyse ekle).
- Tahmin etme, varsayimda bulunma. Transkriptte yoksa EKLEME.

ANALIZ ADIMLARI:
1. Transkripti dikkatlice oku.
2. Doktorun acikca soyledigi tanilari bul (ornek: "hipertansiyon tanisi koyuyorum").
3. Hastanin belirttigi semptomlari tespit et (ornek: "basim agriyor", "sekerim yuksek").
4. Fizik muayene bulgularini ve vital degerleri not et.
5. SADECE yukaridaki adimlardan bulunan bilgilerle ICD-10 kodlarini cikar.

KURALLAR:
- Doktor kesin tani belirttiyse, semptom kodu (R grubu) yerine hastalik kodunu tercih et.
- Birden fazla tani olabilecegini goz onunde bulundur (komorbidite).
- Transkriptte acikca belirtilmeyen detaylari VARSAYMA. Genel kod yeterli ise spesifik kod onerme.
- Gercekte var olmayan ICD-10 kodlari UYDURMA.
- Transkriptte yeterli klinik bilgi yoksa bos liste don: []
- Her oneri icin guven skoru (0.0-1.0) belirt.
- Maksimum 5 oneri sun, en yuksek guvenden dusuge sirala.
- Sadece JSON formatinda yanit ver, baska bir sey yazma.
- Her oneri icin "kaynak_metin" alani ekle: transkriptteki ilgili cumleyi alintila.

ORNEK 1:
Transkript: "Doktor: Tansiyonunuz 160/100 cikti. Hipertansiyon tanisi koyuyorum. Amlodipin 5mg baslayalim."
Yanit:
[
  {{"tani_adi": "Esansiyel (primer) hipertansiyon", "icd_kodu_tahmini": "I10", \
"confidence": 0.95, "reasoning": "Doktor acikca hipertansiyon tanisi koydu, TA: 160/100", \
"kaynak_metin": "Hipertansiyon tanisi koyuyorum"}}
]

ORNEK 2 (HALLUSINASYON ORNEGI - YAPMA!):
Transkript: "Hasta: Sekerim yuksek cikiyor. Doktor: Kan tahlili isteyelim."
YANLIS yanit (YAPMA!):
[
  {{"tani_adi": "Tip 2 diyabet", "icd_kodu_tahmini": "E11", ...}},
  {{"tani_adi": "Astim", "icd_kodu_tahmini": "J45", ...}}
]
DOGRU yanit:
[
  {{"tani_adi": "Anormal kan glukoz duzeyi", "icd_kodu_tahmini": "R73.0", \
"confidence": 0.65, "reasoning": "Hasta seker yuksekligi bildirdi, henuz kesin tani yok", \
"kaynak_metin": "Sekerim yuksek cikiyor"}}
]

TRANSKRIPT:
{transcript}

Yanit (sadece JSON):
"""
