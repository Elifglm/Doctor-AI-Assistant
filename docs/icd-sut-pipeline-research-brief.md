# ICD-10 ve SUT Tetkik Pipeline'ları — Araştırma Brief'i

> **Kim için yazıldı:** Bu pipeline'ların iyileştirilmesi üzerine literatür/yöntem araştırması yapacak kişi için. Projenin önceden bilgisi olmadan okuyup tüm detayları anlayabilmesi hedeflendi.
>
> **Sonuç ne:** "Şu kısımları nasıl iyileştirebiliriz?" sorusuna araştırmaya dayalı (literatür + benzer sistemler + alternatif teknikler) somut öneriler.

---

## 1. Proje Bağlamı (5 dakikalık özet)

**KlinikAsistan**, Türkiye polikliniklerinde doktorların hasta görüşmesi sırasında ses kaydı alıp otomatik anamnez raporu üreten bir AI asistanı. Tezdeki amaç **"AI ile dahiliye konsültasyonlarının yapılandırılmış belgelenmesi"**.

Pipeline yüksek seviyeden:
```
Audio → Whisper ASR → Türkçe transkript
                           ↓
                  ┌────────┴────────┐
                  │ ReportGenerator │
                  │   (orchestrator)│
                  └────────┬────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ↓                  ↓                  ↓
   Anamnez batch       ICD-10 öneri      SUT tetkik öneri
   (26 alan, tek      (hastalık kodları)  (tahlil/tetkik
   LLM çağrısı)                            kodları, intent)
```

**Bu rapor SADECE 2 alt-sistemi ele alıyor: ICD-10 ve SUT tetkik öneri.** Anamnez batch generation ayrı konu.

### 1.1 ICD-10 Nedir, Niye Öneriyoruz?
ICD-10: WHO'nun uluslararası hastalık kodlama standardı (ör: `E11.9` = "Tip 2 diyabet, komplikasyonsuz"). Türkiye'de SGK faturalandırma için zorunlu. Doktor görüşmede "hastanın diyabeti var" dediğinde, sistemin bunu `E11.9` koduna çevirip rapora yazması gerekiyor.

**Veritabanı:** SQLite, **11,332 ICD-10 kodu** Türkçe tanı isimleriyle (`data/icd10.db`).

### 1.2 SUT Tetkik Nedir, Niye Öneriyoruz?
SUT (Sağlık Uygulama Tebliği): Türkiye Sağlık Bakanlığı'nın tahlil/tetkik kodlama listesi (ör: `L107020` = "Tam Kan Sayımı (Hemogram)"). Doktor "hemogram istiyorum" dediğinde sistem bu koda çevirmeli.

**Veritabanı:** SQLite, **603 SUT tetkik kodu** + branş (`data/sut_tetkik.db`).

**SUT'ta ek zorluk — Intent Disambiguation:**
Transkriptte "hemogram" geçen her cümle istek değildir:
- ✅ Doktor: "Tam kan sayımı isteyelim" → REQUEST
- ❌ Hasta: "Geçen sefer hemogram baktırmıştım" → PAST_DONE
- ❌ Doktor: "Eğer şeker yüksekse hemogram bakarız" → HYPOTHETICAL
- ❌ Hasta: "Hemogram baktırmaya gerek var mı?" → PATIENT_QUESTION

Bu yüzden SUT için **morfoloji-aware intent classifier** prompt'u geliştirildi (V3 prompt).

---

## 2. Mevcut Pipeline Mimarisi — Hibrit Retrieval + LLM Selection

Her iki katman da aynı 4-aşamalı tasarımı izliyor:

```
┌────────────────────────────────────────────────────────────────────┐
│ STAGE 1: NER (Named Entity Recognition)                            │
│   GLiNER (zero-shot, multilingual): tibbi terim çıkarımı          │
│   Çıktı: ['diyabet', 'hipertansiyon', 'tam kan sayımı']           │
└────────────────────────────┬───────────────────────────────────────┘
                             ↓
┌────────────────────────────────────────────────────────────────────┐
│ STAGE 2: Sinonim/Token Genişletme                                  │
│   - Tıbbi sinonim sözlüğü (medical_synonyms.json)                  │
│     "şeker" → "diyabet, glukoz, kan şekeri"                        │
│   - Stop-word stripping (Türkçe noise tokens)                      │
│   - Significant token isolation                                    │
│     "MENENJİT İHTİMALİ GÖZE ALINIYOR" → "menenjit"                 │
└────────────────────────────┬───────────────────────────────────────┘
                             ↓
┌────────────────────────────────────────────────────────────────────┐
│ STAGE 3: RAG Candidate Generation (multi-channel)                  │
│   3a. Vector search (BGE-M3 + ChromaDB)                            │
│       Her terim için top-3 semantic neighbors, threshold ≥ 0.45    │
│   3b. Text search fallback (SQLite LIKE)                           │
│       Vector miss durumunda kelime-bazlı arama                     │
│   3c. LLM-explicit extraction (sadece "strict" modda)              │
│       LLM raporu okuyup HASTALIK isimlerini çıkarır,               │
│       isimlerini DB'de arayıp aday havuzuna ekler                  │
│   3d. Hierarchical augmentation (sadece ICD)                       │
│       J44.0 candidate ise → J44.9 ve J44'ü de havuza ekle          │
│   → Tipik output: 30-70 ICD aday / 25-50 SUT aday                  │
└────────────────────────────┬───────────────────────────────────────┘
                             ↓
┌────────────────────────────────────────────────────────────────────┐
│ STAGE 4: LLM Selection (Anthropic Claude)                          │
│   - Aday havuzu + tam transcript/anamnez LLM'e verilir             │
│   - Klinik muhakeme prompt'u:                                      │
│     * Disease code over symptom code                               │
│     * Specificity .9 if ambiguous                                  │
│     * Differential diagnosis logic                                 │
│   - LLM 3-6 kod seçer (JSON output)                                │
└────────────────────────────┬───────────────────────────────────────┘
                             ↓
┌────────────────────────────────────────────────────────────────────┐
│ STAGE 5: Hallucination Guard                                       │
│   "strict" mode: aday havuzunda olmayan kod ATILIR                 │
│   "db_rescue" mode: havuz dışı kod DB'de varsa kabul edilir        │
│   (Tez ablation switch'i — recall vs precision tradeoff)           │
└────────────────────────────────────────────────────────────────────┘
```

---

## 3. Stage-by-Stage Detaylı Açıklama

### 3.1 NER — GLiNER (Zero-shot Multi-label)

**Model:** `urchade/gliner_multi-v2.1` — multilingual zero-shot NER, ~500MB CPU model.

**Niye GLiNER?**
- Zero-shot (özel eğitim yok) → Türkçe medical NER datasetimiz yok, fine-tune imkanı sınırlı
- Multi-label (aynı span birden fazla etikete sahip olabilir)
- Free, on-device

**Etiketler** (`MEDICAL_LABELS` listesi):
```
semptom, hastalik, ilac, dozaj, alerji, ameliyat,
tibbi_test, vucud_bolumu, sure, aile_hastaligi,
sigara, alkol, meslek
```

**Threshold:** 0.5 (config'den ayarlanabilir).

**Çıktı:**
```python
[
    {"text": "diyabet", "label": "hastalik", "score": 0.92},
    {"text": "tam kan sayımı", "label": "tibbi_test", "score": 0.88},
    ...
]
```

**Bilinen zayıf nokta:**
- ASR hatalarına duyarlı: "hemogran" (yanlış yazım) yakalanmayabilir
- 1-2 kelimelik kısa formlar (T3, T4, TSH) düşük skor alabilir
- Türkçe morfoloji: "şekerime" → "şeker" çıkarımı zayıf

### 3.2 Sinonim Sözlüğü (`medical_synonyms.json`)

**Yapı:**
```json
{
  "diseases": [
    {
      "tibbi_terim_tr": "Diabetes Mellitus",
      "kisaltma": "DM",
      "halk_dili": ["şeker hastalığı", "şeker", "kandaki şeker"]
    },
    ...
  ],
  "lab_tests": [...],
  "symptoms": [...],
  "imaging": [...],
  "medications": [...]
}
```

**Build-time:** Manuel olarak hazırlanmış (~728 entry). 5 kategori.

**Run-time expansion logic:**
```python
NER terms = ["şeker", "tansiyon"]
   ↓
Synonym expansion:
   "şeker" → ["DM", "Diabetes Mellitus", "şeker hastalığı"]
   "tansiyon" → ["HT", "Hipertansiyon", "yüksek tansiyon"]
   ↓
Token-level significant extraction (stop-word strip):
   "MENENJİT İHTİMALİ GÖZE ALINIYOR" → "menenjit"
   ↓
Output: NER + sinonimler + significant tokens (deduplicated)
```

**Açık problem:** Sözlük statik. Yeni hastalık eklenirse manuel güncelleme gerek.

### 3.3 Vector Search — BGE-M3 + ChromaDB

**Embedding model:** `BAAI/bge-m3` (multilingual, dense, 1024-dim)

**Niye BGE-M3?**
- Türkçe destekli (tabloda 100+ dil, Türkçe anlamlı temsil)
- Tıbbi metin için MiniLM'den daha iyi (proje testlerinde)
- Query/passage prefix gerektirmez (E5 ailesinin aksine)

**Vector DB:**
- ChromaDB (persistent, local)
- ICD: 11,332 kod indexli (`data/icd10_chroma_bge/`)
- SUT: 603 kod indexli (`data/sut_tetkik_chroma_bge/`)

**Indexing zamanı (build_*_vectors.py script'leri):**
- Her kod için `tani` (ICD) veya `adi` (SUT) text BGE-M3 ile encode edilir
- Vector + metadata (kod, tani, kategori) Chroma'ya yazılır

**Search:**
```python
async def search_multiple(terms: list[str], n_per_term: int = 3, min_score: float = 0.45):
    for term in terms:
        embedding = bge_m3.encode(term, normalize=True)
        chroma_results = collection.query(query_embeddings=[embedding], n_results=3)
        # Cosine similarity (1-distance), ≥ 0.45 threshold
        # Deduplicate: aynı kod birden fazla terimde gelirse en yüksek skor tutulur
    return sorted(results, key=lambda r: -r.score)
```

**Bilinen zayıflık:**
- Threshold çok düşük → noise candidates (örn `5-Hidroksi indol asetik asit/Kreatinin (Spot idrar)` → "kreatinin" sorgusu için top hit)
- Threshold çok yüksek → recall miss (T07 gastrit case'i: doğru K29.7 sorgu kanalına girmedi)
- Dense embedding parlak terimi gizler: "MENENJİT İHTİMALİ" sorgusunda "menenjit" sinyalini "ihtimal/göze alıyor" filler'ları gölgeleyebilir → workaround: token isolation (yukarıda)

### 3.4 LLM-Explicit Extraction (sadece strict modda)

ICD pipeline'ında ek bir LLM çağrısı:
```python
async def _llm_extract_diagnoses_and_symptoms(report_text):
    prompt = """Aşağıdaki tıbbi rapor metninde HASTALIK TANISI ve SEMPTOM
    isimlerini çıkar. JSON: {"tani":[...], "semptom":[...]}"""
    response = await llm.generate(prompt)
    parsed = json.loads(response)  # {"tani":["DM","HT"], "semptom":["dispne"]}
    # Bu isimleri SQLite ICD DB'de search ediliyor → adaylar pool'a ekleniyor
```

**Niye var?** Vector search Türkçe karakter ASCII-fold yaptığında "İ" → "i" gibi dönüşümlerde kayıp yaşıyordu. LLM "DM" kısaltmasını gördüğünde "Diabetes Mellitus" → DB search → E11.9 zincirini kuruyor.

**Maliyet:** 1 ekstra Anthropic çağrısı / kayıt.

**db_rescue modunda atlanır** çünkü hallucination guard zaten DB validation yapıyor (kullanım amacı çakışıyor).

### 3.5 Hierarchical Augmentation (sadece ICD)

ICD-10'un hiyerarşik yapısı:
```
J44      (KOAH ana kategori)
├── J44.0  (akut alt solunum yolu enfeksiyon ile)
├── J44.1  (akut alevlenme)
└── J44.9  (tanımlanmamış)
```

Eğer vector arama `J44.0`'ı bulduysa, sistem otomatik olarak `J44.9` (unspecified) ve `J44` (parent) kodlarını da aday havuzuna ekler. **Niye?** LLM "yetersiz kanıt → .9 unspecified tercih et" kuralını uygulayabilsin diye.

**Kod:**
```python
async def _augment_with_unspecified(candidates, seen):
    wanted = set()
    for c in candidates:
        kodu = c["icd_kodu"]  # örn "J44.0"
        if "." not in kodu:
            wanted.add(f"{kodu}.9")
            continue
        parent = kodu.split(".")[0]  # "J44"
        wanted.add(parent)            # parent
        wanted.add(f"{parent}.9")     # ".9 unspecified"
    # SQL fetch + add to pool
```

### 3.6 LLM Selection — Klinik Muhakeme Prompt'u

#### 3.6.1 ICD-10 Selection Prompt (anamnez-bazlı)

`apps/backend/src/services/icd10_suggestion_service.py:77` — `ICD10_REPORT_SELECTION_PROMPT`

```
Sen bir deneyimli tıbbi kodlama uzmanısın. Aşağıda bir anamnez raporunun
ilgili alanları ve ICD-10 aday kodları verilmiştir.

GÖREV: Aday kodlardan rapora KLİNİK OLARAK uygun olanları seç.
İki kategoriye göre kodla:

[ASAMA A — "tani"] AÇIK TANI KODLARI (confidence 0.85-0.95):
- Doktorun "kesin_tani", "on_tani" veya "oz_gecmisi_soy_gecmisi"
  alanlarında AÇIKÇA yazdığı hastalık kodları (KAH, DM, HT, KOAH, KBY...).

[ASAMA B — "semptom"] SEMPTOM KODLARI (confidence 0.65-0.80):
- Doktor net tanı koymamış ama RAPORDA SEMPTOM AÇIKÇA GEÇİYORSA,
  ICD-10'un R-bölümünden semptom kodunu seç.

ÇIKARIM YAPMA — DOKTOR DEMEDİYSE TAHMİN ETME:
- Tedaviye/konsültasyon istemine bakarak hastalığa atlama (ramipril
  varsa I10 EKLEME — bu tahmin olur).
- Doktor sadece tetkik istedi, tanı koymadıysa, sadece SEMPTOM kodlarını seç.

KRİTİK KURALLAR:
1. SADECE aşağıdaki ADAY ICD-10 KODLARI listesindeki kodları kullan. Kod uydurma.
2. Bir semptom başka bir hastalığın sonucu olabiliyorsa, hastalık kodunu
   semptom kodu yerine tercih et.
   - Örnek: "Baş dönmesi + anemi bulguları" → D50 (anemi) seç, R42 (vertigo) ATLA.
3. SPESİFİKLİK — alt-tip seçimi:
   - Yetersiz kanıt varsa "tanımlanmamış" alt kodu (.9 ile biten) tercih et.
   - KOAH var ama akut enfeksiyon yok → J44.9 seç, J44.0 SEÇME.
   - Diyabet var ama tip/komplikasyon belirsiz → E11.9 seç.
4. Birden fazla hastalık/semptom varsa hepsini listele.
5. Maksimum 6 kod (3 tani + 3 semptom).

ANAMNEZ RAPORU:
{report_text}

ADAY ICD-10 KODLARI:
{candidates}

Yanıt (sadece JSON, başka bir şey yazma):
[
  {"icd_kodu":"E11.9","tani":"Tip 2 DM","confidence":0.92,"source":"tani","reasoning":"..."},
  {"icd_kodu":"R06.0","tani":"Dispne","confidence":0.78,"source":"semptom","reasoning":"..."}
]
```

#### 3.6.2 SUT Intent Disambiguation Prompt V3

`apps/backend/src/services/sut_suggestion_service.py:260` — `SUT_SELECTION_PROMPT_V3`

V3 prompt'un en önemli özelliği **adım adım Türkçe morfoloji analizi**:

```
ADIM ADIM AKIL YÜRÜTME (her aday için):

1. **kaynak_cumle**: tetkikin geçtiği TAM cümleyi transkriptten çıkar.
   "Doktor:" / "Hasta:" prefix'i koru.

2. **konuşmacı**: cümle "Doktor:" ile başlıyorsa DOCTOR, "Hasta:" ile
   başlıyorsa PATIENT. Belirsizse OTHER.

3. **liste_kontekst** (KRİTİK YENİ KURAL):
   Cümlede iki nokta (":") veya "şunlar/şunları/aşağıdakileri" gibi
   liste başlatıcı varsa VE liste içinde virgülle ayrılmış birden fazla
   tetkik adı varsa → liste başındaki ANA FİİLİ tespit et ve onun
   tense'ini liste öğelerine MİRAS olarak uygula.
   Örnek:
     "Tahliller isteyeceğiz: TSH, T3, T4, anti-TPO, hemogram"
     → ana fiil: "isteyeceğiz" (FUTURE)
     → liste öğeleri (TSH, T3, T4, anti-TPO, hemogram) HEPSİ FUTURE
     → her biri için intent: REQUEST

4. **zaman_kipi**: Türkçe morfoloji ipuçları:
   - PAST_NARRATIVE: -mIştI, -mIş, -dI ekleri
     ("baktırmıştım", "yaptırdım", "geldi", "bakmıştık")
   - OPTATIVE: -AlIm 1.çoğul ("isteyelim", "bakalım", "yapalım")
   - FUTURE: -AcAk ("isteyeceğim" 1.tekil, "isteyeceğiz" 1.çoğul)
   - **IMPERATIVE_PASSIVE: -sIn 3.tekil pasif emir**
     ("bakılsın", "yapılsın", "istensin", "ölçülsün") — REQUEST sayılır
   - IMPERATIVE_ACTIVE: 2.tekil/çoğul emir ("iste", "bak", "isteyin")
   - HYPOTHETICAL: -sA + ana cümle
     ("şeker yüksekse insülin bakarız", "gerekirse holter takarız")
   - INTERROGATIVE: soru ("- mi?", "- mı?", "lazım mı?", "bakalım mı?")
   - DECLARATIVE: düz haber cümlesi

5. **intent_etiketi**:
   - REQUEST: konuşmacı=DOCTOR + (FUTURE | OPTATIVE | IMPERATIVE_*)
     + olumlu cümle. SADECE bu seçilir.
   - PAST_DONE: zaman_kipi=PAST_NARRATIVE (kim söylerse söylesin)
   - PATIENT_QUESTION: konuşmacı=PATIENT + INTERROGATIVE
   - HYPOTHETICAL: -sA + ana cümle yapısı
   - RESULT_DISCUSS: tetkik sonucu konuşuluyor ("CRP 5 gelmiş")
   - OTHER: diğer

6. **include**: intent_etiketi == REQUEST AND aday listesinde kod var

NEGATİF ÖRNEKLER (HİÇ DAHIL ETME):
- "Hasta: öz geçmişte hemogram baktırdım" → PATIENT/PAST_NARRATIVE → EXCLUDE
- "Doktor: iki yıl önce şeker baktınız" → DOCTOR/PAST_NARRATIVE → EXCLUDE
- "Doktor: şekerin yüksekse insülin bakarız" → HYPOTHETICAL → EXCLUDE
- "Hasta: D vitamini bakar mıyız?" → PATIENT_QUESTION → EXCLUDE
- "Doktor: CRP 12 gelmiş" → RESULT_DISCUSS → EXCLUDE

POZİTİF ÖRNEKLER (SEÇ):
- "Doktor: tam kan isteyelim" → REQUEST
- "Doktor: troponin ve EKG isteyeceğim" → REQUEST (iki ayrı mention)
- "Doktor: bir de B12 bakalım" → REQUEST
- "Anti-TPO bakılsın" → IMPERATIVE_PASSIVE → REQUEST
```

V3 vs V2 farkı: V3'e eklenen **3 bug-fix**:
1. **Liste-mirası**: V2'de virgüllü liste öğelerinin tense'i çıkarılamıyordu → her öğe DECLARATIVE/OTHER işaretleniyordu
2. **Pasif imperative**: V2'de `-sIn` ekli emirler atlanıyordu
3. **Hypothetical detection**: V2 `-sA` koşullu cümleyi REQUEST gibi işaretleyebiliyordu

### 3.7 Hallucination Guard (Strict vs DB-Rescue)

**Strict mode** (default):
```python
for code in llm_response:
    if code in candidate_pool:
        accept(code)
    else:
        drop(code)  # hallucinated, removed
```

**DB-rescue mode**:
```python
for code in llm_response:
    if code in candidate_pool:
        accept(code)
    elif db.exists(code):  # ← LLM'in tıbbi bilgisini kabul et
        accept(code)
    else:
        drop(code)
```

**Tez argümanı:** db_rescue, RAG'ın recall miss'lerini LLM'in eğitilmiş tıbbi bilgisi ile kurtarır. Test sonuçlarında ICD-10'da F1'i 0.04-0.09 arttırıyor.

---

## 4. Mevcut Test Sonuçları — n=20 Sentetik Dahiliye Senaryosu

### 4.1 Test Düzeneği

**Veri seti:** 20 LLM-üretilmiş, insan-doğrulanmış Türkçe doktor-hasta diyaloğu (`data/eval_synthetic/transcript_T01.txt` — `T20.txt`).

Senaryo dağılımı:
- 10 basit (single-condition): DM, HT, hiperkolesterolemi, hipotiroidi, anemi, astım, gastrit, bronşit, UTI, hepatit B
- 6 multi-comorbidity: DM+HT+lipid, KAH+HT+DM, KOAH+HT, hipotiroidi+lipid, KY+AF, hipertansif kalp+DM
- 4 edge case: D50 vs R42 muhakeme, J44.0 vs J44.9 specificity, V3 prompt stress, past vs current request

**Gold standardlar:** Her transkript için
- `gold_T<NN>_icd10.json` — beklenen ICD kodları
- `gold_T<NN>_intent.json` — SUT mention'ları (REQUEST/EXCLUDE etiketli)
- `gold_T<NN>_anamnez.json` — 26 dahiliye anamnez alanı

### 4.2 Karşılaştırılan Konfigürasyonlar

| Etiket | Model | Mode | Notlar |
|---|---|---|---|
| haiku_strict (API) | Haiku 4.5 | strict | Production default |
| haiku_dbrescue (API) | Haiku 4.5 | db_rescue | Recall-friendly |
| opus_strict (API) | Opus 4.7 | strict | Quality ceiling test |
| opus_dbrescue (API) | Opus 4.7 | db_rescue | Best of both |
| sub-agent Opus 4.7 | Opus 4.7 | strict | Claude Code agents |

### 4.3 Sonuçlar (FULL TABLE)

#### Anamnez (4 koşul aynı — metrik saturated)
| Koşul | exact | token-F1 | BLEU-1 |
|---|---:|---:|---:|
| haiku_strict | 0.232 | 0.280 | 0.286 |
| haiku_dbrescue | 0.233 | 0.282 | 0.289 |
| opus_strict | 0.232 | 0.280 | 0.288 |
| opus_dbrescue | 0.232 | 0.281 | 0.288 |

> **Bulgu:** Token-overlap metriği bu 4 koşulu ayırt edemiyor. Anamnez kalitesinde Haiku=Opus diyemiyoruz, metrik yetersiz.

#### ICD-10 EXACT match (kod birebir)
| Koşul | TP | FP | FN | P | R | F1 |
|---|---:|---:|---:|---:|---:|---:|
| haiku_strict | 22 | 47 | 14 | 0.319 | 0.611 | 0.419 |
| haiku_dbrescue | 25 | 48 | 11 | 0.342 | 0.694 | 0.459 |
| opus_strict | 18 | 40 | 18 | 0.310 | 0.500 | 0.383 |
| opus_dbrescue | 20 | 28 | 16 | 0.417 | 0.556 | **0.476** |
| sub-agent Opus 4.7 | 21 | 38 | 15 | 0.356 | 0.583 | 0.442 |

#### ICD-10 PREFIX match (3-char prefix, e.g. E11.9 ≈ E11.0)
| Koşul | TP | FP | FN | P | R | F1 |
|---|---:|---:|---:|---:|---:|---:|
| haiku_strict | 26 | 42 | 10 | 0.382 | 0.722 | 0.500 |
| haiku_dbrescue | 28 | 45 | 8 | 0.384 | 0.778 | 0.514 |
| opus_strict | 21 | 37 | 15 | 0.362 | 0.583 | 0.447 |
| opus_dbrescue | 22 | 26 | 14 | 0.458 | 0.611 | 0.524 |
| sub-agent Opus 4.7 | 27 | 32 | 9 | 0.458 | 0.750 | **0.568** |

#### SUT Intent (REQUEST detection)
| Koşul | TP | FP | FN | P | R | F1 |
|---|---:|---:|---:|---:|---:|---:|
| haiku_strict | 116 | 18 | 44 | 0.866 | 0.725 | 0.789 |
| haiku_dbrescue | 116 | 19 | 44 | 0.859 | 0.725 | 0.786 |
| opus_strict | 119 | 15 | 41 | 0.888 | 0.744 | 0.810 |
| opus_dbrescue | 117 | 14 | 43 | 0.893 | 0.731 | 0.804 |
| sub-agent Opus 4.7 | 125 | 14 | 35 | 0.899 | 0.781 | **0.836** |

### 4.4 Yorum: Mevcut Performans Profili

**ICD-10 katmanında en iyi F1: ~0.46 exact / ~0.57 prefix**
- Bu değerler tıbbi kodlama literatürü için **mediocre ama düşük değil** (manual coder agreement %60-80, multi-coder consistency benzer aralıkta)
- Asıl boşluk **specificity gap**: F1_prefix - F1_exact ≈ 0.10. Sistem doğru hastalık kategorisini buluyor ama .0/.9 alt-kod seçiminde zorlanıyor

**SUT katmanında en iyi F1: ~0.84**
- Bu değerler intent disambiguation için **iyi**. V3 prompt'u Türkçe morfoloji-aware tasarımı sayesinde özellikle list-inheritance, passive imperative, hypothetical ayrımlarını başarıyla yapıyor

**Hallucination guard'ın net etkisi (ICD'de):**
- strict → db_rescue: F1 +0.04 ila +0.09 (model'a göre değişiyor)
- LLM'in tıbbi bilgisini kullanmak recall'u arttırıyor, precision'a hafif düşüş

**Model boyutunun etkisi minör:**
- Haiku → Opus arasında F1 farkı ortalama +0.03
- Cost-quality dengede Haiku tercih edilmeli (Opus 15-25x daha pahalı)

---

## 5. Gözlemlenen Hata Kategorileri

### 5.1 Kategori A — RAG Retrieval Miss (Recall hata)

**Örnek (T07 — Gastrit + Reflü):**
- Gold: `K29.7` (Gastrit), `K21.9` (Reflü), `R10.4` (Karın ağrısı)
- Sistem: `K25.9, K31.9` (Mide ülseri, Mide-duodenum tanımlanmamış)
- **Sebep:** Vector search "epigastrik ağrı, ekşime, regürjitasyon" → K25 (ülser) yakaladı, K29 (gastrit) yakalayamadı. K21 (reflü) hiç candidate'a girmedi.

**Örnek (T09 — UTI):**
- Gold: `N39.0` (Üriner sistem enfeksiyonu)
- Sistem: `Z88.0, R12, R53` (Penisilin alerjisi, göğüste yanma, halsizlik)
- **Sebep:** N30/N39 kodları candidate listesine girmedi. Vector search "P39.3 yenidoğan UTI", "O23.0 gebelik UTI" gibi alakasız kodlar getirdi.

**Frequency:** 20 form'un ~6'sında (T07, T09, T11 kreatinin, T12 E11.9, T16 kreatinin, T18 R06.0)

### 5.2 Kategori B — Specificity Gap (Subcode ayrımı)

**Örnek (T05 — Anemi):**
- Gold: `D50.9` (Demir eksikliği anemisi, tanımlanmamış)
- Sistem: `D50.0` (Kronik kan kaybına bağlı demir eksikliği anemisi)
- **Klinik açıdan** D50.0 daha spesifik (menorajik kanama belgelenmiş), gold ise lab konfirmasyonu beklendiği için D50.9 demiş
- **Exact match:** F1=0
- **Prefix match (D50):** F1=0.40

**Örnek (T06 — Astım):**
- Gold: `J45.9` (Astım, tanımlanmamış)
- Sistem: `J45.0` (Astım, allerjik)
- Aynı pattern: Sistem daha spesifik subcode seçti

**Tartışma:** Bu hatalar "klinik olarak doğru ama gold ile eşleşmiyor". Tezde **inter-annotator agreement** olarak tartışılabilir.

### 5.3 Kategori C — Symptom-vs-Disease Decision Failure

**Örnek (T01 — DM):**
- Gold: `[E11.9]` (sadece DM)
- Sistem: `[E11.9, E66.9, R53]` (DM, obezite, halsizlik)
- **Sebep:** LLM "BMI 32 belgelenmiş → E66.9 (obezite) ekle" diye akıl yürüttü. Gold ise sadece doktorun açık tanı koyduğu kodu istiyor.
- Bu tartışmalı: BMI 32 → obezite klinik olarak doğru, ama doktor "obezite tanısı koymadı".

### 5.4 Kategori D — Reranker Top-K Filtering (Yeni Bulgu)

Recent test (RRF fusion + cross-encoder reranker):
- Reranker top_k=25 ile candidate havuzunu filtreliyor
- Bazı doğru kodlar bu top-25'e giremiyor (örn T05 D50.x havuzdan düştü)
- **Sonuç:** Recall regresyonu (-0.083 ICD exact, -0.150 SUT)

**Önemli:** RRF + reranker kodu pull'da geri alındı (commit `c863b91`). Ama sub-agent test çıktıları korundu (`data/subagent_outputs_rrf/` arşivi).

---

## 6. Açık Araştırma Soruları

> **Senin görevin bu sorulara araştırmaya dayalı cevap önerileri üretmek. "X tekniği denenir mi?" "Y benzer projeler ne yapmış?" "Z literatürde nasıl çözülmüş?" tarzı.**

### Q1 — Specificity Gap'i Nasıl Kapatabiliriz?

**Sorun:** F1_prefix - F1_exact ≈ 0.10. Sistem "DM var" doğru tespit ediyor ama "E11.9 mi E11.0 mı E11.7 mi" karar veremiyor.

**Olası araştırma yönleri:**
- **Hierarchical classification**: önce ana kategori (E11), sonra alt-kod (E11.9). 2-stage prompt design.
- **ICD-10 hierarchy-aware loss/scoring**: parent-child uzaklığını metrik olarak kullan
- **Subcode-specific prompt examples**: prompt'a "ne zaman .9, ne zaman .0" örnekleri ekle
- **Fine-tune approach**: küçük bir Türkçe medical coding LLM (Llama-3.1-8B, Qwen2.5) ile subcode selection özelinde fine-tune
- **Inter-annotator agreement (IAA) measurement**: gold'u 2-3 doktora yeniden etiketletme — gerçek "correctness" upper-bound nedir?

**Aramalı:** Medical code assignment, fine-grained classification, hierarchical multi-label classification, ICD-10 auto-coding benchmarks (ör: MIMIC-IV-ICD), Klüfer 2023, Edin et al. 2023.

### Q2 — RAG Recall Miss Problem'i

**Sorun:** ~30% form'da gold ICD/SUT kodu candidate'a girmiyor. Vector search alakasız kodlar getiriyor.

**Olası araştırma yönleri:**
- **Multi-vector retrieval (ColBERT-style)**: tek dense embedding yerine çoklu token-level embeddings
- **Hybrid retrieval (dense + sparse + lexical)**: BM25 + dense + RRF fusion (zaten denendi, top_k tuning sorunu)
- **Query rewriting via LLM**: "menorajik kanama, halsizlik" → "demir eksikliği anemisi N92.0" gibi LLM tabanlı query expansion
- **Domain-specific embedding fine-tuning**: BGE-M3'ü Türkçe medical dataset üzerinde DPR-style fine-tune
- **Better synonym dictionary**: mevcut sözlük statik (728 entry) — UMLS Türkçe haritası, ATIS Türkçe medical thesaurus var mı?
- **Cross-lingual transfer**: İngilizce medical embedding modelleri (PubMedBERT, BioClinicalBERT) ile cross-lingual setup

**Aramalı:** Dense retrieval improvements, query expansion via LLM, medical IR benchmarks (BEIR-medical, MS-MARCO), cross-lingual medical IR, UMLS-aware retrieval.

### Q3 — Symptom-vs-Disease Decision'ın Doğru Tasarımı

**Sorun:** Sistem tıbbi reasoning yapıyor (BMI 32 → obezite ekle), gold ise sadece "doktor ne dediyse" istiyor. Bu fundamentally tasarım sorusu: **extraction mı, inference mı?**

**Olası araştırma yönleri:**
- **Pure NER+mapping pipeline**: doktor "diyabet" der → DM mappingi → E11.9 (LLM reasoning yok)
- **Dual-path system**: Stage A pure extraction (yüksek precision), Stage B reasoning (yüksek recall)
- **Confidence-thresholded reasoning**: confidence ≥0.9 ise sadece extraction, <0.9 ise LLM reasoning
- **User-controllable mode**: production'da doktor "minimal coding" / "comprehensive coding" toggle'ı
- **Evaluation framework redesign**: "minimal_correct" + "expanded_correct" ayrı metrik

**Aramalı:** Information extraction vs inference taxonomy, conservative vs liberal coding, clinical NLP evaluation methodology, ASR medical transcript IE benchmarks.

### Q4 — Anamnez Metriği Iyileştirme

**Sorun:** Token-F1, BLEU-1 birbirine eşdeğer Türkçe medical text'i ayırt edemiyor. Haiku=Opus diyor ama gerçekten öyle mi bilmiyoruz.

**Olası araştırma yönleri:**
- **LLM-as-judge**: GPT-4 / Claude-judge ile pairwise comparison
- **Embedding-based semantic similarity**: BERTScore, SBERT cosine
- **Fact-coverage metric**: Önce gold'dan "fact list" çıkar, sistem output'unda kaç fact bulundu say
- **Structural alignment**: anamnez 26 alanı için per-field accuracy + cross-field consistency
- **Doctor preference test**: 2-3 dahiliye uzmanı blind A/B comparison

**Aramalı:** Medical text generation evaluation, faithfulness metrics, MedDialog evaluation benchmarks, BERTScore medical, RadGraph (radiology), CXR-Metric.

### Q5 — Reranker'ı Doğru Kullanma

**Sorun:** RRF + cross-encoder reranker eklendi, ama top_k=25 limiti recall'a zarar verdi. Top_k tuning, GPU kullanımı, alternatif reranker tercihi belirsiz.

**Olası araştırma yönleri:**
- **Top-k sensitivity analysis**: 25, 50, 75, 100 candidate'la deney
- **Adaptive top-k**: query complexity'ye göre dinamik k seçimi
- **Smaller reranker**: BGE-reranker-v2-m3 yerine cross-encoder/ms-marco-MiniLM-L-12-v2 (200MB vs 600MB)
- **Reranker fine-tune**: Türkçe medical query-doc pair'leriyle BGE-reranker'ı fine-tune
- **Late interaction (ColBERT)**: bi-encoder ile ColBERT-style late interaction
- **GPU vs CPU comparison**: aynı reranker GPU'da daha iyi mi sıralıyor?

**Aramalı:** Cross-encoder reranking benchmarks, retrieval-then-rerank pipelines, BEIR-rerank, MS-MARCO passage reranking, medical reranking literature.

### Q6 — Hallucination Guard'ın Optimum Strateji

**Sorun:** strict mode bazen recall miss yaratıyor (LLM doğru kodu öneriyor, candidate'ta yok diye atılıyor). db_rescue mode bunu çözüyor ama precision'a maliyetli.

**Olası araştırma yönleri:**
- **Three-way validation**: candidate ⊃ DB-validated ⊃ LLM-only (3 confidence seviyesi)
- **Code-context validation**: LLM önerdiği kodun "tani" string'i ile transkript arasında semantic similarity threshold
- **Self-consistency**: LLM'i 3-5 kez çalıştır, çoğunluk oyuyla kabul et
- **Verification sub-agent**: ayrı bir LLM çağrısı "bu kod bu rapora uygun mu?" diye doğrula
- **Hybrid mode**: ICD'de db_rescue, SUT'ta strict (saturation farklı)

**Aramalı:** LLM hallucination mitigation, RAG validation, self-consistency decoding, verifier models, code generation hallucination.

### Q7 — Türkçe Tıbbi NER'in Kalitesi

**Sorun:** GLiNER zero-shot, fine-tune değil. ASR hatalarına ve morfolojik varyantlara hassas.

**Olası araştırma yönleri:**
- **Türkçe medical NER fine-tune**: GLiNER → Türkçe medical corpus üstünde few-shot/fine-tune
- **LLM-based NER**: Haiku 4.5'a NER tasksini direkt ver (cost arttırır)
- **Multi-stage NER**: önce coarse (hastalık/tetkik/ilaç), sonra fine (specific terms)
- **Spell-correction preprocessing**: ASR çıktısını GPT-4 ile düzelt, NER'a ondan sonra ver
- **Türkçe BioBERT**: Türkçe biomedical fine-tuned BERT modeli var mı?

**Aramalı:** Turkish biomedical NER, GLiNER fine-tuning, ASR error correction NER, Turkish medical NLP corpora (varsa).

---

## 7. Bizim Test Setimizden Spesifik Hata Vakaları

> Bu vakalar concrete failure mode'ları gösteriyor, araştırmada "ne tip iyileştirme bu vakayı çözer" sorusuna cevap arandığında somut örnek olarak kullanılabilir.

### Vaka 1 — RAG Miss (T07 Gastrit+Reflü)

**Transkript özeti:**
> Doktor: "Sizdeki klinik tablo gastrit ile uyumlu, reflü de var. Mide iltihabı ve mide asidinin yemek borusuna kaçması olarak da bilinir. Empirik PPI başlayalım."

**Gold:** `K29.7` (Gastrit), `K21.9` (Reflü özofajit olmaksızın), `R10.4` (Karın ağrısı)

**Sistem (her 5 koşulda):** `K25.9` (mide ülseri tanımlanmamış), `K31.9` (mide-duodenum tanımlanmamış) — ne K29 ne K21 hiçbir koşulda candidate'a giremedi

**Diagnostic:**
- NER terms: ['gastrit', 'reflü', 'mide ağrısı', 'epigastrik']
- Vector search BGE-M3 → K29 hiçbir term için top-3'e giremedi
- Sinonim sözlüğü "gastrit" → ["gastrit", "mide iltihabı"] expansion var, yine de K29 retrieval'a girmiyor

**Sorgular:**
1. BGE-M3 Türkçe "gastrit" → K29 (Gastritis, unspecified) embedding similarity neden düşük?
2. ChromaDB'deki K29 entry'si nasıl indexed? `tani` field'ı ne?
3. Alternatif retrieval (BM25, ColBERT, query rewriting) bu vakayı kurtarabilir mi?

### Vaka 2 — Specificity Gap (T05 Anemi)

**Transkript özeti:**
> Doktor: "Demir eksikliği anemisi düşünüyorum. Aybaşı şikayetinizden kaynaklı kronik kan kaybı muhtemelen etyoloji. Ferritin ve demir paneli ile doğrulayalım."

**Gold:** `D50.9` (Demir eksikliği anemisi, tanımlanmamış)

**Sistem (Opus strict):** `D50.0` (Kronik kan kaybına bağlı demir eksikliği anemisi)

**Tartışma:** D50.0 klinik olarak DOĞRU (menorajik etyoloji belgelenmiş), gold ise lab onayı beklendiği için D50.9 demiş. Inter-annotator question.

**Sorgular:**
1. Gold standard'a "klinik gerekçeli daha spesifik kod" eklemek mi? (multi-valid gold)
2. Subcode selection için ek prompt example'ı: "lab konfirmasyonu yoksa .9 tercih et" daha güçlü uygulanabilir mi?
3. Inter-annotator agreement için 2-3 dahiliye uzmanı yeniden etiketletmek tezde standart pratik mi?

### Vaka 3 — Doctor Reasoning Override (T04 Hipotiroidi)

**Transkript özeti:**
> Doktor: "Klinik tablo hipotiroidi düşündürüyor — halsizlik, kilo artışı, üşüme, kabızlık var. Ama tahlil sonuçlarına göre tedavi planlanacak."

**Gold:** `E03.9` (Hipotiroidizm, tanımlanmamış)

**Sub-agent Opus 4.7 çıktısı:** `K59.0` (Kabızlık), `R63.5` (Kilo alma), `L67.9` (Saç dökülmesi), `R68` (genel semptom)

**Agent reasoning:** *"Doktor 'tahlil sonuçlarına göre' dediği için tanı koymadı. Sadece semptom kodları seçtim per 'doktor demediyse tahmin etme' kuralı."*

**Tartışma:** Agent'ın yorumu prompt kuralını sıkı uyguluyor. Ama "klinik tablo X düşündürüyor" cümlesi tanı sayılır mı?

**Sorgular:**
1. Prompt'a "ön tanı (preliminary diagnosis)" gibi ara seviye nasıl eklenir?
2. Confidence-based output: kesin tani vs ön tani vs semptom kodu tercihleri eşiklere bağlı olabilir mi?
3. Türkçe doktor jargonunda "düşündürüyor" / "muhtemelen" / "olası" gibi hedge ifadeler kodlamayı nasıl etkilemeli?

---

## 8. Mevcut Kod Konumu (Araştırmacının inceleyeceği dosyalar)

```
apps/backend/src/services/
├── icd10_suggestion_service.py    # ICD-10 pipeline (~669 satır)
│   ├── ICD10_REPORT_SELECTION_PROMPT  (line 77)
│   ├── ICD10_EXPLICIT_EXTRACTION_PROMPT (line 52)
│   ├── ICD10SuggestionService class
│   │   ├── __init__()              (validation_mode flag)
│   │   ├── suggest()               (transcript-based)
│   │   ├── suggest_from_report()   (anamnez-based, prod path)
│   │   ├── _extract_ner_terms()    (GLiNER + keyword fallback)
│   │   ├── _find_vector_candidates() (BGE-M3 + sinonim expansion)
│   │   ├── _text_search_fallback() (SQLite LIKE)
│   │   ├── _llm_extract_diagnoses_and_symptoms() (LLM-explicit)
│   │   ├── _augment_with_unspecified() (hierarchical .9 expansion)
│   │   ├── _llm_select_from_report() (final LLM call)
│   │   └── _parse_llm_selection()  (hallucination guard)
│
├── sut_suggestion_service.py      # SUT pipeline (~985 satır)
│   ├── SUT_SELECTION_PROMPT_V2      (line 174, V2 prompt)
│   ├── SUT_SELECTION_PROMPT_V3      (line 260, V3 — production default)
│   ├── SUT_REPORT_SELECTION_PROMPT  (line 59, anamnez-based variant)
│   ├── SUTSuggestionService class
│   │   └── (parallel structure to ICD10SuggestionService)
│
├── icd10_vector_service.py        # BGE-M3 + ChromaDB wrapper (113 satır)
├── sut_vector_service.py          # Same for SUT (120 satır)
├── ner_service.py                 # GLiNER NER (137 satır)
├── nlp_normalizer.py              # Sinonim sözlüğü + token isolation (265 satır)
└── embedding_config.py            # BGE-M3/MiniLM/E5 profile selection (82 satır)

apps/backend/src/scripts/
├── eval_icd10_codes.py            # ICD eval framework
├── eval_sut_intent.py             # SUT eval framework (orijinal, gold standardlarla)
├── eval_anamnez_fields.py         # Anamnez eval (token-F1, BLEU, exact)
├── prep_subagent_inputs.py        # Sub-agent test düzeneği (RAG candidate generation)
└── build_icd10_vectors.py         # ChromaDB indexing (offline)
└── build_sut_vectors.py           # SUT ChromaDB indexing

data/
├── icd10.db                       # SQLite, 11,332 ICD-10 kodu
├── sut_tetkik.db                  # SQLite, 603 SUT kodu
├── icd10_chroma_bge/              # ChromaDB persistent (BGE-M3 indexed)
├── sut_tetkik_chroma_bge/         # ChromaDB SUT
├── medical_synonyms.json          # ~728 entry curated sinonim dict
├── eval_synthetic/                # Test veri seti (T01-T20)
│   ├── transcript_T<NN>.txt
│   ├── gold_T<NN>_icd10.json
│   ├── gold_T<NN>_intent.json
│   └── gold_T<NN>_anamnez.json
└── subagent_outputs_baseline_v1/  # Sub-agent Opus 4.7 baseline test çıktıları
└── subagent_outputs_rrf/          # RRF+Reranker test çıktıları (regresyon kanıtı)

docs/
├── ablation-evaluation-report.md  # Önceki tezsel ablation raporu
└── icd-sut-pipeline-research-brief.md  # ← Bu dosya
```

---

## 9. Tezsel Bağlam (Araştırmacı için kritik nokta)

Bu pipeline bir **yüksek lisans tezi** kapsamında değerlendiriliyor. Tezdeki ana iddialar:

1. **Hibrit retrieval-LLM mimarisi** Türkçe medical coding için viable bir yaklaşımdır
2. **Hallucination guard ablation** (strict vs db_rescue) hallucination ↔ recall trade-off'unu gösterir
3. **Cost-quality optimum: Haiku 4.5** (Opus 4.7 marjinal kazanım, 15-25x maliyet)
4. **V3 prompt** Türkçe morfoloji-aware intent disambiguation (saturated F1 0.79-0.84)
5. **Sub-agent infrastructure** API-equivalent within ±5% (cost-controlled alternative)

Senin araştırma raporun tezde **"İyileştirme önerileri ve future work"** bölümünü destekleyecek. Yani:
- Hangi tekniklerin denenebileceği
- Literatürde hangi benzer projeler hangi yaklaşımları kullandı
- Mevcut state-of-the-art ne (özellikle Türkçe medical NLP)
- Bu pipeline'ın hangi bileşenleri en yüksek beklenen iyileştirme potansiyeline sahip

Önemli: Tezde sadece "denenebilir" yeterli, **uygulanması zorunlu değil**. Yani senin araştırman bize sonra hangi yatırımlara öncelik vereceğimizi söyleyecek.

---

## 10. Mantıklı Bir Araştırma Çıktısı Şeması

Eğer bana 10-20 sayfalık bir araştırma raporu verecek olsan, şu yapı çok kıymetli olur:

### Bölüm 1 — Mevcut Durumun Akademik Konumlandırılması
Türkçe medical NLP için mevcut sistemler nasıl performans gösteriyor? F1 0.46-0.84 aralığı bu domain için tipik mi, düşük mü, yüksek mi?

### Bölüm 2 — Her Bileşen İçin Literatür Taraması
- NER (Türkçe medical, multi-lingual zero-shot, GLiNER alternatifleri)
- Retrieval (dense, hybrid, fine-tuned, multi-vector)
- Reranking (cross-encoder, late-interaction, neural rerankers)
- LLM medical reasoning (chain-of-thought, self-consistency, verification)
- Hallucination mitigation (RAG-specific, code-generation-specific)

### Bölüm 3 — Spesifik Sorularımıza Hedeflenmiş Öneriler
Bölüm 6'daki Q1-Q7 her birine 1-2 paragraflık öneri + reference paper.

### Bölüm 4 — Önceliklendirilmiş Roadmap
"Bu projede en yüksek ROI'li 3 iyileştirme şudur" listesi:
1. ___ (rationale + estimated effort + estimated F1 lift)
2. ___
3. ___

### Bölüm 5 — Risk/Trade-off Analizi
- Hangi iyileştirmeler complexity ekler?
- Hangileri annotation/data investment gerektirir?
- Hangileri sadece prompt engineering ile yapılabilir?

### Bölüm 6 — Kıyaslanabilir Sistemler ve Benchmark
- MIMIC-IV-ICD, MedDialog, ASR-medical benchmarks
- Türkçe medical NLP datasets (varsa)
- Industrial systems (Nuance DAX, Microsoft Healthcare Bot, vb.) yaklaşımları

---

## 11. Bağlantılar & Kaynaklar (Araştırmaya başlayabilmen için)

**Mutlaka okunmalı:**
- BGE-M3 paper (Chen et al. 2024) — kullandığımız embedding modeli
- GLiNER paper (Zaratiana et al. 2024) — kullandığımız NER
- RRF original (Cormack et al. 2009) — denedik, başarısız oldu, neden?
- "Reciprocal Rank Fusion outperforms Condorcet" paper

**Türkçe medical NLP kaynakları:**
- TR-BERT (Türkçe BERT modelleri)
- Turkish biomedical text mining literature (Boğaziçi, ITÜ NLP grupları)
- (varsa) UMLS Türkçe haritası

**Industry references:**
- Nuance Dragon Medical (de facto industry standard)
- Microsoft Healthcare NLP
- Google's Med-PaLM
- Epic'in HIE coding integrations

**ICD coding benchmarks:**
- MIMIC-IV-ICD (English)
- CodiEsp (Spanish — multi-lingual relevance)
- Edin et al. 2023 "Automated medical coding on MIMIC-III and MIMIC-IV"
- Klüfer 2023 "Hierarchical multi-label classification of ICD-10"

**SUT-equivalent (lab order extraction):**
- i2b2/n2c2 challenges (medication, problem, treatment extraction)
- Medication intent extraction literature

---

## 12. Hızlı Erişim İçin: Test Sonuçları Dosyaları

Eğer araştırmanı yaparken "bu specific case neyle başarısız oldu" diye merak edersen:

```
data/subagent_outputs_baseline_v1/
├── T01_icd_opus_output.json   # Selected codes + reasoning
├── T01_sut_opus_output.json   # SUT mentions + intent
├── ...
└── T20_*.json

data/subagent_outputs_rrf/
└── (aynı yapı, RRF+Reranker konfigürasyonu — REGRESYON gösterdi)

data/eval_synthetic/
├── gold_T01_icd10.json   # Beklenen ICD kodları
├── gold_T01_intent.json  # Beklenen SUT REQUEST mention'ları
└── ...
```

Her sub-agent output'u şunu içeriyor:
- Seçilen kodlar
- Confidence scores
- Reasoning (neden seçildi)
- Excluded candidates (neden atlandı)

Bu transparency tezde error analysis için altın değerinde, senin araştırmana da somut "şu tip hatayı şu teknik çözer" örnekleri çıkarmana yardım eder.

---

*Rapor sonu — KlinikAsistan ekibi, 2026-05-08*
