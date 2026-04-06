# Streaming ASR ile Hem Hiz Hem Dogruluk - Arastirma Dokumani

## Problem

Mevcut hibrit (streaming + batch) mimaride kayit bittikten sonra **tum ses dosyasi sifirdan tekrar transkribe ediliyor**. Bu, kullanicinin kayit sonrasi 2-5 dakika beklemesine neden oluyor. Kullanici streaming sirasinda zaten transkripsiyon goruyor — amac bu transkripti son cikti olarak kullanarak batch adimini **tamamen ortadan kaldirmak** veya **minimum seviyeye indirmek**.

### Hedef
- Kayit sirasinda yuksek dogruluklu streaming transkripsiyon
- Kayit bittikten sonra **sifirdan transkripsiyon YAPILMASIN**
- Sadece diarization + kelime hizalama + rapor olusturma yapilsin
- Toplam bekleme suresi: dakikalar yerine **saniyeler**

---

## Mevcut Mimari (Hibrit - Simdiki Durum)

```
KAYIT SIRASINDA:
  Ses → faster-whisper large-v3-turbo (beam=1)
      → Canli metin ekranda (ATILIYOR, DB'ye kaydedilmiyor)

KAYIT SONRASI (2-5 dakika bekleme):
  Stage 1: Gurultu bastirma (DeepFilterNet3)           ~30-60s
  Stage 2: Transkripsiyon (large-v3, beam=5)           ~60-120s  << EN YAVAS
  Stage 3: Kelime hizalama (wav2vec2)                  ~20-40s
  Stage 4: Konusmaci ayristirma (pyannote)             ~30-60s
  Stage 5: Rapor olusturma (NER + LLM)                ~10-30s
  TOPLAM:                                              ~2.5-5 dakika
```

Stage 2 (batch transkripsiyon) toplam surenin yaklasik **%50'sini** olusturuyor. Eger streaming transkripti kullanabilirsek bu adim tamamen atlanabilir.

---

## Sistem Bilgileri

```
GPU:                NVIDIA RTX 5080 Laptop GPU (16GB VRAM)
Python:             3.11.14
faster-whisper:     1.2.1
whisperx:           3.8.1
pyannote.audio:     4.0.4
torch:              2.8.0+cu128
OS:                 Windows 11 Pro
```

### Mevcut Streaming Yapilandirmasi
```python
# Streaming (kayit sirasinda)
model = "large-v3-turbo"
compute_type = "float16"
beam_size = 1        # greedy decoding - hiz icin
language = "tr"

# Batch (kayit sonrasi - ortadan kaldirilmak istenen)
model = "large-v3"
compute_type = "float16"
beam_size = 5        # beam search - dogruluk icin
batch_size = 16
```

---

## Arastirilmasi Gereken Ana Soru

**Streaming transkripsiyon dogrulugunu batch seviyesine cikarmak ve streaming ciktisini dogrudan son cikti olarak kullanmak mumkun mu?**

Alt sorular:
1. Streaming'de beam_size artirmak (1 -> 5) ne kadar yavaslatir?
2. large-v3-turbo yerine large-v3 (tam model) streaming'de kullanilabilir mi?
3. Streaming ciktisina kelime hizalama (forced alignment) uygulanabilir mi?
4. Streaming sırasında gurultu bastirma yapilabilir mi (real-time DeepFilterNet)?
5. Diarization icin streaming transkripti yeterli mi?

---

## Olasi Mimariler (Arastirilacak)

### Mimari A: Streaming Dogrulugunu Artir + Batch Atla

```
KAYIT SIRASINDA:
  Ses → [Gercek zamanli gurultu bastirma?]
      → faster-whisper large-v3 (tam model, beam=3-5)
      → Canli metin ekranda + KAYDEDILIYOR

KAYIT SONRASI (saniyeler):
  - Transkripsiyon ATLANIR (streaming ciktisi kullanilir)
  - Kelime hizalama (wav2vec2) streaming segmentlerine uygulanir
  - Konusmaci ayristirma (pyannote)
  - Rapor olusturma (NER + LLM)
  TOPLAM: ~1-2 dakika (transkripsiyon suresi cikarilmis)
```

Soru: large-v3 + beam=5 streaming'de ne kadar yavas? RTX 5080 16GB ile real-time factor nedir?

### Mimari B: Streaming + Hafif Duzeltme (Re-scoring)

```
KAYIT SIRASINDA:
  Ses → faster-whisper large-v3-turbo (beam=1)
      → Canli metin ekranda + KAYDEDILIYOR

KAYIT SONRASI (saniyeler):
  - Sadece DUZELTME yapilir (sifirdan transkripsiyon degil)
  - Ornegin: LLM ile post-correction
  - Veya: Whisper'in condition_on_previous_text ozelligi ile 2. pas
  - Kelime hizalama + diarization + rapor
  TOPLAM: ~1-2 dakika
```

Bu yaklasimda streaming ciktisi "ham taslak" olarak kullanilir, LLM tibbi terimleri duzeltir.

### Mimari C: Chunked Streaming (LocalAgreement / ufal/whisper_streaming)

```
KAYIT SIRASINDA:
  Ses → ufal/whisper_streaming LocalAgreement politikasi
      → Onceki chunk'larla tutarli, yakin-final transkript
      → Canli metin ekranda + KAYDEDILIYOR

KAYIT SONRASI (saniyeler):
  - Son chunk'in finalizasyonu
  - Kelime hizalama + diarization + rapor
  TOPLAM: <1 dakika
```

LocalAgreement: Her yeni chunk geldiginde onceki chunk'larla birlikte transkribe eder, tutarli olan kismi "kesinlesmis" olarak isaretler. Bu yaklasim ~3 saniye gecikmede batch'e yakin dogruluk sagliyor.

### Mimari D: Speculative Decoding / Cascaded Models

```
KAYIT SIRASINDA:
  Ses → large-v3-turbo (hizli, taslak transkript)
      → large-v3 (sadece dusuk guvenli segmentleri duzelt)
      → Canli metin ekranda + KAYDEDILIYOR

KAYIT SONRASI:
  - Hicbir transkripsiyon yapilmaz
  - Sadece diarization + rapor
```

Bu yaklasimda buyuk model sadece kucuk modelin "emin olmadigi" segmentleri yeniden isler. Toplam islem suresi buyuk olculde azalir.

---

## Arastirilacak Konular

### 1. Streaming Dogruluk Karsilastirmasi

faster-whisper ile su konfigurasyonlarin WER (Word Error Rate) farklarini arastir:

| Konfigurasyon | Model | beam | Beklenen WER | Beklenen Hiz |
|---|---|---|---|---|
| Mevcut streaming | large-v3-turbo | 1 | ? | ~200-500ms/3s segment |
| Iyilestirilmis streaming | large-v3-turbo | 3 | ? | ? |
| Iyilestirilmis streaming | large-v3-turbo | 5 | ? | ? |
| Tam model streaming | large-v3 | 1 | ? | ? |
| Tam model streaming | large-v3 | 3 | ? | ? |
| Mevcut batch | large-v3 | 5 | En dusuk | ~60-120s/10dk ses |

Turkce icin bu karsilastirma var mi? Yoksa genel benchmark'lardan tahmin edilebilir mi?

### 2. Real-time Factor (RTF) Analizi

RTX 5080 16GB GPU'da su modellerin real-time factor degerleri nedir?

- large-v3-turbo float16: 3 saniyelik segment kac ms'de islenir?
- large-v3 float16: 3 saniyelik segment kac ms'de islenir?
- beam=1 vs beam=3 vs beam=5 hiz farki nedir?

**RTF < 1.0 olmali** (yani 3 saniyelik ses 3 saniyeden kisa surede islenmeli) streaming icin.

Ornek: RTF = 0.1 demek 3 saniyelik ses 0.3 saniyede islenir → streaming icin mukemmel.

### 3. initial_prompt ve condition_on_previous_text Etkisi

Streaming'de `initial_prompt` (tibbi terimler) ve `condition_on_previous_text=True` kullaniliyor. Bunlarin dogruluktaki etkisi ne kadar?

- `initial_prompt` ile WER ne kadar duser? (%5? %10? %20?)
- `condition_on_previous_text` streaming'de hata propagasyonu yapar mi?
- Daha uzun/detayli tibbi terim listesi dogrulugu arttirir mi?

### 4. ufal/whisper_streaming ve LocalAgreement

- `ufal/whisper_streaming` kutuphanesi nedir?
- LocalAgreement politikasi nasil calisir?
- faster-whisper backend'i ile uyumlu mu?
- Dogruluk batch'e ne kadar yakin? (raporlanan rakamlara gore)
- Python API'si nasil? Entegre etmek zor mu?

### 5. WhisperLive ve SimulStreaming

- `collabora/WhisperLive`: Streaming ASR server, faster-whisper kullanir
- `RealAcoustics/SimulStreaming`: 2025'te yayinlanan, daha hizli streaming
- Bu projeler nasil calisir? Bizim mimariye entegre edilebilir mi?

### 6. LLM Post-Correction

Streaming ciktisini LLM ile duzeltmek:
- Ornegin: "hastaligininin" → "hastalığının" (deASCIIfication)
- Tibbi terim duzeltme: "kardiak" → "kardiyak"
- Bu yaklasim ne kadar etkili? WER'i ne kadar dusurur?
- Hangi LLM kullanilmali? (Yerel Ollama vs API)
- Gecikme ne kadar ekler?

### 7. Kelime Hizalama Streaming Ciktisiyla Uyumlu mu?

WhisperX'in `align()` fonksiyonu streaming segmentlerine uygulanabilir mi?
- Streaming segmentleri kelime-seviyesi timestamp icerir mi? (faster-whisper `word_timestamps=True`)
- Eger streaming zaten kelime timestamp'leri veriyorsa, ayri bir align adimina gerek var mi?
- `faster-whisper` ile `word_timestamps=True` kullanmak hizi ne kadar etkiler?

### 8. Gercek Zamanli Gurultu Bastirma

DeepFilterNet3'u streaming modda kullanmak mumkun mu?
- DeepFilterNet3 frame-by-frame isleyebilir mi?
- Real-time latency nedir?
- Yoksa daha hafif bir alternatif var mi? (RNNoise, PercepNet)
- Streaming'de gurultu bastirma gerekli mi? (Whisper zaten gurultulu sese dayanikli)

---

## Mevcut Kod Referanslari

### Streaming Transcriber (mevcut)
Dosya: `apps/backend/src/asr/streaming_transcriber.py`

```python
class StreamingTranscriber:
    def __init__(self, settings, medical_prompt, gpu_manager):
        self._settings = settings          # StreamingSettings
        self._medical_prompt = medical_prompt
        self._previous_text = ""           # Onceki baglam

    def load_model(self):
        from faster_whisper import WhisperModel
        self._model = WhisperModel(
            "large-v3-turbo",              # << Degistirilebilir: large-v3?
            device="cuda",
            compute_type="float16",
        )

    def transcribe_segment(self, audio_np):
        # initial_prompt: tibbi terimler + onceki metin
        prompt = self._medical_prompt + " " + self._previous_text[-500:]
        
        segments, info = self._model.transcribe(
            audio_np,
            language="tr",
            beam_size=1,                   # << Degistirilebilir: 3? 5?
            initial_prompt=prompt,
            vad_filter=True,
        )
        
        text = " ".join(seg.text.strip() for seg in segments)
        self._previous_text += " " + text
        return StreamingResult(text=text)
```

### Streaming Settings (mevcut)
Dosya: `apps/backend/src/asr/settings.py`

```python
class StreamingSettings(BaseModel):
    model_name: str = "large-v3-turbo"     # << large-v3 olabilir mi?
    compute_type: str = "float16"
    device: str = "cuda"
    language: str = "tr"
    beam_size: int = 1                     # << 3-5 olabilir mi?
    vad_threshold: float = 0.5
    min_speech_duration_ms: int = 250
    speech_pad_ms: int = 400
    condition_on_previous_text: bool = True
```

### Batch Pipeline (ortadan kaldirilmak istenen)
Dosya: `apps/backend/src/asr/pipeline.py`

```python
async def batch_process(self, wav_path, progress_callback=None):
    # Stage 0: Validate
    # Stage 1: Noise suppression (DeepFilterNet3)      ~30-60s
    # Stage 2: Transcription (large-v3, beam=5)        ~60-120s  << KALDIRMAK ISTIYORUZ
    # Stage 3: Alignment (wav2vec2)                    ~20-40s
    # Stage 4: Diarization (pyannote)                  ~30-60s
    # Stage 5: Format + save
```

### VAD (mevcut)
Dosya: `apps/backend/src/asr/vad.py`

```python
class SileroVAD:
    # torch.hub Silero VAD modeli
    # 512-sample frame'ler (32ms @ 16kHz)
    # VADIterator API ile streaming uyumlu
    # Konusma baslangic/bitis algiliyor
    # Tamamlanan segmentleri numpy array olarak donduruyor
```

### Audio Akisi
```
Frontend (250ms WebM/Opus chunks)
  → WebSocket → Backend
  → AudioChunkConverter (FFmpeg pipe: WebM → PCM 16kHz float32)
  → AudioAccumulator (batch icin biriktirir)
  → SileroVAD (konusma segmenti algila)
  → StreamingTranscriber (faster-whisper, ~200-500ms/segment)
  → WebSocket → Frontend (interim_transcript)
```

---

## Beklenen Cikti

Arastirma sonucunda su sorulara cevap bekliyoruz:

1. **En iyi mimari hangisi?** (A/B/C/D veya baska bir oneri)
2. **Streaming'de hangi model + beam_size kullanilmali?**
3. **Batch transkripsiyon tamamen atlanabilir mi?**
4. **Kelime hizalama streaming ciktisiyla yapilabilir mi?**
5. **Toplam bekleme suresi ne kadar dusurulebilir?**
6. **Dogruluk kaybi ne kadar olur?** (WER farki)
7. **Somut implementasyon adimlari neler?**

---

## Kisitlar

- GPU: RTX 5080 16GB VRAM — streaming modeli VRAM'e sigmali
- Dil: Turkce (tibbi terminoloji, code-switching: Turkce cumle icinde Latince tibbi terimler)
- Gecikme: Streaming sirasinda metin ~1-3 saniyede gorunmeli
- Dogruluk: Tibbi terimler icin yuksek dogruluk kritik (ilac adlari, hastalik isimleri)
- Altyapi: Windows 11, Python 3.11, faster-whisper, pyannote 4.0
