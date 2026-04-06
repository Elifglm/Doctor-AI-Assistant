# ASR Performans Iyilestirme Arastirma Raporu

## Mevcut Durum Ozeti

Turkce klinik ASR uygulamasi (doktor-hasta gorusmesi transkripsiyon) batch modda calisiyor. Gercek ses kayitlariyla test edildiginde **performans cok kotu**. Kullanicinin gercek kaydiyla test sonuclari:

- **Yanlis kelimeler cok fazla** — Turkce'ye ozgu morfoloji hatalari, fonetik karisikliklar
- **Diarization (konusmaci ayristirma) birbirine karisiyor** — Doktor/Hasta etiketleri yanlis ataniyor
- **Ust uste konusmalarda (overlapping speech) sistem cokuyor** — ne transkripsiyon ne diarization duzgun calismiyor

### Sentetik Ses Test Sonuclari (Referans)
| Test | WER | Aciklama |
|------|-----|----------|
| gTTS tibbi diyalog | %8-12 | Sentetik ses, temiz, tek konusmaci |
| FLEURS gercek Turkce | %17.5 (normalized) | Gercek ses, genel icerik |
| **Gercek klinik kayit** | **Cok yuksek** | Gercek ortam, 2 konusmaci, gurultu, ust uste konusma |

### Hiz (Bu konuda sorun yok)
| Ses Suresi | Islem Suresi | RTF |
|-----------|-------------|-----|
| 5dk | 38s | 0.122 |
| 2.5dk | 31s | 0.24 |

---

## Sistem Mimarisi (Mevcut)

### Pipeline Akisi
```
WAV Dosyasi
  |
  v
[Stage 1] faster-whisper BatchedInferencePipeline
           Model: large-v3, float16, batch_size=16, beam_size=5
           temperature=0.0, vad_filter=True
           hotwords: tibbi terimler listesi
           condition_on_previous_text=False (batched modda zorunlu)
  |
  v
[Stage 2] TurkishPostProcessor
           1. DeASCIIfication (turkish-deasciifier)
           2. Zemberek morfolojik analiz (sadece loglama)
           3. Statik tibbi terim sozlugu duzeltme
  |
  v
[Stage 3] pyannote speaker-diarization-3.1
           num_speakers=2, torchaudio.load workaround
           exclusive_speaker_diarization (pyannote 4.0)
           Kelime bazli speaker atama + segment bolme
  |
  v
[Stage 4] DB kayit + Rapor olusturma (NER + LLM)
```

### Dosya Yapisi
```
apps/backend/src/asr/
  pipeline.py         # Ana orkestrator - BatchASRPipeline.process()
  settings.py         # Yapilandirma - BatchTranscriptionSettings, DiarizationSettings
  diarizer.py         # pyannote entegrasyonu + kelime bazli speaker atama
  post_processor.py   # Turkce duzeltme (deasciify + zemberek + sozluk)
  audio_utils.py      # AudioAccumulator (WebM → WAV donusumu)
  gpu_manager.py      # GPU bellek yonetimi (mod gecisi)
  output_formatter.py # Segment formatlama
  exceptions.py       # Hata siniflari

apps/backend/src/services/
  asr_service.py      # Async singleton wrapper

apps/backend/src/ws/
  audio_handler.py    # WebSocket handler (kayit + isleme)
```

---

## Detayli Kod Aciklamalari

### 1. pipeline.py — BatchASRPipeline

Tek giris noktasi: `process(wav_path, progress_callback) -> dict`

**Transkripsiyon (Stage 1):**
```python
from faster_whisper import WhisperModel, BatchedInferencePipeline

model = WhisperModel("large-v3", device="cuda", compute_type="float16")
batched = BatchedInferencePipeline(model=model)

segments_iter, info = batched.transcribe(
    wav_path,
    language="tr",
    beam_size=5,
    batch_size=16,
    temperature=0.0,
    word_timestamps=True,
    vad_filter=True,
    hotwords="kol kolunda kolumda ... tibbi terimler ...",
    hallucination_silence_threshold=2.0,
)
```

**Onemli notlar:**
- `BatchedInferencePipeline` kullaniliyor (sequential `model.transcribe()` degil)
- `condition_on_previous_text=False` hardcoded (batched modda degistirilemez)
- Her VAD segmenti BAGIMSIZ olarak transkribe ediliyor — onceki segmenten baglam tasinmiyor
- `initial_prompt` KULLANILMIYOR — batched modda dogrulugu dusurdugu tespit edildi
- `hotwords` ile tibbi terim bias veriliyor

**Post-processing (Stage 2):**
```python
processor = TurkishPostProcessor()
for seg in segments:
    seg["text"] = processor.process(seg["text"])
```
3 adimli: deASCIIfication → Zemberek loglama → statik sozluk duzeltme

**Diarization (Stage 3):**
```python
# pyannote 4.0 workaround: torchaudio.load ile in-memory waveform
waveform, sample_rate = torchaudio.load(audio_path)
result = pipeline({"waveform": waveform, "sample_rate": sample_rate}, num_speakers=2)
diarization = result.exclusive_speaker_diarization
```

**Speaker atama — KELIME BAZLI BOLME:**
```python
# Her kelimeye diarization'dan speaker ata
# Speaker degistiginde yeni segment olustur
for word in words:
    w_speaker = get_speaker_for_time(w_start, w_end)
    if w_speaker != current_speaker:
        # Onceki segmenti kaydet, yeni segment basla
```

### 2. settings.py — Yapilandirma

```python
class BatchTranscriptionSettings:
    model_name = "large-v3"
    compute_type = "float16"
    beam_size = 5
    batch_size = 16
    temperature = 0.0
    word_timestamps = True
    vad_filter = True
    hotwords = "kol kolunda kolumda ... (677 karakter tibbi terim listesi)"

class DiarizationSettings:
    model_name = "pyannote/speaker-diarization-3.1"
    num_speakers = 2
    default_labels = {"SPEAKER_00": "Doktor", "SPEAKER_01": "Hasta"}
```

### 3. diarizer.py — Konusmaci Ayristirma

**pyannote 4.0 workaround'lari:**
- `torchaudio.load()` ile in-memory waveform (torchcodec DLL sorunu)
- `exclusive_speaker_diarization` (ortusme olmayan cikti)
- `token=` parametresi (eski `use_auth_token` kaldirildi)

**Kelime bazli speaker atama:**
- Whisper uzun segmentler uretir (30s+)
- Her kelimeye diarization turn'lerinden en cok ortüsen speaker atanir
- Speaker degistiginde segment bolunur
- Ornek: 4 Whisper segmenti → 20 speaker-ayrimli segmente bolunur

**SPEAKER_00/01 mapping sorunu:**
- pyannote hangi konusmacinin doktor oldugunu bilmez
- SPEAKER_00 = Doktor, SPEAKER_01 = Hasta sabit mapping kullaniliyor
- Bu mapping her kayitta YANLIS olabilir (pyannote atamasirastgele)

### 4. post_processor.py — Turkce Duzeltme

**3 katmanli duzeltme:**
1. `turkish-deasciifier`: ASCII → Turkce karakter donusumu ("gogus" → "göğüs")
2. Zemberek morfolojik analiz: Gecersiz kelimeleri tespit et (SADECE LOGLAMA, duzeltme yok)
3. Statik sozluk: Bilinen Whisper hatalarini duzelt ("kulumda" → "kolumda")

**Zemberek sorunlari:**
- `TurkishSpellChecker` crash ediyor (numpy int8 overflow)
- Morfolojik analiz "kulumda"yi gecerli kabul ediyor (kul+um+da)
- Sadece loglama yapiyor, gercek duzeltme yapmiyor

### 5. audio_utils.py — Ses Donusumu

**AudioAccumulator:**
- Frontend 250ms WebM/Opus chunk'lar gonderir
- Chunk'lar biriktirilir
- Kayit bitince FFmpeg ile tek seferde WAV'a donusturulur (16kHz mono PCM)
- Streaming yok — sadece biriktir + donustur

### 6. audio_handler.py — WebSocket Handler

**Akis:**
1. WS baglantisi acilir
2. Binary chunk'lar gelir → `accumulator.add_raw()` (sadece biriktir)
3. `{type: "stop"}` gelir → `_process_recording()`:
   - WebM → WAV donusumu
   - Batch ASR pipeline calistir
   - Segment'leri DB'ye kaydet
   - Rapor olustur
   - Sonucu frontend'e gonder

---

## Tespit Edilen Problemler

### Problem 1: Gercek Seste Transkripsiyon Kalitesi Cok Dusuk

**Belirtiler:**
- Bircok kelime yanlis taniniyor
- Turkce'ye ozgu morfoloji hatalari (ek hatalari, sesli harf karisiikliklari)
- Sayilar ve ozel isimler yanlis

**Teknik Nedenler:**
- `BatchedInferencePipeline` her VAD segmentini BAGIMSIZ isliyor
- `condition_on_previous_text=False` hardcoded — onceki cumleden baglam tasinmiyor
- Whisper'in Turkce zero-shot WER'i zaten %4.3-14.2 arasinda (temiz seste)
- Gercek ortam sesi (gurultu, yanki, mikrofon kalitesi) WER'i daha da artiriyor

**Test Sonuclari:**
- Sentetik ses (gTTS): WER ~%8-12 (iyi)
- Gercek ses (FLEURS): WER ~%17.5 (orta)
- Gercek klinik kayit: WER tahmin %25-35+ (kotu)

### Problem 2: Diarization Birbirine Karisiyor

**Belirtiler:**
- Doktor cumlesi "Hasta" olarak etiketleniyor
- Hasta cumlesi "Doktor" olarak etiketleniyor
- Bazi segmentlerde etiket tamamen yanlis

**Teknik Nedenler:**

1. **SPEAKER_00/01 mapping rastgele**: pyannote konusmacilari ayirir ama "hangisi doktor" bilmez. Sabit mapping (SPEAKER_00=Doktor) her kayitta yanlis olabilir.

2. **Ust uste konusma (overlapping speech)**: Doktor ve hasta ayni anda konustugunda:
   - pyannote `exclusive_speaker_diarization` kullaniyor — bu ortusmeyi KALDIRIR
   - Ortusme olan bolgelerde yalnizca bir konusmaci secilir, digeri kaybolur
   - Bu, hem transkripsiyon hem diarization hatasi olusturur

3. **Kelime bazli speaker atama hassas**: Her kelime icin diarization turn'u ile ortusme hesaplaniyor. Kisa kelimelerde (0.1-0.2s) ortusme hesabimhassas degil — yanlis speaker atanabilir.

### Problem 3: Ust Uste Konusma (Overlap) Tamamen Bozuyor

**Belirtiler:**
- Doktor ve hasta ayni anda konustugunda ne ASR ne diarization duzgun calisir
- Whisper iki sesi karistirip anlamsiz metin uretiyor
- pyannote overlap bolgesinde sadece bir konusmaci seciyor

**Teknik Nedenler:**
- Whisper tek konusmaci icin tasarlanmis — ust uste konusmada performans dramatik duser
- `exclusive_speaker_diarization` overlap'i zorla tek konusmaciya indirgiyor
- Bu kayip telafi edilemiyor

---

## Mevcut Post-Processing Eksiklikleri

### Zemberek Calismiyor
- `TurkishSpellChecker` numpy overflow hatasi veriyor
- Morfolojik analiz "kulumda"yi gecerli buluyor (kul+um+da ayrimi)
- Sadece loglama yapiyor — hicbir kelimeyi duzeltmiyor

### Statik Sozluk Yetersiz
- Sadece onceden tanimlanmis hatalari duzeltir
- Yeni hatalar icin manuel ekleme gerekir
- Baglama bagimli duzeltme yapamaz ("kolumda" vs "kulumda" — ikisi de gecerli)

### DeASCIIfication Sinirli
- Sadece ASCII → Turkce karakter donusumu
- Eger Whisper zaten Turkce karakter kullaniyorsa etkisiz

---

## Kullanici Yorumlari (Gercek Test)

> "Baya yanlis kelimeler vardi. Diarization birbirine karismisti. Cok kotu bir performans."

> "Ust uste konusmalar da vardi. O da hataya suruklemiş olabilir."

> "Gercek ses kaydinda baya kotu calisti."

---

## Sistem Bilgileri

```
GPU:                NVIDIA RTX 5080 Laptop GPU (16GB VRAM)
OS:                 Windows 11 Pro
Python:             3.11.14
faster-whisper:     1.2.1 (CTranslate2 backend)
pyannote.audio:     4.0.4 (workaround'larla)
torch:              2.8.0+cu128
torchaudio:         2.8.0+cu128
ffmpeg:             8.0.1-full_build
turkish-deasciifier: 0.1 (GitHub'dan)
zemberek-python:    0.2.3 (SpellChecker crash)
```

---

## Arastirilmasi Gereken Konular

### 1. Transkripsiyon Kalitesini Artirma

- `BatchedInferencePipeline` vs `sequential model.transcribe()` — hangisi gercek seste daha iyi?
  - Sequential: `condition_on_previous_text=True` ile baglam tasinir ama 2-3x yavas
  - Batched: Hizli ama baglamiz
  - Orta yol var mi? (ornegin buyuk batch'ler ile kismi baglam)

- `initial_prompt` — batched modda dogrulugu dusurdugu gozlemlendi ama sequential modda faydali
  - Gercek seste `initial_prompt` ne kadar etkili?
  - Prompt icerigi nasil optimize edilir?

- Whisper large-v3 vs large-v3-turbo — gercek Turkce seste hangisi daha dogru?

- Turkce'ye fine-tune edilmis modeller:
  - `selimc/whisper-large-v3-turbo-turkish` (WER %18.92 CV17)
  - `Sercan/distil-whisper-large-v3-tr` (WER %14.43)
  - Bunlar faster-whisper ile uyumlu mu? CTranslate2'ye convert edilebilir mi?

### 2. Diarization Kalitesini Artirma

- **SPEAKER_00/01 mapping sorunu nasil cozulur?**
  - Doktor sesi enrollment (onceden kaydet, embedding karsilastir)
  - Ilk konusanin doktor oldugu varsayimi
  - Kullanici arayuzunde "ilk konusan kim?" secimi

- **Overlapping speech nasil handle edilir?**
  - `speaker_diarization` (overlap dahil) vs `exclusive_speaker_diarization` (overlap yok)
  - Overlap bolgeleri icin ayri isleme yapilabilir mi?
  - Whisper overlap'ta nasil davranir? Arastirma bulgulari?

- **pyannote 4.0 vs 3.1 gercek performans karsilastirmasi**
  - 4.0'da VRAM bug (9.54GB) var mi hala?
  - 3.1'e donmek mantikli mi?
  - NeMo diarization alternatif mi?

- **Kelime bazli speaker atama dogruluğu nasil artirilir?**
  - Mevcut yontem: her kelime icin en cok ortüsen diarization turn'u
  - Daha iyi yontemler? (sliding window, smoothing, majority voting)

### 3. Post-Processing Iyilestirme

- **Zemberek SpellChecker duzeltilmeli** — numpy overflow sorunu nasil cozulur?
- **KenLM n-gram language model** — Turkce tibbi metin uzerinde egitilmis LM ile yeniden puanlama
- **SymSpell** — Hizli fuzzy matching ile yazim duzeltme
- **Hunspell Turkce** — Morfolojik kural bazli yazim kontrolu

### 4. Gercek Ortam Sorunlari

- **Mikrofon kalitesi** — laptop mic vs harici mikrofon ne kadar fark yapar?
- **Oda akustigi** — yanki, arka plan gurultusu
- **Konusma stili** — hizli konusma, mumbling, aksanlar
- **Ust uste konusma frekansi** — tipik doktor-hasta gorusmesinde ne kadar overlap var?

### 5. Alternatif Yaklasimlar

- **WhisperX** tekrar denenmeli mi? (daha once pyannote uyumsuzlugu nedeniyle birakılmisti)
- **Google Cloud Speech-to-Text** — Turkce destekliyor, karsilastirma baseline olarak
- **Azure Speech Services** — Custom Speech ile domain adaptasyonu
- **Ensemble yaklasim** — Whisper + wav2vec2 birlikte kullanma
- **LoRA fine-tuning** — ne kadar veri lazim? Sentetik veri yeterli mi?

---

## Kisitlamalar

- Fine-tuning su an icin planlanmiyor (veri hazirlama zamani yok)
- LLM post-correction gecikme eklediği icin istenmiyor
- Sequential mode 2-3x yavaslatiyor — kullanici istem¡yor
- Windows 11 + pyannote 4.0 uyumsuzluklari workaround gerektiriyor
- Mikrofon kalitesi kontrol edilemiyor (laptop mic kullaniliyor)

---

## Beklenen Cikti

1. **Gercek seste WER'i %15'in altina indirme yollari** (fine-tuning olmadan)
2. **Diarization dogrulugunu %80+ yapma yollari** (SPEAKER mapping dahil)
3. **Overlapping speech icin strateji**
4. **Post-processing pipeline iyilestirme** (Zemberek duzeltme, KenLM, vb.)
5. **Somut implementasyon plani** — hangi degisiklik, hangi sirada
6. **Turkce fine-tune modellerin faster-whisper ile kullanimi** mumkun mu?
