# ASR Sistemini Sifirdan Tasarlama - Arastirma Dokumani

## Problem Ozeti

Turkce klinik ASR uygulamasinda (doktor-hasta gorusmesi transkripsiyon) streaming yaklasimi denendi ve BASARISIZ oldu. Asagidaki problemler yasandi:

### Streaming Yaklasiminin Sorunlari

1. **FFmpeg pipe kilitleniyor**: Uzun kayitlarda (>1 dakika) FFmpeg subprocess pipe'i kilitlenip kirilyior. Windows'ta pipe buffer limiti (64KB) streaming yaklasim ile uyumsuz.

2. **LocalAgreement yavs**: ufal/whisper_streaming'in LocalAgreement algoritmasi her process_iter() cagrisinda TUM audio buffer'i yeniden transkribe ediyor. Buffer buyudukce islem suresi artiyor → gercek zamanli calisamiyor.

3. **Parcalanmis cikti**: Streaming transkripsiyon cok kucuk parcalar halinde metin uretiyor ("bazen bir sey" / "kaldirirken" / "boyle..." / "Bir gucsuzluk"). Cumleler bolunuyor, anlam kaybi oluyor.

4. **Dusuk dogruluk**: Streaming modda beam_size dusuk tutulmak zorunda (hiz icin) → dogruluk dusuyor. "kolumda" → "kulumda", "agriniz mi" → "haram mi" gibi hatalar cikiyor.

5. **Karmasik mimari**: FFmpeg pipe + VAD + LocalAgreement + post-processor + segment merger → cok katmanli, debug etmesi zor, kiriilgan bir yapi.

### Karar: "Once Kaydet, Sonra Isle" Modeline Donus

Streaming yaklasimi birakiliyor. Yeni hedef:
- Kayit sirasinda ses SADECE KAYDEDILSIN (basit, guvenilir)
- Kayit bittikten sonra yuksek kaliteli batch ASR uygulansin (hizli + dogru)
- Pipeline mumkun oldugunca hizli calissin (hedef: 1 dakikalik kayit icin <30 saniye islem)

---

## Sistem Bilgileri

```
GPU:                NVIDIA RTX 5080 Laptop GPU (16GB VRAM)
OS:                 Windows 11 Pro 10.0.26200
Python:             3.11.14 (miniconda3, conda env: asr)
Conda env path:     C:\Users\Huckleberry\miniconda3\envs\asr\
faster-whisper:     1.2.1 (CTranslate2 backend)
whisperx:           3.8.1
pyannote.audio:     4.0.4
torch:              2.8.0+cu128
torchaudio:         2.8.0+cu128
ffmpeg:             8.0.1-full_build (WinGet ile kurulu)
```

---

## Mevcut Proje Yapisi

```
KlinikAsistan/
├── apps/
│   ├── backend/
│   │   └── src/
│   │       ├── asr/                    # ASR pipeline (yeniden tasarlanacak)
│   │       │   ├── audio_utils.py      # FFmpeg donusturucu + AudioAccumulator
│   │       │   ├── diarizer.py         # pyannote konusmaci ayristirma
│   │       │   ├── gpu_manager.py      # GPU bellek yonetimi
│   │       │   ├── online_transcriber.py  # LocalAgreement (KALDIRILACAK)
│   │       │   ├── output_formatter.py # Segment formatlama
│   │       │   ├── pipeline.py         # Ana orkestrator (YENIDEN YAZILACAK)
│   │       │   ├── post_processor.py   # Turkce duzeltme
│   │       │   ├── segment_merger.py   # Segment birlestirme
│   │       │   ├── settings.py         # Yapilandirma
│   │       │   ├── exceptions.py       # Hata siniflari
│   │       │   └── vendor/
│   │       │       └── whisper_online.py  # (KALDIRILACAK)
│   │       ├── services/
│   │       │   ├── asr_service.py      # Async pipeline yonetici
│   │       │   ├── report_generator.py # Anamnez rapor uretimi (NER + LLM)
│   │       │   ├── ner_service.py      # Tibbi varlık cikarimi
│   │       │   └── llm_service.py      # LLM entegrasyonu
│   │       ├── ws/
│   │       │   └── audio_handler.py    # WebSocket handler
│   │       └── routes/
│   │           └── transcription.py    # WS endpoint
│   └── frontend/
│       └── src/renderer/src/
│           ├── hooks/useRecording.ts    # Kayit yonetimi
│           ├── services/audioCapture.ts # Mikrofon yakalama
│           ├── services/wsClient.ts     # WebSocket istemci
│           ├── pages/LiveSessionPage.tsx # Kayit sayfasi
│           └── pages/ReportReviewPage.tsx # Rapor inceleme
├── src/                                # ESKI ASR pipeline (dokunulmuyor)
├── config/
│   ├── settings.py                     # Genel yapilandirma
│   └── medical_terms.py               # Tibbi terim prompt'u
└── data/
    └── recordings/                     # WAV kayitlar
```

---

## Frontend Ses Yakalama Mekanizmasi

### audioCapture.ts
- Web Audio API ile mikrofon yakalama
- MediaRecorder ile 250ms aralikla WebM/Opus chunk'lar uretir
- Binary chunk'lari WebSocket uzerinden backend'e gonderir

### useRecording.ts
- Kayit durumu yonetimi: idle → recording → paused → processing
- WebSocket baglantisi kurma/kapatma
- Timer ve audio level gosterimi

### WebSocket Protokolu
```
Frontend → Backend:
  - Binary: WebM/Opus audio chunk'lar (250ms aralikla)
  - JSON: {type: "stop"} kayit durdurma
  - JSON: {type: "resume"} devam ettirme

Backend → Frontend:
  - JSON: {type: "interim_transcript", text, is_partial, sequence_id}
  - JSON: {type: "processing_start", message}
  - JSON: {type: "progress", stage, message, progress}
  - JSON: {type: "result", session_id, segments, full_text, metadata}
  - JSON: {type: "report_ready", report_id}
  - JSON: {type: "error", message, code}
```

---

## Backend Ses Isleme Mekanizmasi

### audio_handler.py
- WebSocket handler: chunk'lari alir, biriktirir
- `_handle_audio_chunk()`: Her chunk icin ASR service'i cagiriyordu (streaming modda)
- `_process_recording()`: Kayit durdurulunca batch isleme baslatir
- `_save_segments()`: Transkripsiyon sonuclarini DB'ye kaydeder
- `_auto_generate_report()`: Anamnez raporu otomatik olusturur

### audio_utils.py
- `AudioChunkConverter`: FFmpeg subprocess ile WebM → PCM donusumu (streaming icin, PROBLEMLI)
- `AudioAccumulator`: PCM chunk'lari biriktirir, WAV olarak kaydeder
- `load_and_validate_audio()`: Ses dosyasi dogrulama

### pipeline.py (mevcut - streaming + finalize)
- `start_streaming()`: Streaming modelleri yukle
- `process_audio_chunk()`: Her chunk icin transkripsiyon (PROBLEMLI)
- `stop_streaming()`: WAV kaydet, modelleri bosalt
- `finalize()`: Diarization + speaker atama

### asr_service.py
- Async singleton wrapper
- GPU detection + CPU fallback
- Process lock (tek seferde bir islem)

---

## Veritabani Semasi

### TranscriptionSegment tablosu
```sql
session_id      INTEGER     -- Oturum ID
segment_index   INTEGER     -- Segment sirasi
text            TEXT        -- Transkribe edilmis metin
speaker         TEXT        -- "SPEAKER_00", "SPEAKER_01"
speaker_label   TEXT        -- "Doktor", "Hasta"
start_time      REAL        -- Baslangic (saniye)
end_time        REAL        -- Bitis (saniye)
confidence      REAL        -- Guven skoru (nullable)
words_json      TEXT        -- Kelime seviyesi timing (JSON)
is_edited       BOOLEAN     -- Kullanici tarafindan duzenlendi mi
```

### Session tablosu
```sql
id              INTEGER     -- Primary key
status          TEXT        -- NOT_STARTED, RECORDING, PROCESSING, AWAITING_REVIEW
audio_file_path TEXT        -- WAV dosya yolu
audio_duration  REAL        -- Ses suresi (saniye)
doctor_name     TEXT        -- Doktor adi
patient_name    TEXT        -- Hasta adi
```

---

## Istenen Yeni Mimari

### Temel Prensip
```
KAYIT SIRASINDA:
  Frontend → WebSocket → Backend
    → Chunk'lar SADECE BIRIKTIRILIR (hicbir ASR islemi yapilmaz)
    → Ham ses verisi kaydedilir

KAYIT SONRASI:
  → WebM → WAV donusumu (FFmpeg, tek seferde, guvenilir)
  → ASR Pipeline (hizli + dogru):
    1. Transkripsiyon (faster-whisper large-v3)
    2. Kelime hizalama (opsiyonel)
    3. Konusmaci ayristirma (pyannote)
    4. Post-processing (Turkce duzeltme)
    5. Rapor olusturma (NER + LLM)
```

### Performans Hedefleri

| Metrik | Hedef | Aciklama |
|--------|-------|----------|
| 1 dakikalik kayit isleme | <30 saniye | Toplam pipeline suresi |
| 5 dakikalik kayit isleme | <2 dakika | Olceklenebilirlik |
| WER (genel Turkce) | <%15 | Whisper large-v3 zero-shot |
| WER (tibbi Turkce) | <%20 | Tibbi terminoloji daha zor |
| Diarization DER | <%15 | 2 konusmaci (Doktor/Hasta) |

### Hiz Icin Kritik Parametreler (Arastirilacak)

faster-whisper large-v3 RTX 5080'de cok hizli (RTF ~0.04). Toplam pipeline suresini azaltmak icin:

1. **batch_size**: Whisper'in batch_size parametresi (WhisperX'te). Buyuk batch = daha hizli.
2. **compute_type**: float16 vs int8_float16 vs int8. int8 %20 daha yavas ama daha az VRAM.
3. **beam_size**: 1 (greedy) vs 5 (beam search). beam=1 ~3x daha hizli ama WER daha yuksek.
4. **VAD filter**: Sessiz bolumleri atlayarak toplam isleme suresini %40-60 azaltir.
5. **Paralel pipeline**: Transkripsiyon + diarization paralel calisabilir mi?

---

## Yasanan Teknik Problemler (Cozum Bekliyor)

### 1. pyannote.audio 4.0 + Windows Uyumsuzluklari

**torchcodec DLL sorunu**: pyannote 4.0 ses dosyalarini torchcodec ile okumaya calisiyor ama Windows'ta DLL'ler bulunamiyor. Cozum: `torchaudio.load()` ile in-memory waveform dict gecmek.

```python
# CALISAN cozum:
waveform, sample_rate = torchaudio.load(audio_path)
diarization = pipeline({"waveform": waveform, "sample_rate": sample_rate}, num_speakers=2)
```

**DiarizeOutput wrapper**: pyannote 4.0 `DiarizeOutput` objesi dondurur, eski API `Annotation` bekler. `exclusive_speaker_diarization` attribute'u kullanilmali.

### 2. WhisperX + pyannote 4.0 Uyumsuzlugu

`whisperx.assign_word_speakers()` pandas DataFrame bekliyor, pyannote Annotation objesi donduruyor. Annotation → DataFrame donusumu gerekli:

```python
diarize_df = pd.DataFrame(
    [{"start": seg.start, "end": seg.end, "speaker": spk}
     for seg, _, spk in annotation.itertracks(yield_label=True)],
    columns=["start", "end", "speaker"]
)
```

### 3. Turkce Morfoloji Hatalari

Whisper'in Turkce'ye ozgu hatalari:
- Sesli harf karisikliklari: kolumda → kulumda (o/u)
- Ek dusmeleri: hissediyorum → hissediyor (-um dusmus)
- Tam kelime yanlis tanima: agriniz mi → haram mi

Zemberek morfolojik analiz denendi ama `kulumda` da gecerli Turkce oldugu icin cozum olmadi. SpellChecker numpy uyumsuzlugu nedeniyle crash ediyor.

### 4. FFmpeg Pipe Deadlock (Windows)

FFmpeg subprocess pipe'lari Windows'ta 64KB buffer limitine sahip. Uzun kayitlarda pipe dolup kilitleniyor. Streaming yaklasimi icin temel engel.

---

## Arastirilmasi Gereken Konular

### 1. En Hizli Batch ASR Pipeline Nasil Kurulur?

faster-whisper ile:
- `model.transcribe(audio, language="tr", beam_size=5, batch_size=16, word_timestamps=True, vad_filter=True)`
- RTX 5080 16GB'de large-v3 float16 ile 1 dakikalik ses kac saniyede islenir?
- batch_size'in etkisi nedir? (WhisperX'in batch modu vs faster-whisper'in kendi batch modu)
- VAD filter ile sessiz bolumler atlaninca ne kadar hiz kazanilir?

### 2. WhisperX mi, Saf faster-whisper mi?

WhisperX ek ozellikler sunar:
- Batch transkripsiyon (batch_size ile)
- wav2vec2 kelime hizalama
- Konusmaci ayristirma (pyannote wrapper)

Ama dezavantajlari var:
- pyannote 4.0 ile uyumsuzluk (duzeltildi ama kirilgan)
- Ekstra bagimlilik
- wav2vec2 alignment gereksiz olabilir (faster-whisper word_timestamps=True yeterli mi?)

Soru: faster-whisper'i dogrudan kullanmak (WhisperX olmadan) daha basit ve guvenilir olur mu?

### 3. Paralel Pipeline Mumkun mu?

ASR ve diarization paralel calisabilir mi?
```
Audio → [ASR thread] → transkript
      → [Diarization thread] → konusmaci segmentleri
      → [Merge] → konusmaci etiketli transkript
```

Bu yaklasim toplam sureyi onemli olcude azaltabilir.

### 4. Diarization Hizi Nasil Arttirilir?

pyannote 4.0 ile diarization suresi:
- 1 dakikalik ses: ~30-60 saniye (cok yavas!)
- Daha hizli alternatifler var mi?
- pyannote parametreleri ile hiz optimize edilebilir mi?
- NeMo diarization daha hizli mi?

### 5. Turkce Dogruluk Nasil Arttirilir? (Fine-tuning Olmadan)

- `initial_prompt`: Turkce tibbi terimler ile decoder'i yonlendirme
- `hotwords`: faster-whisper'in hotword boosting ozelligi
- `temperature=0.0`: Deterministic cikti
- Post-processing: deASCIIfication + tibbi terim sozlugu
- Sesli harf uyumu kurallari ile otomatik duzeltme

### 6. Frontend Deneyimi

Kayit sirasinda ASR yapilmadigi icin:
- Kullanici kayit sirasinda bos ekran gorur (transkript yok)
- Bunun yerine ne gosterilebilir? (ses dalga formu, ses seviyesi, kayit suresi)
- Kullanici deneyimini iyilestirmenin yollari neler?
- Kayit sonrasi isleme suresi progress bar ile gosterilebilir (zaten var)

### 7. Ses Kalitesi ve On-Isleme

- WebM/Opus codec'i kalite kaybi yapiyor mu?
- Daha iyi bir codec secenegi var mi? (PCM/WAV dogrudan?)
- Ses normalizasyonu (volume normalization) dogrulugu arttirir mi?
- Mikrofon kalitesi onemli mi? (laptop mic vs harici mikrofon)
- Gurultu bastirma (DeepFilterNet) ZARAR MI VERIYOR? (arastirma: evet, Whisper icin zarar)

### 8. Basit ve Guvenilir Ses Kayit Mekanizmasi

Mevcut sistem WebSocket uzerinden WebM chunk gonderiyor. Alternatifler:
- Frontend'de tum sesi biriktirip tek dosya olarak gonderme (daha basit)
- MediaRecorder yerine AudioWorklet ile ham PCM gonderme
- Kayit bitince dosyayi HTTP POST ile yukleme (WebSocket yerine)

Hangi yaklasim en guvenilir ve basit?

---

## Mevcut Calisan Bilesenler (Korunacak)

1. **Diarization**: pyannote 4.0 ile calisiyor (torchaudio workaround + DataFrame donusumu + exclusive_speaker_diarization)
2. **Rapor uretimi**: NER + LLM ile anamnez raporu (report_generator.py)
3. **Frontend**: Kayit kontrolleri, progress gosterimi, rapor inceleme sayfasi
4. **Veritabani**: Session + TranscriptionSegment + Report tablolari
5. **Turkce post-processing**: deASCIIfication + tibbi terim sozlugu

---

## Kisitlamalar

- **LLM kullanilamaz** transkripsiyon duzeltme icin (gecikme ekler)
- **Fine-tuning yapilamaz** su an icin (veri hazirlama zamani yok)
- **Windows 11** uzerinde calismali
- **RTX 5080 16GB** GPU mevcut
- **Turkce tibbi terminoloji** desteklenmeli (code-switching: Turkce + Latince tibbi terimler)
- **2 konusmaci**: Doktor ve Hasta

---

## Beklenen Cikti

1. **En iyi batch ASR pipeline mimarisi** (faster-whisper mi, WhisperX mi, baska mi?)
2. **Optimal parametreler** (beam_size, batch_size, compute_type, vad parametreleri)
3. **Pipeline adimlari ve siralama** (paralel mi seri mi?)
4. **Tahmini islem sureleri** (1dk, 5dk, 10dk ses icin)
5. **Turkce dogruluk iyilestirme yontemleri** (fine-tuning olmadan)
6. **Frontend deneyimi onerileri** (kayit sirasinda ne gosterilir?)
7. **Basit ve guvenilir ses kayit mekanizmasi** onerisi
8. **Somut implementasyon plani** (adim adim)
