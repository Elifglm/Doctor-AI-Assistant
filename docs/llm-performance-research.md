# LLM Rapor Oluşturma Performans Problemi - Araştırma Dokümanı

## 1. Proje Nedir?

Türkçe doktor-hasta görüşmelerini otomatik olarak kayıt altına alan ve anamnez raporu oluşturan bir masaüstü uygulaması geliştiriyoruz. Akış şu şekilde:

1. Doktor, hasta ile görüşmeye başlar ve uygulamadan **ses kaydı** başlatır
2. Ses kaydı bittikten sonra **ASR (Automatic Speech Recognition)** pipeline çalışır:
   - Gürültü bastırma (DeepFilterNet)
   - Konuşma tanıma (WhisperX large-v3-turbo)
   - Konuşmacı ayrıştırma (pyannote diarization) → "Doktor: ...", "Hasta: ..." formatında transkript
3. Transkript elde edildikten sonra **LLM pipeline** çalışır:
   - NER (Named Entity Recognition) ile tıbbi bilgiler çıkarılır
   - RAG (Retrieval Augmented Generation) ile referans bilgi getirilir
   - LLM ile 12 bölümlük standart anamnez raporu oluşturulur
4. Doktor oluşturulan raporu inceler, düzenler ve onaylar

**Tez projesidir.** 4 kişilik bir ekip tarafından geliştirilmektedir.

---

## 2. Problem

**~1 dakikalık bir ses kaydının transkriptinden anamnez raporu oluşturulması yaklaşık 9 dakika sürüyor.** Bu klinik ortamda kabul edilemez bir süre. Hedefimiz bu süreyi önemli ölçüde düşürmek (ideal: 30 saniye veya altı).

---

## 3. Donanım

| Bileşen | Detay |
|---------|-------|
| **GPU** | NVIDIA GeForce RTX 5080 Laptop GPU |
| **VRAM** | 16 GB (16302 MB) |
| **İşletim Sistemi** | Windows 11 Pro |
| **Python** | 3.11 (Conda: `asr` environment) |
| **RAM** | Yeterli (spesifik değer bilinmiyor ama sorun yok) |

---

## 4. Mevcut Mimari ve Akış

### 4.1 Genel Mimari
```
Frontend (Electron + React + TypeScript)
    ↕ REST API + WebSocket + SSE
Backend (Python FastAPI, port 8700)
    ↕
Ollama (localhost:11434) ← LLM çalıştırıyor
```

### 4.2 LLM Pipeline Akışı (Sorunlu Kısım)

Transkript hazır olduktan sonra şu pipeline sırayla çalışır:

```
[1] NER Extraction (GLiNER, CPU, ~500MB model)
        ↓
[2] Her bölüm için RAG Query (ChromaDB, 49 belge)
        ↓
[3] Her bölüm için LLM Generation (Ollama, Qwen3:14b, GPU)
        ↓
[4] Validation (CPU, anlık)
```

### 4.3 Kritik Sorun: 12 AYRI LLM ÇAĞRISI

Raporun 12 bölümü var ve **her bölüm için ayrı bir LLM çağrısı yapılıyor**. Bu çağrılar **sıralı (sequential)** olarak çalışıyor:

```
Bölüm 1: Başvuru Şikayeti         → LLM çağrısı (prompt gönder, cevap bekle)
Bölüm 2: Şimdiki Hastalık Hikayesi → LLM çağrısı (prompt gönder, cevap bekle)
Bölüm 3: Geçmiş Tıbbi Özgeçmiş    → LLM çağrısı (prompt gönder, cevap bekle)
Bölüm 4: Kullanılan İlaçlar       → LLM çağrısı (prompt gönder, cevap bekle)
Bölüm 5: Alerjiler                → LLM çağrısı (prompt gönder, cevap bekle)
Bölüm 6: Aile Öyküsü              → LLM çağrısı (prompt gönder, cevap bekle)
Bölüm 7: Sosyal Öykü              → LLM çağrısı (prompt gönder, cevap bekle)
Bölüm 8: Sistemlerin Gözden Geç.  → LLM çağrısı (prompt gönder, cevap bekle)
Bölüm 9: Fizik Muayene            → LLM çağrısı (prompt gönder, cevap bekle)
Bölüm 10: Değerlendirme           → LLM çağrısı (prompt gönder, cevap bekle)
Bölüm 11: Tedavi Planı            → LLM çağrısı (prompt gönder, cevap bekle)
Bölüm 12: Ek Notlar               → LLM çağrısı (prompt gönder, cevap bekle)
```

Yani toplam süre = **12 × (tek bölüm LLM süresi)** + NER süresi + RAG süresi

Tahmini kırılım (9 dakika = 540 saniye):
- NER: ~10-15 saniye
- RAG (12 sorgu): ~2-3 saniye
- **LLM (12 çağrı): ~520 saniye** ← DARBOĞAZ BURASI
- Validation: <1 saniye

**Her LLM çağrısı ortalama ~43 saniye sürüyor.**

---

## 5. Her LLM Çağrısında Ne Gönderiliyor?

Her bölüm için Ollama'ya gönderilen prompt şu yapıda:

```
SYSTEM PROMPT (~200 token):
  "Sen bir Türkçe tıbbi dokümantasyon asistanısın..." (8 kural)

USER PROMPT (her bölüm için):
  TRANSKRIPT:
    <TÜM TRANSKRİPT METNİ - tüm konuşma>

  TESPİT EDİLEN TIBBİ BİLGİLER:
    <NER entity'leri - o bölümle ilgili olanlar>

  REFERANS BİLGİ:
    <RAG'den gelen 5 belge>

  GÖREV:
    <Bölüme özel talimat, 2-3 cümle>

  BÖLÜM: <Bölüm adı>
  "Sadece bu bölümün içeriğini yaz."
```

**Önemli:** Transkript metni her 12 çağrıda da TEKRAR gönderiliyor. Yani 1 dakikalık bir konuşmanın transkripti (~500-1000 token) 12 kez işleniyor.

---

## 6. Kullanılan Modeller ve Ayarlar

### 6.1 LLM: Qwen3:14b (Ollama ile)
| Ayar | Değer |
|------|-------|
| **Model** | `qwen3:14b` (Q4_K_M quantization, ~12GB VRAM) |
| **Yedek model** | `qwen3:8b` (~6GB VRAM) |
| **Temperature** | 0.3 |
| **Top-p** | 0.9 |
| **Max tokens** | 2048 (her bölüm için) |
| **Timeout** | 300 saniye |
| **Ollama URL** | `http://localhost:11434` |
| **API endpoint** | `POST /api/generate` (non-streaming mod kullanılıyor) |

### 6.2 NER: GLiNER
| Ayar | Değer |
|------|-------|
| **Model** | `urchade/gliner_multi-v2.1` |
| **Device** | CPU |
| **Threshold** | 0.5 |
| **Labels** | semptom, hastalık, ilaç, dozaj, alerji, ameliyat, tıbbi_test, vücut_bölümü, süre, aile_hastalığı, sigara, alkol, meslek (13 label) |

### 6.3 RAG: ChromaDB
| Ayar | Değer |
|------|-------|
| **Toplam belge** | 49 (25 ICD-10 kodu + 15 ilaç + 7 kılavuz + 2 şablon) |
| **Embedding** | ChromaDB varsayılan (all-MiniLM-L6-v2) |
| **Sorgu sayısı** | Her bölüm için 5 sonuç (`n_results=5`) |

---

## 7. Kod Yapısı (İlgili Dosyalar)

```
apps/backend/src/
├── services/
│   ├── llm_service.py          # Ollama HTTP client (httpx async)
│   ├── ner_service.py          # GLiNER NER extraction
│   ├── rag_service.py          # ChromaDB retrieval
│   └── report_generator.py     # Pipeline orkestratör (NER → RAG → LLM → Validation)
├── prompts/
│   ├── system_prompt.py        # 8 kurallık sistem prompt'u
│   ├── section_prompts.py      # 12 bölüm tanımı + prompt builder
│   └── few_shot_examples.py    # Örnek transkript→rapor çifti
├── routes/
│   └── reports.py              # POST /api/v1/reports (AI generation endpoint)
config/
└── settings.py                 # LLMSettings, NERSettings, RAGSettings
```

### 7.1 Darboğaz Kodu: `report_generator.py` (Sıralı Döngü)

```python
# Bu döngü sıralı çalışıyor - her bölüm bir öncekinin bitmesini bekliyor
for i, key in enumerate(section_keys):  # 12 bölüm
    # RAG query (~0.2s)
    rag_results = await self.rag.query(query_text)

    # Prompt oluştur (tüm transkript + NER + RAG her seferinde dahil)
    prompt = build_section_prompt(key, full_text, section_entities, rag_results)

    # LLM çağrısı (~43 saniye) ← ANA DARBOĞAZ
    content = await self.llm.generate(prompt, SYSTEM_PROMPT)
```

### 7.2 LLM Çağrısı: `llm_service.py`

```python
async def generate(self, prompt: str, system: str = "") -> str:
    payload = {
        "model": self.model,           # "qwen3:14b"
        "prompt": prompt,               # Transkript + NER + RAG + görev
        "system": system,               # Sistem prompt'u
        "stream": False,                # Non-streaming - tüm cevabı bekle
        "options": {
            "temperature": 0.3,
            "top_p": 0.9,
            "num_predict": 2048,        # Max output token
        },
    }
    resp = await self.client.post("/api/generate", json=payload)
    return resp.json().get("response", "")
```

---

## 8. 12 Bölümün Listesi

| # | Bölüm Key | Bölüm Adı (TR) | Tipik Çıktı Uzunluğu |
|---|-----------|-----------------|----------------------|
| 1 | chief_complaint | Başvuru Şikayeti | 1-2 cümle |
| 2 | history_present | Şimdiki Hastalık Hikayesi | 3-5 cümle |
| 3 | past_medical | Geçmiş Tıbbi Özgeçmiş | 1-3 cümle veya "Belirtilmedi" |
| 4 | medications | Kullanılan İlaçlar | Liste veya "Belirtilmedi" |
| 5 | allergies | Alerjiler | 1 cümle veya "Belirtilmedi" |
| 6 | family_history | Aile Öyküsü | 1-2 cümle veya "Belirtilmedi" |
| 7 | social_history | Sosyal Öykü | 1-3 cümle veya "Belirtilmedi" |
| 8 | review_systems | Sistemlerin Gözden Geçirilmesi | 2-4 cümle veya "Belirtilmedi" |
| 9 | physical_exam | Fizik Muayene | 2-4 cümle veya "Belirtilmedi" |
| 10 | assessment | Değerlendirme | 1-3 cümle |
| 11 | plan | Tedavi Planı | 3-5 madde |
| 12 | notes | Ek Notlar | 1 cümle veya "Belirtilmedi" |

**Not:** Bölümlerin çoğu çok kısa çıktı üretiyor (1-3 cümle), ama her biri için tam 14B parametreli model çalışıyor ve her seferinde TÜM transkript yeniden gönderiliyor.

---

## 9. Neden Bu Kadar Yavaş? (Analiz)

### 9.1 Ana Nedenler

1. **12 ayrı LLM çağrısı**: Her bölüm için ayrı HTTP request + model inference. Her çağrıda prompt processing (prefill) + token generation (decode) süresi var.

2. **Prompt tekrarı**: ~500-1000 token'lık transkript metni her 12 çağrıda tekrar gönderiliyor. Ollama her seferinde prompt'u sıfırdan process ediyor.

3. **Qwen3:14b büyük model**: 14B parametre, Q4_K_M quantization ile ~12GB VRAM. RTX 5080 Laptop'ta inference hızı sınırlı.

4. **Ollama cold start**: Her çağrıda model yeniden context'e yüklenebilir (Ollama'nın KV cache yönetimine bağlı).

5. **Non-streaming mod**: `stream: False` ile tüm response bekleniyorken, kullanıcıya hiçbir feedback verilmiyor (aslında streaming endpoint var ama mevcut test non-streaming kullanıyor).

6. **max_tokens=2048**: Her bölüm için 2048 token reserve ediliyor, ama çoğu bölüm 50-100 token üretiyor.

### 9.2 Tahmini Süre Kırılımı (tek LLM çağrısı, ~43 saniye)

```
Prompt tokenization:  ~0.5s
Prompt prefill:       ~5-10s (transkript + NER + RAG ~ 800-1500 token input)
Token generation:     ~30-35s (çıktı üretme, ~40-60 token/s decode hızı varsayımıyla)
HTTP overhead:        ~0.5s
```

**Ama wait:** Eğer decode hızı 40-60 tok/s ise ve çıktı 50-100 token ise, generation ~1-2.5s olmalı. O zaman büyük süre nerede?

Muhtemel ek nedenler:
- Ollama'nın KV cache'i yeterince büyük olmayabilir, her çağrıda prompt'u yeniden process ediyordur
- Qwen3'ün "thinking mode"u aktif olabilir (/think tokenları üretiyor olabilir, görünmeyen iç reasoning)
- Ollama'nın model yükleme/boşaltma overhead'i
- num_predict=2048 ile model durma koşulunu geç algılıyor olabilir

---

## 10. Olası Çözüm Yönleri (Araştırılacak)

Aşağıdaki yaklaşımları araştırmanı istiyoruz. Her birinin uygulanabilirliğini, avantajlarını/dezavantajlarını ve bizim senaryomuza (Türkçe medikal, yerel GPU, 14B model, Ollama) uygunluğunu değerlendir:

### 10.1 Tek Çağrıda 12 Bölüm (Prompt Birleştirme)
12 ayrı çağrı yerine tek bir çağrıda tüm bölümleri oluşturmak. JSON veya structured output formatında.
- Avantaj: 12x prompt prefill overhead ortadan kalkar
- Risk: Çıktı kalitesi düşebilir mi? Token limiti yeterli mi?

### 10.2 Daha Küçük/Hızlı Model
- `qwen3:8b` (6GB VRAM, ~2x daha hızlı)
- `qwen3:4b` veya `qwen3:1.7b`
- `gemma3:4b` veya `phi4-mini`
- Türkçe tıbbi metin kalitesi kabul edilebilir mi?

### 10.3 Ollama Ayar Optimizasyonları
- `num_ctx` (context window) düşürmek
- `num_batch` artırmak
- `num_gpu` layer ayarı
- KV cache boyutu
- `OLLAMA_NUM_PARALLEL` environment variable
- `keep_alive` ile modeli bellekte tutmak

### 10.4 Ollama Alternatifi: vLLM, llama.cpp, TGI
- vLLM: Continuous batching, PagedAttention → çok daha hızlı inference
- llama.cpp server: Doğrudan GGUF model, prefix caching
- Hugging Face TGI: Production-ready inference server
- Bunlar Windows'ta çalışır mı?

### 10.5 Prompt Kısaltma / Optimizasyon
- Transkripti özetleyip kısa versiyonu göndermek
- Sadece ilgili segmentleri göndermek (NER entity'leri etrafındaki context)
- Sistem prompt'u kısaltmak
- RAG sonuçlarını kaldırmak veya azaltmak

### 10.6 Paralel LLM Çağrıları
- Ollama'da `OLLAMA_NUM_PARALLEL` ile aynı anda birden fazla request
- Ancak GPU belleği yeterli mi? 14B model zaten ~12GB kullanıyor
- 8B model ile paralel çağrı?

### 10.7 Qwen3 Thinking Mode Kontrolü
- Qwen3 varsayılan olarak "thinking" modunda çalışıyor olabilir (`<think>...</think>` tokenları üretiyor)
- `/no_think` komutu veya prompt'a ekleme ile thinking'i devre dışı bırakmak
- Bu decode token sayısını dramatik şekilde azaltabilir

### 10.8 Speculative Decoding
- Küçük draft model + büyük model ile hızlandırma
- Ollama bunu destekliyor mu?

### 10.9 Prefix Caching
- Transkript her 12 çağrıda aynı → prefix cache ile sadece 1 kez process edilir
- Ollama'da bu var mı? vLLM/llama.cpp'de var mı?

### 10.10 Batch Processing
- 12 prompt'u tek seferde batch olarak göndermek
- Ollama API batch destekliyor mu?

---

## 11. Kısıtlarımız

1. **Tamamen yerel çalışmalı**: KVKK (Türk GDPR) gereği hasta verileri dışarıya gönderilemez. Cloud API (OpenAI, Anthropic vb.) kullanamayız.
2. **Windows 11**: Geliştirme ve çalışma ortamı Windows. Linux-only çözümler uygulanamaz (WSL ile çalışabilirlik araştırılabilir).
3. **Türkçe tıbbi metin**: Model Türkçe tıbbi terminolojiyi iyi anlamalı.
4. **RTX 5080 Laptop (16GB VRAM)**: Daha fazla VRAM yok. Model + inference bu sınır içinde kalmalı.
5. **Ollama şu an kurulu ve çalışıyor**: Mümkünse Ollama üzerinden çözüm tercih edilir, ama gerekirse alternatife geçilebilir.
6. **Kalite önemli**: Hız için kaliteden çok fazla ödün vermek istemiyoruz. Raporun doktor tarafından inceleneceğini unutma, ama temel bilgilerin doğru çıkması lazım.

---

## 12. Araştırma Soruları

Lütfen şunları araştır:

1. **Qwen3:14b'nin Ollama'da gerçek inference hızı nedir?** (tok/s, RTX 5080 veya benzer GPU'larda benchmark)
2. **Qwen3'ün thinking mode'u varsayılan olarak açık mı?** Kapatmanın etkisi ne olur?
3. **Ollama'da prefix caching var mı?** Yoksa hangi inference engine'de var?
4. **12 bölümü tek prompt'ta oluşturmak kaliteyi ne kadar etkiler?** Structured output (JSON mode) ile yapılabilir mi?
5. **vLLM Windows'ta çalışır mı?** WSL gerekir mi? Performans farkı ne olur?
6. **Qwen3:8b vs Qwen3:14b Türkçe tıbbi metin kalitesi karşılaştırması**
7. **Ollama ayar optimizasyonları** (num_ctx, num_batch, keep_alive, num_parallel) ile ne kadar iyileşme sağlanır?
8. **llama.cpp server + prefix caching** seçeneği Windows'ta uygulanabilir mi?
9. **Batch inference** (birden fazla prompt'u paralel/batch işleme) Ollama'da mümkün mü?
10. **Alternatif daha hızlı Türkçe destekli modeller** var mı? (Aya-Expanse, Gemma 3, Phi-4, Llama 3.3 vb.)

---

## 13. Hedef

Mevcut 9 dakikayı **30 saniye veya altına** düşürmek. Kabul edilebilir bir çıktı kalitesiyle.

Araştırma sonuçlarını bulduğun gibi paylaş, beraber en uygun çözümü belirleyip uygulayacağız.
