# LLM Pipeline - Kapsamli Teknik Dokumantasyon

> **Proje**: KlinikAsistan - Turkce Poliklinik Otomatik Anamnez Raporu Olusturma
> **Tarih**: Mart 2026
> **Branch**: `feature/llm-performance-optimization`

---

## 1. Genel Bakis

KlinikAsistan projesinin LLM pipeline'i, doktor-hasta gorusmesinin transkriptinden otomatik olarak 11 bolumlu standart anamnez raporu olusturur. Pipeline tamamen yerel (on-premise) calisir; KVKK geregi hasta verileri disariya gonderilmez.

### Pipeline Adimlari (Ozet)

```
Transkript (Doktor-Hasta Diyalogu)
        |
        v
[1] NER Extraction (GLiNER, devre disi)   -- detay: Bolum 9
[2] RAG Query (ChromaDB + bge-m3)          -- detay: Bolum 9
        |
        v
[3] LLM Generation (Qwen3:14b via Ollama)  ← ANA ODAK
        |
        v
[4] Validation (Grounding + NLI)           -- detay: Bolum 9
        |
        v
11 Bolumlu Anamnez Raporu (JSON)
```

---

## 2. LLM Servisi

**Dosya**: `apps/backend/src/services/llm_service.py`

### 2.1 Mimari: Factory Pattern

LLM servisi, abstract `LLMBackend` sinifini implement eden iki backend ile factory pattern kullaniyor. `LLMService` sinifi public interface olarak calisiyor ve konfigurasyona gore uygun backend'i seciyor.

```
LLMService (public interface)
    |
    +-- OllamaBackend   → POST /api/generate         (Ollama REST API)
    |
    +-- LlamaCppBackend  → POST /v1/chat/completions  (OpenAI-uyumlu API)
```

Her iki backend de asagidaki ortak arayuzu implement eder:

| Method | Aciklama |
|--------|----------|
| `initialize()` | HTTP client baslatma |
| `shutdown()` | HTTP client kapatma |
| `check_health()` | Servis erisebilirlik kontrolu |
| `is_model_loaded()` | Modelin bellege yuklu olup olmadigini kontrol |
| `generate()` | Non-streaming metin uretimi |
| `generate_stream()` | Token-token streaming metin uretimi (AsyncIterator) |

### 2.2 OllamaBackend (Varsayilan)

Ollama REST API'ye (`http://localhost:11434`) async HTTP istekleri gonderir.

**Non-streaming cagrisi:**
```python
payload = {
    "model": "qwen3:14b",
    "prompt": prompt,
    "system": system,
    "stream": False,
    "think": False,            # Extended thinking devre disi
    "keep_alive": -1,          # Model bellekte kalsin
    "options": {
        "temperature": 0.3,
        "top_p": 0.9,
        "num_predict": 4096,
    },
}
# Opsiyonel: format_schema verilirse → Ollama structured JSON output
if format_schema:
    payload["format"] = format_schema
```

**Streaming cagrisi:**
- Ayni payload, `"stream": True` ile
- `resp.aiter_lines()` uzerinden satir satir JSON parse
- Her satirdaki `"response"` alani bir token
- `"done": true` gelince stream sonlanir

**Saglik kontrolleri:**
- `check_health()`: `GET /api/tags` → 200 ise saglikli
- `is_model_loaded()`: `/api/tags` response'unda model adi aranir

### 2.3 LlamaCppBackend (Alternatif)

llama.cpp server'in OpenAI-uyumlu API'sini (`http://localhost:8080`) kullanir.

**Temel farklar:**
- Prompt yerine `messages` formati kullanir: `[{role: "system", content: ...}, {role: "user", content: ...}]`
- Streaming'de `data: ` prefix'li SSE satirlari, `data: [DONE]` ile sonlanir
- Token bilgisi `choices[0].delta.content` icinde gelir
- Saglik kontrolu: `GET /health`

### 2.4 LLM Parametreleri

| Parametre | Deger | Neden |
|-----------|-------|-------|
| `model_name` | `qwen3:14b` | Turkce tibbi metin icin yeterli kalite (~12GB VRAM) |
| `fallback_model` | `qwen3:8b` | Ana model basarisiz olursa yedek (~6GB VRAM) |
| `temperature` | 0.3 | Dusuk: tibbi metin icin deterministik, tutarli cikti |
| `top_p` | 0.9 | Odakli ama cesitli token secimi |
| `max_tokens` | 4096 | 11 bolumun tamami icin yeterli |
| `timeout_seconds` | 120 | Uzun generation'lar icin yeterli, sonsuz beklemeyi onler |
| `think` | `false` | Qwen3 extended thinking devre disi - performans kritik |
| `keep_alive` | -1 | Model bellekte kalir, cold start overhead yok |
| `backend_type` | `"ollama"` | Varsayilan; `"llamacpp"` olarak degistirilebilir |

---

## 3. Prompt Muhendisligi

### 3.1 Sistem Prompt'lari

**Dosya**: `apps/backend/src/prompts/system_prompt.py`

Iki ayri sistem prompt'u vardir:

#### `SYSTEM_PROMPT` (Bolum-bazli generation, fallback yolunda kullanilir)

9 temel kural tanimlar:

1. **SADECE** transkriptte gecen bilgileri kullan - bilgi ekleme
2. Bilgi yoksa "Belirtilmedi" yaz - tahminde bulunma
3. Tibbi terminolojiyi koru
4. Ucuncu sahis klinik dil kullan: "Bas agrim var" → "Hasta bas agrisi tarifliyor"
5. Tum cikti Turkce
6. Spekulasyon yapma, cikarsam yapma, yorum ekleme
7. Belirsiz bilgiler icin `[belirsiz]` isareti koy
8. Kisa ve oz yaz, gereksiz tekrar yok
9. Diyalogu analiz ederek bilgileri cikar

#### `UNIFIED_SYSTEM_PROMPT` (Tek seferde 11 bolum, birincil yolda kullanilir)

Ayni 9 kural + 2 ek:

- **Kural 10**: Ciktiyi **SADECE** JSON formatinda ver, ek aciklama ekleme
- **Kural 11**: `/nothink` - Qwen3 thinking modunu devre disi birak

`/nothink` komutu kritik bir optimizasyondur. Qwen3 modeli varsayilan olarak her cevap oncesi gizli `<think>...</think>` blogu uretir. Bu blok yuzlerce token icerip generation suresini ciddi olcude artirabilir. `/nothink` ile bu tamamen engellenir.

### 3.2 Anamnez Bolumleri ve Ozel Talimatlari

**Dosya**: `apps/backend/src/prompts/section_prompts.py`

Rapor 11 standart anamnez bolumunden olusur. Her bolumun kendine ozel LLM talimati vardir:

| # | Key | Baslik (TR) | LLM'e Verilen Talimat Ozeti |
|---|-----|-------------|----------------------------|
| 1 | `chief_complaint` | Basvuru Sikayeti ve Simdiki Hastalik Hikayesi | Ana sikayet, baslangic tarihi, sure, siddet, lokalizasyon, artiran/azaltan faktorler, kronolojik siralama |
| 2 | `past_medical` | Gecmis Tibbi Ozgecmis | Onceki hastaliklar, ameliyatlar, hastane yatislari, kronik hastaliklar |
| 3 | `medications` | Kullanilan Ilaclar | Ilac adi, dozaj, kullanim sikligi - liste halinde |
| 4 | `allergies` | Alerjiler | Ilac, gida, diger alerjiler |
| 5 | `family_history` | Aile Oykusu | Anne, baba, kardesler, yakin akraba hastaliklari |
| 6 | `social_history` | Sosyal Oyku | Meslek, sigara (miktar, sure), alkol, egzersiz, yasam kosullari |
| 7 | `review_systems` | Sistemlerin Gozden Gecirilmesi | Kardiyovaskuler, solunum, GI, norolojik yakinmalar |
| 8 | `physical_exam` | Fizik Muayene | Doktorun muayenede soyledigi bulgular |
| 9 | `assessment` | Degerlendirme | On tani, ayirici tani, kesin tani |
| 10 | `plan` | Tedavi Plani | Tetkikler, ilaclar, islemler, kontrol randevusu, sevk |
| 11 | `notes` | Ek Notlar | Diger bolumlere uymayan onemli bilgiler |

Her bolum talimati ayrica su genel kurali icerir: "Bilgi yoksa 'Belirtilmedi' yaz."

### 3.3 Prompt Yapilari

LLM'e gonderilen iki farkli prompt formati vardir:

#### a) Unified Prompt (`build_unified_prompt`) - Birincil Yol

Tek bir prompt ile 11 bolumun tamami JSON olarak uretilir:

```
TRANSKRIPT:
  Doktor: Hosgeldiniz, nasilsiniz?
  Hasta: Son bir haftadir basim agriyor...
  ...

TESPIT EDILEN TIBBI BILGILER:
  <NER entity listesi veya "Tespit edilen tibbi bilgi yok.">

REFERANS BILGI:
  <RAG sonuclari veya "Ek referans bilgisi yok.">

GOREV: Asagidaki 11 bolumun her biri icin transkripti analiz et ve
JSON nesnesi olarak cikti ver.

BOLUMLER VE TALIMATLARI:
  - "chief_complaint" (Basvuru Sikayeti): <ozel talimat>
  - "past_medical" (Gecmis Tibbi Ozgecmis): <ozel talimat>
  - "medications" (Kullanilan Ilaclar): <ozel talimat>
  ... (11 bolum)

CIKTI FORMATI: Tek bir JSON nesnesi. Her anahtar bir bolum.
Bilgi olmayan bolumler icin "Belirtilmedi" yaz.
```

**Beklenen LLM ciktisi:**
```json
{
  "chief_complaint": "Hasta bir haftadir devam eden bas agrisindan ...",
  "past_medical": "Belirtilmedi",
  "medications": "Hicbir ilac kullanmiyor.",
  ...
}
```

#### b) Section Prompt (`build_section_prompt`) - Fallback Yolu

Her bolum icin ayri prompt gonderilir:

```
TRANSKRIPT:
  <tum transkript>

TESPIT EDILEN TIBBI BILGILER:
  <o bolumle ilgili entity'ler>

REFERANS BILGI:
  <RAG sonuclari>

GOREV: <bolume ozel talimat>

BOLUM: <bolum basligi>
Sadece bu bolumun icerigini yaz. Bolum basligi ekleme.
```

### 3.4 JSON Schema (Structured Output)

Ollama'nin structured output ozelligi icin JSON schema tanimlanmistir:

```json
{
  "type": "object",
  "properties": {
    "chief_complaint": {"type": "string"},
    "past_medical": {"type": "string"},
    "medications": {"type": "string"},
    "allergies": {"type": "string"},
    "family_history": {"type": "string"},
    "social_history": {"type": "string"},
    "review_systems": {"type": "string"},
    "physical_exam": {"type": "string"},
    "assessment": {"type": "string"},
    "plan": {"type": "string"},
    "notes": {"type": "string"}
  },
  "required": [tum 11 alan]
}
```

### 3.5 Few-Shot Ornekler

**Dosya**: `apps/backend/src/prompts/few_shot_examples.py`

LLM'e beklenen cikti kalitesini ve klinik dil standardini gostermek icin ornek bir transkript-rapor cifti tanimlanmistir:

- **Ornek senaryo**: Hipertansiyon tanisi alan hasta (bas agrisi, yuksek tansiyon, sigara oykusu)
- **Ornek cikti**: 12 bolumun tamami, ucuncu sahis klinik dille yazilmis
- `get_few_shot_prompt()` fonksiyonu ile sistem prompt'una eklenebilir

---

## 4. Rapor Olusturma Pipeline'i (ReportGenerator)

**Dosya**: `apps/backend/src/services/report_generator.py`

`ReportGenerator` sinifi, LLM generation'in tum orkestrasyon mantigi burada toplanir. Diger servisleri (NER, RAG, LLM, NLI) koordine eder.

### 4.1 Birincil Yol: Unified Generation (`generate_report`)

```
[1] Transkript Birlestirme (_merge_segments)
    - Tum segmentler "Konusmaci: metin" formatinda tek metin haline getirilir
    |
[2] NER Extraction → ATLANIR (performans icin devre disi)
    - entities = [] doner
    |
[3] RAG Sorgusu → tek sorgu, 10 sonuc
    |
[4] Unified LLM Cagrisi
    - build_unified_prompt() ile tek prompt olusturulur
    - UNIFIED_SYSTEM_PROMPT + think=False ile LLM cagrilir
    - Donen JSON parse edilir (_parse_unified_response)
    - Markdown code fence varsa otomatik cikarilir
    |
[5] Basarisiz olursa → Fallback yoluna duser (Bolum 4.2)
    |
[6] Validation (grounding + NLI)
    |
[7] Sonuc: 11 bolumlu rapor JSON'u
```

**JSON Parse Mantigi (`_parse_unified_response`):**
- LLM ciktisi bazen ` ```json ... ``` ` ile sarilabilir → regex ile cikarilir
- `json.loads()` ile parse edilir
- Eski `history_present` alani varsa `chief_complaint` ile birlestirilir (backward compat)

### 4.2 Fallback Yol: Bolum-Bazli Generation

Unified yol basarisiz olursa (JSON parse hatasi vb.) otomatik olarak devreye girer:

```
Her bolum icin (11 kez):
    1. Bolum-ozel RAG sorgusu
    2. build_section_prompt() ile prompt olustur
    3. SYSTEM_PROMPT + think=False ile LLM cagir
    4. Serbest metin cevabi al
    5. Guven puani hesapla
    6. Sonraki bolume gec
```

### 4.3 Unified vs Fallback Karsilastirma

| | Unified | Fallback |
|--|---------|----------|
| **LLM cagrisi** | 1 | 11 |
| **RAG sorgusu** | 1 | 11 |
| **Tahmini sure** | ~30-60 sn | ~9 dk |
| **Cikti formati** | JSON (parse gerekli) | Serbest metin |
| **Hata toleransi** | Dusuk (JSON hatasi → fallback) | Yuksek (bagimsiz bolumler) |
| **Kalite** | Iyi | Biraz daha iyi (odakli prompt) |
| **Kullanim** | Birincil yol | Otomatik fallback |

### 4.4 SSE Streaming Generation (`generate_report_stream`)

Kullaniciya canli ilerleme gostermek icin SSE (Server-Sent Events) ile streaming generation yapilir:

**Event akisi (unified yol):**
```
progress     → { stage: "ner",        message: "...", progress: 0.1  }
progress     → { stage: "ner_done",   message: "...", progress: 0.2  }
progress     → { stage: "generating", message: "...", progress: 0.3  }
progress     → { stage: "generating", message: "...(45 token)",  progress: 0.3-0.8 }  ← her 20 token'da guncellenir
progress     → { stage: "parsing",    message: "...", progress: 0.8  }
section_done → { section: "chief_complaint", content: "...", confidence: "high" }
section_done → { section: "past_medical",    content: "...", confidence: "low"  }
... (11 bolum)
progress     → { stage: "validating", message: "...", progress: 0.9  }
done         → { sections: [...], approved_sections: 0, total_sections: 11 }
```

**Streaming'de fallback devreye girerse:**
- Her bolum icin ek event'ler yayinlanir:
  - `section_start` → bolum basliyor
  - `token` → her bir token (canli yazi efekti icin)
  - `section_done` → bolum tamamlandi

**Streaming implementasyon detayi:**
- `llm.generate_stream()` ile token-token alinir
- Token'lar `accumulated` string'ine eklenir
- Her 20 token'da `progress` event'i emit edilir
- Tum token'lar alindiktan sonra JSON parse yapilir

### 4.5 Guven Puanlama

Her bolum icin `_score_confidence` fonksiyonu guven seviyesi hesaplar:

| Durum | Guven | Aciklama |
|-------|-------|----------|
| NER entity var ve icerikte geciyor | `high` | Transkriptten dogrulanmis bilgi |
| NER entity var ama icerikte gecmiyor | `medium` | Bilgi var ama eslesmedi |
| Entity yok ama icerik dolu | `medium` | Icerik var, dogrulama yapilamamis |
| Bos veya "Belirtilmedi" | `low` | Transkriptte bilgi bulunamadi |

---

## 5. LLM Cikti Isleme

### 5.1 Unified Response Parse

LLM'den donen ham metin birden fazla formatta gelebilir:

1. **Saf JSON**: `{"chief_complaint": "...", ...}` → dogrudan parse
2. **Markdown fence**: ` ```json\n{...}\n``` ` → regex ile JSON cikarilir
3. **Parse hatasi** → fallback yoluna dusulur

```python
def _parse_unified_response(raw: str) -> dict[str, str]:
    text = raw.strip()
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    return json.loads(text)
```

### 5.2 Bolum Olusturma (`_build_sections_from_json`)

Parse edilen JSON'dan standart sections listesi olusturulur:

- Eski `history_present` alani varsa `chief_complaint` ile birlestirilir
- Her bolum icin `key`, `title`, `content`, `status` ("draft"), `confidence` alanlari eklenir
- Eksik bolumler "Belirtilmedi" olarak doldurulur

---

## 6. LLM Dogrulama (Validation)

**Dosya**: `apps/backend/src/services/report_generator.py` (`_validate` metodu)

LLM ciktisi iki asamali dogrulamadan gecer:

### 6.1 Grounding Check

Basit ama etkili bir halusinasyon kontrolu:

```python
# Uzun (>4 karakter), buyuk harfle baslayan kelimeler kontrol edilir
# Bu kelimeler genellikle tibbi terimler veya ozel isimlerdir
medical_words = [w for w in words if len(w) > 4 and w[0].isupper()
                 and w.lower() not in transcript_lower]

if len(medical_words) > 3:
    section["confidence"] = "low"
    section["warning"] = "Transkriptte bulunmayan tibbi terimler tespit edildi"
```

Mantik: LLM transkriptte gecmeyen tibbi terimler uretiyorsa, muhtemelen halusinasyon yapiyordur.

### 6.2 NLI Dogrulama

Daha sofistike bir dogrulama olarak NLI (Natural Language Inference) modeli kullanilir. Detayi Bolum 9'da.

Ozetle: LLM urettigi her cumle, transkriptle `entailment/neutral/contradiction` acisindan degerlendirilir. Ortalama skor < 0.5 ise guven dusurulur.

---

## 7. API Endpoint'leri ve SSE

**Dosya**: `apps/backend/src/routes/reports.py`

### 7.1 LLM ile Ilgili Endpoint'ler

| Method | Endpoint | LLM Kullanimi |
|--------|----------|---------------|
| `POST /api/v1/reports` | `method: "ai_generated"` ile AI pipeline calistirilir |
| `GET /api/v1/reports/stream/{session_id}` | SSE ile canli streaming generation |

### 7.2 AI Rapor Olusturma Akisi (`POST /api/v1/reports`)

1. `session_id` ile transkript segmentleri veritabanindan alinir
2. Segment yoksa → `400 Bad Request`
3. `report_generator` hazir degilse → `503 Service Unavailable`
4. `report_generator.generate_report()` cagrilir (Bolum 4.1)
5. Sonuc `ReportService.generate_with_content()` ile kaydedilir
6. Audit log yazilir

### 7.3 SSE Streaming Endpoint (`GET /api/v1/reports/stream/{session_id}`)

1. Transkript segmentleri alinir
2. `EventSourceResponse` ile async generator donulur
3. `report_generator.generate_report_stream()` event'leri SSE formatinda yayinlanir
4. Her event: `{"event": "<tip>", "data": "<json>"}`
5. Hata olursa `error` event'i yayinlanir

### 7.4 Frontend SSE Client

**Dosya**: `apps/frontend/src/renderer/src/services/sseClient.ts`

- Native `EventSource` yerine `fetch` + `ReadableStream` kullanir (Authorization header destegi icin)
- `AbortController` ile iptal mekanizmasi
- `event:` ve `data:` satirlari manuel parse edilir

---

## 8. Performans Optimizasyonu

### 8.1 Baslangictaki Problem

Ilk implementasyonda rapor olusturma **~9 dakika** (540 saniye) suruyordu.

**Kokenler:**
- **12 sirayla LLM cagrisi**: Her bolum icin ayri Ollama istegi, her biri ~43 saniye
- **Transkript tekrari**: ~500-1000 token'lik transkript 12 kez isleniyor, prefix cache yok
- **Qwen3 thinking mode**: Gizli `<think>...</think>` bloklari yuzlerce ek token uretiyor
- **NER overhead**: CPU'da GLiNER modeli ~10-15 saniye
- **Non-streaming**: Kullaniciya hicbir geri bildirim yok, 9 dk bekleniyor

**Sure kirilimi (9 dk = 540 sn):**
```
NER:            ~10-15 sn
RAG (12 sorgu): ~2-3 sn
LLM (12 cagri): ~520 sn  ← %96 DARBOGAZIN TAMAMI
Validation:     <1 sn
```

### 8.2 Uygulanan Optimizasyonlar

| # | Optimizasyon | Onceki | Sonraki | Etki |
|---|-------------|--------|---------|------|
| 1 | **Unified generation** | 12 sirayla LLM cagrisi | Tek LLM cagrisi | ~12x hizlanma (prompt prefill 1 kez) |
| 2 | **Think mode kapatma** | `think: true` (varsayilan) | `think: false` + `/nothink` | Decode token sayisi ~%50-70 azalma |
| 3 | **NER devre disi birakma** | GLiNER CPU ~15 sn | Tamamen atlanir | ~15 sn kazanc |
| 4 | **Tek RAG sorgusu** | 12 ayri sorgu | 1 sorgu, 10 sonuc | ~2 sn kazanc |
| 5 | **Max tokens ayarlama** | 2048/bolum (toplam 24K) | 4096 toplam | Daha hizli EOS algilama |
| 6 | **keep_alive: -1** | Model yukle/bosalt dongusu | Bellekte kalici | Cold start yok |
| 7 | **SSE streaming** | Tum sonuc bekle | Token-token canli gosterim | Algilanan bekleme suresi cok dusuk |
| 8 | **Timeout 300→120 sn** | 5 dk bekleme | 2 dk bekleme | Hata durumlarinda hizli geri donus |

### 8.3 Optimizasyon Sonuclari

```
ONCE:  ~9 dakika (540 saniye) - kullanici 9 dk boyunca bos ekrana bakiyor
SONRA: ~30-60 saniye (unified) - kullanici token akisini canli goruyor
HEDEF: 30 saniye veya alti
```

En buyuk kazanc **unified generation** (12→1 LLM cagrisi) ve **think mode kapatma** ile saglandi.

### 8.4 Arastirilan ama Henuz Uygulanmayan Yaklasimlar

Detayli arastirma: `docs/llm-performance-research.md`

| Yaklasim | Aciklama | Durum |
|----------|----------|-------|
| **Daha kucuk model** | Qwen3:8b, 4b; Gemma3:4b; Phi-4 | Arastirildi, kalite trade-off var |
| **vLLM** | Continuous batching, PagedAttention | Windows destegi sinirli |
| **llama.cpp server** | Prefix caching, daha hizli inference | Backend olarak implement edildi (LlamaCppBackend) |
| **Ollama ayar tuning** | num_ctx, num_batch, OLLAMA_NUM_PARALLEL | Arastirildi |
| **Speculative decoding** | Kucuk draft + buyuk model | Ollama'da sinirli destek |
| **Prefix caching** | Ayni prompt prefix'ini cache'le | llama.cpp'de var, Ollama'da sinirli |
| **Paralel LLM cagrisi** | Birden fazla bolum ayni anda | GPU bellek siniri nedeniyle riskli |

---

## 9. Yardimci Yapilar (Kisa Ozet)

LLM generation'a girdi saglayan veya ciktisini dogrulayan yardimci yapilar:

### 9.1 RAG (ChromaDB)

**Dosya**: `apps/backend/src/services/rag_service.py`

- **Ne yapar**: Transkriptten semantik benzerlik ile ilgili tibbi bilgi getirir
- **Veritabani**: ChromaDB (kalici), `BAAI/bge-m3` embedding modeli
- **Icerik**: 49 belge - ICD-10 kodlari (25), ilaclar (15), klinik kilavuzlar (7), sablonlar (2)
- **LLM'e etkisi**: Prompt'a "REFERANS BILGI" olarak eklenir, LLM'in tibbi dogrulugunu arttirir
- **Seed script**: `python -m apps.backend.src.rag.seed_data [--force]`

### 9.2 NER (GLiNER) - Devre Disi

**Dosya**: `apps/backend/src/services/ner_service.py`

- **Ne yapar**: Transkriptten tibbi entity'leri cikarir (semptom, ilac, hastalik vb.)
- **Model**: `urchade/gliner_multi-v2.1`, CPU, zero-shot, 13 Turkce tibbi etiket
- **LLM'e etkisi**: Entity'ler prompt'a "TESPIT EDILEN TIBBI BILGILER" olarak eklenirdi
- **Neden devre disi**: ~15 sn CPU suresi, performans icin kapatildi

### 9.3 NLI Dogrulama

**Dosya**: `apps/backend/src/services/nli_service.py`

- **Ne yapar**: LLM ciktisinin transkriptle tutarliligi kontrol eder (halusinasyon tespiti)
- **Model**: `mDeBERTa-v3-base-xnli-multilingual-nli-2mil7`, CPU, ~900MB
- **Yontem**: Premise (transkript) + Hypothesis (uretilen cumle) → entailment skoru
- **LLM'e etkisi**: Dusuk entailment skoru → bolum guveni "low"'a dusurulur

---

## 10. Konfigurasyon

**Dosya**: `config/settings.py`

LLM ile ilgili tum ayarlar Pydantic BaseModel ile tanimlidir:

```python
class LLMSettings(BaseModel):
    backend_type: str = "ollama"           # "ollama" | "llamacpp"
    ollama_url: str = "http://localhost:11434"
    llamacpp_url: str = "http://localhost:8080"
    model_name: str = "qwen3:14b"
    fallback_model: str = "qwen3:8b"
    temperature: float = 0.3
    top_p: float = 0.9
    max_tokens: int = 4096
    timeout_seconds: int = 120
    think: bool = False                    # Extended thinking devre disi
```

**Environment variable destegi**: `ASR_` prefix'i ile override edilebilir (ornek: `ASR_LLM__MODEL_NAME=qwen3:8b`)

---

## 11. Servis Yasam Dongusu

**Dosya**: `apps/backend/src/main.py`

FastAPI lifespan context manager ile:

```
Uygulama Baslatma:
  1. Database kurulumu
  2. LLMService.initialize()       → Ollama/llama.cpp HTTP client baslatma
  3. RAGService.initialize()       → ChromaDB + embedding model
  4. NLIService.initialize()       → mDeBERTa model yukleme
  5. ReportGenerator olusturma     → Tum servisleri orkestre eder
  6. app.state'e atama             → Route'lardan erisilebilir hale gelir

Uygulama Kapatma:
  1. LLMService.shutdown()         → HTTP client kapatma
```

---

## 12. Dosya Yapisi

```
apps/backend/src/
├── services/
│   ├── llm_service.py           # ★ LLM client - Ollama + llama.cpp backend'leri
│   ├── report_generator.py      # ★ Pipeline orkestratoru - unified + fallback + streaming
│   ├── report_service.py        #   Rapor CRUD islemleri
│   ├── ner_service.py           #   NER servisi (devre disi)
│   ├── rag_service.py           #   RAG servisi
│   └── nli_service.py           #   NLI dogrulama servisi
├── prompts/
│   ├── system_prompt.py         # ★ Sistem prompt'lari (SYSTEM_PROMPT + UNIFIED_SYSTEM_PROMPT)
│   ├── section_prompts.py       # ★ 11 bolum tanimi, prompt builder'lar, JSON schema
│   └── few_shot_examples.py     # ★ Ornek transkript-rapor cifti
├── rag/
│   └── seed_data.py             #   RAG seed verileri (49 belge)
├── routes/
│   └── reports.py               # ★ REST + SSE API endpoint'leri
config/
└── settings.py                  # ★ LLMSettings, NERSettings, RAGSettings, NLISettings
docs/
├── llm-performance-research.md  #   Performans arastirma dokumani
└── pipeline_architecture.md     #   Genel pipeline mimarisi
```

`★` = LLM ile dogrudan ilgili dosyalar

---

## 13. Kisitlar

1. **Tamamen yerel calisma**: KVKK geregi hasta verileri cloud'a gonderilemez - cloud LLM API'leri kullanilamaz
2. **Windows 11**: Gelistirme ortami Windows, Linux-only cozumler (vLLM vb.) dogrudan kullanilamaz
3. **16GB VRAM limiti**: RTX 5080 Laptop GPU, model secimi bu sinira uygun olmali
4. **Turkce tibbi metin**: Model Turkce tibbi terminolojiyi yeterince iyi anlamali
5. **Unified JSON riski**: Parse hatasi olusursa fallback devreye girer (sure artar)
6. **NER devre disi**: Halusinasyon tespitinde entity-bazli dogrulama su an kullanilmiyor
