# Feature Branch Raporu: feature/hybrid-asr-pipeline

## Genel Bakis

Bu branch'te KlinikAsistan uygulamasinin ASR (Automatic Speech Recognition) sistemi sifirdan yeniden tasarlandi. Eski WhisperX tabanli pipeline yerine faster-whisper + pyannote tabanli yeni bir batch ASR pipeline olusturuldu. Calisma 4-7 Nisan 2026 tarihlerinde gerceklestirildi.

**Branch**: `feature/hybrid-asr-pipeline`
**Merge**: `master` branch'ina merge edildi (commit: 1f04f5b)
**Degisiklik**: 29 dosya, +4,933 satir, -334 satir

---

## Kronolojik Gelisim Sureci

### Faz 1: Hibrit Streaming + Batch Mimari (Ilk Tasarim)

Ilk plan Whisper large-v3 ile hibrit bir mimari kurmakti:
- Kayit sirasinda: Streaming ASR (canli transkripsiyon)
- Kayit sonrasi: Batch ASR (yuksek kaliteli)

Bu faz icin yazilan bilesenler:
- `StreamingTranscriber` — faster-whisper ile VAD tabanli streaming
- `SileroVAD` — torch.hub VADIterator ile gercek zamanli konusma algilama
- `AudioChunkConverter` — FFmpeg pipe ile WebM→PCM donusumu
- `OnlineTranscriber` — ufal/whisper_streaming LocalAgreement entegrasyonu
- `SegmentMerger` — Kisa streaming parcalarini cumle seviyesinde birlestirme
- Frontend `InterimTranscriptView` — Canli transkript gosterimi
- Frontend `interimStore` — Zustand store interim metin yonetimi

### Faz 2: Streaming Problemleri ve Basarisizlik

Streaming yaklasimi su sorunlarla karsilasti:

1. **FFmpeg pipe kilitleniyor**: Windows'ta 64KB pipe buffer limiti nedeniyle 1dk+ kayitlarda subprocess pipe'i dolup kilitlendi
2. **LocalAgreement cok yavas**: Her process_iter() cagrisi TUM audio buffer'i yeniden transkribe ediyordu. Buffer buyudukce islem suresi artti
3. **Parcalanmis cikti**: Streaming transkripsiyon cok kucuk parcalar halinde metin uretti ("bazen bir sey" / "kaldirirken" / "boyle...")
4. **Dusuk dogruluk**: Streaming modda beam_size dusuk tutulmak zorundaydi
5. **Karmasik mimari**: FFmpeg pipe + VAD + LocalAgreement + post-processor + segment merger → cok katmanli, kirilgan yapi

### Faz 3: Batch-Only Mimariye Gecis

Streaming yaklasimi terk edildi. "Once kaydet, sonra isle" modeline gecildi:
- Kayit sirasinda: Ses SADECE biriktirilir (ASR islemi yok)
- Kayit sonrasi: Yuksek kaliteli batch ASR uygulanir

### Faz 4: Dogruluk Optimizasyonu

Model ve parametre karsilastirmalari yapildi:
- `BatchedInferencePipeline` vs `sequential model.transcribe()`
- `large-v3` vs `large-v3-turbo` vs fine-tuned modeller
- `initial_prompt` + `condition_on_previous_text` etkileri

---

## Olusturulan Dosyalar (Backend)

### apps/backend/src/asr/__init__.py
- `BatchASRPipeline` ve `ASRSettings` icin lazy import
- Agir bagimliliklari yuklemeden public API saglar

### apps/backend/src/asr/pipeline.py — Ana Orkestrator
**BatchASRPipeline** sinifi — tek giris noktasi: `process(wav_path, progress_callback)`

Pipeline adimlari:
1. Stage 0: Ses dosyasi dogrulama
2. Stage 1: Transkripsiyon — `faster-whisper sequential model.transcribe()`
   - Model: large-v3-turbo, float16
   - beam_size=5, temperature=0.0
   - condition_on_previous_text=True (baglam tasima)
   - initial_prompt ile tibbi terim priming
   - prompt_reset_on_temperature=0.5 (halusinasyon onleme)
   - vad_filter=True (sessizlik filtreleme)
3. Stage 2: Turkce post-processing (deASCIIfication + Zemberek + sozluk)
4. Stage 3: pyannote diarization + kelime bazli speaker atama
5. Stage 4: Format + metadata

GPU yonetimi: Whisper → unload → pyannote → unload (sirayla, asla ayni anda degil)

### apps/backend/src/asr/settings.py — Yapilandirma
- `BatchTranscriptionSettings`: model_name, compute_type, beam_size, hotwords, vb.
- `DiarizationSettings`: pyannote model, num_speakers=2, default_labels
- `GPUSettings`: target_gpu, max_vram
- `AudioSettings`: sample_rate=16000, max_recording_duration
- `ASRSettings`: Tum alt gruplari birlestirir, .env'den yuklenir (prefix: ASR_V2_)

### apps/backend/src/asr/diarizer.py — Konusmaci Ayristirma
**SpeakerDiarizer** sinifi:

pyannote 4.0.4 workaround'lari:
- `torchaudio.load()` ile in-memory waveform dict (torchcodec DLL sorunu)
- `exclusive_speaker_diarization` (ortusme olmayan cikti)
- `token=` parametresi (eski `use_auth_token` kaldirildi)

Kelime bazli speaker atama (`assign_speakers_by_time`):
- Her kelimeye diarization turn'lerinden en cok ortüsen speaker atanir
- Speaker degistiginde segment bolunur
- Ornek: 4 Whisper segmenti → 20 speaker-ayrimli segmente donusur

### apps/backend/src/asr/post_processor.py — Turkce Duzeltme
**TurkishPostProcessor** sinifi — 3 katmanli:

1. **DeASCIIfication**: `turkish-deasciifier` ile ASCII→Turkce karakter donusumu
2. **Zemberek morfolojik analiz**: Gecersiz kelimeleri tespit et (loglama modu)
3. **Statik tibbi terim sozlugu**: Bilinen Whisper hatalarini duzelt

Icerir:
- `MEDICAL_CORRECTIONS` dict: "kulumda"→"kolumda", "haram mi"→"agriniz mi" vb.
- `MEDICAL_WHITELIST` set: Latince tibbi terimler Zemberek'ten korunur

### apps/backend/src/asr/audio_utils.py — Ses Isleme
**AudioAccumulator** sinifi:
- Frontend'den gelen WebM/Opus chunk'lari biriktirir
- Kayit bitince FFmpeg ile tek seferde WAV'a donusturur (16kHz mono PCM)
- Max 60 dakika kayit limiti

`load_and_validate_audio()`: Ses dosyasi dogrulama + sure hesaplama

### apps/backend/src/asr/gpu_manager.py — GPU Yonetimi
**ASRGPUManager** sinifi:
- Mod tabanli GPU bellek yonetimi (transcription ↔ diarization)
- Thread-safe model registry
- VRAM izleme ve otomatik temizlik (gc + torch.cuda.empty_cache)
- Dusuk VRAM uyarisi (<2GB kaldığinda force temizlik)

### apps/backend/src/asr/output_formatter.py — Segment Formatlama
- `SegmentOutput` TypedDict: text, speaker, speaker_label, start, end, words
- `format_segments()`: WhisperX/Whisper ciktisini DB-uyumlu formata donustur
- `build_metadata()`: Pipeline metadata dict olustur

### apps/backend/src/asr/exceptions.py — Hata Hiyerarsisi
- `ASRError` (temel)
- `BatchProcessingError`, `DiarizationError`
- `AudioConversionError`, `AudioValidationError`
- `GPUMemoryError`

---

## Degistirilen Dosyalar (Backend)

### apps/backend/src/services/asr_service.py
Tamamen yeniden yazildi:
- Eski: `start_streaming()`, `process_chunk()`, `stop_and_batch()`
- Yeni: `process_recording(wav_path, progress_cb)` — tek giris noktasi
- Singleton pattern korundu (`asr_service = ASRService()`)
- GPU detection + CPU fallback korundu
- `_process_lock` ile tek seferde bir islem garantisi

### apps/backend/src/ws/audio_handler.py
Tamamen yeniden yazildi:
- Eski: Streaming chunk isleme + interim transcript gonderme + batch finalize
- Yeni: Sadece chunk biriktir → stop'ta batch isle

Yeni akis:
1. WS baglantisi acilir
2. Binary chunk'lar gelir → `accumulator.add_raw()` (sadece biriktir)
3. `{type: "stop"}` gelir → `_process_recording()`:
   - WebM → WAV donusumu (FFmpeg, tek sefer)
   - Batch ASR pipeline calistir
   - Segment'leri DB'ye kaydet
   - Rapor olustur
   - Sonucu frontend'e gonder

WS race condition duzeltmesi:
- Stale baglanti varsa reject yerine replace (eski baglantiyi kapat, yenisini kabul et)
- `get_active_websocket()` helper fonksiyonu eklendi

### apps/backend/src/routes/transcription.py
- Stale WS connection replacement stratejisi
- `RECORDING` status race condition duzeltmesi
- `get_active_websocket` import eklendi

### apps/backend/src/routes/health.py
- `streaming_available` ve `asr_mode` alanlari kaldirildi
- `asr_pipeline_ready` kontrolu `asr_service.is_ready` ile degistirildi
- Versiyon 2.0.0'a guncellendi

### apps/backend/requirements.txt
- `pydantic-settings>=2.0.0` eklendi
- Opsiyonel bagimliliklar dokumante edildi (turkish-deasciifier, zemberek-python)

---

## Degistirilen Dosyalar (Frontend)

### apps/frontend/src/renderer/src/hooks/useRecording.ts
- `useInterimStore` import ve kullanimi kaldirildi
- `interim_transcript` WS handler kaldirildi
- `processing_start` handler basitlestirildi
- Resume'da VAD reset mesaji kaldirildi
- Stop'ta interim clear kaldirildi
- 50ms cleanup yield eklendi (WS race condition icin)
- WS stale entry kontrolu eklendi

### apps/frontend/src/renderer/src/pages/LiveSessionPage.tsx
- `useInterimStore` kaldirildi
- Interim transcript gorunumu kaldirildi
- Bilgi banner guncellendi: "Kayit devam ediyor. Durdurunca transkripsiyon baslayacak."
- Stage label'lari batch pipeline icin guncellendi (4 asama)
- TranscriptView'dan interim props kaldirildi

### apps/frontend/src/renderer/src/pages/SessionHistoryPage.tsx
- Gecmis sayfasina gorusme silme (arsivleme) butonu eklendi
- `Trash2` ikonu, `useQueryClient` hook, `handleDelete` callback
- Grid layout'a aksiyon sutunu eklendi
- Onay dialogu (confirm) ile guvenli silme

### apps/frontend/src/renderer/src/pages/DashboardPage.tsx
- Ana sayfaya gorusme silme butonu eklendi
- `handleDelete` callback, `useQueryClient` hook
- SessionCard'a `onDelete` ve `isDeleting` props gecildi

### apps/frontend/src/renderer/src/components/dashboard/SessionCard.tsx
- `onDelete` ve `isDeleting` props eklendi
- Trash2 ikonu ile silme butonu (loading state destekli)
- `e.stopPropagation()` ile satir tiklamasini engelleme

### apps/frontend/src/renderer/src/components/session/TranscriptView.tsx
- `interimLines` ve `currentPartial` props kaldirildi
- `InterimTranscriptView` import kaldirildi
- Sadece final segment'leri gosterir

### apps/frontend/src/renderer/src/services/wsClient.ts
- Stale entry kontrolu: `existing.isConnected` kontrol edilir, stale ise kaldirilir
- Erken kayit: `_activeClients.set()` connect() basinda yapilir (onopen'da degil)

### apps/frontend/src/renderer/src/types/transcription.ts
- Dead types kaldirildi: `InterimTranscriptLine`, `WSInterimTranscript`
- `WSProcessingStart` sadeleştirildi (`streaming_segments_count` kaldirildi)
- `WSMessage` union temizlendi

---

## Silinen Dosyalar

### Backend
- `apps/backend/src/asr/online_transcriber.py` — LocalAgreement streaming wrapper
- `apps/backend/src/asr/segment_merger.py` — Streaming fragment birlestirici
- `apps/backend/src/asr/vendor/whisper_online.py` — ufal/whisper_streaming fork
- `apps/backend/src/asr/vendor/__init__.py` — vendor dizini

### Frontend
- `apps/frontend/src/renderer/src/stores/interimStore.ts` — Interim transcript Zustand store
- `apps/frontend/src/renderer/src/components/session/InterimTranscriptView.tsx` — Canli transkript UI

---

## Olusturulan Dokumanlar

| Dosya | Icerik |
|-------|--------|
| `docs/diarization-debug-report.md` | pyannote AudioDecoder hatasi arastirmasi |
| `docs/diarization-debug-report-v2.md` | WhisperX + pyannote 4.0 uyumsuzlugu (iterrows hatasi) |
| `docs/streaming-only-asr-arastirma.md` | Streaming-only mimari arastirmasi |
| `docs/whisper-turkish-accuracy-report.md` | Whisper Turkce dogruluk sorunlari |
| `docs/asr-sifirdan-tasarim-raporu.md` | ASR sifirdan tasarim plani |
| `docs/asr-performans-iyilestirme-raporu.md` | Performans iyilestirme arastirmasi |
| `docs/llm-dual-mode-dokumantasyon.md` | LLM dual-mode dokumantasyonu |
| `docs/llm-pipeline-dokumantasyon.md` | LLM pipeline dokumantasyonu |

---

## Yasanan Teknik Problemler ve Cozumleri

### 1. React StrictMode WS Race Condition
**Problem**: React StrictMode double-mount ile iki WS baglantisi aciliyor, ikincisi reddediliyor.
**Cozum**: Backend'de reject→replace stratejisi. Frontend'de stale entry kontrolu + 50ms cleanup yield.

### 2. pyannote 4.0 torchcodec DLL Sorunu
**Problem**: `AudioDecoder is not defined` — torchcodec DLL'leri Windows'ta bulunamiyor.
**Cozum**: `torchaudio.load()` ile in-memory waveform dict gecme (pyannote resmi workaround).

### 3. pyannote 4.0 DiarizeOutput Wrapper
**Problem**: pyannote 4.0 `DiarizeOutput` donduruyor, WhisperX `Annotation` bekliyor.
**Cozum**: `result.exclusive_speaker_diarization` ile Annotation cikarma.

### 4. WhisperX assign_word_speakers DataFrame Hatasi
**Problem**: `'Annotation' object has no attribute 'iterrows'` — WhisperX pandas DataFrame bekliyor.
**Cozum**: Annotation→DataFrame donusumu (itertracks ile). Sonra tamamen kendi speaker assignment yazildi.

### 5. pyannote use_auth_token Parametresi
**Problem**: pyannote 4.0'da `use_auth_token` kaldirilmis.
**Cozum**: `token=` parametresine gecis.

### 6. FFmpeg Pipe Deadlock (Windows)
**Problem**: Streaming modda FFmpeg pipe 1dk+ kayitlarda kilitlendi (64KB buffer).
**Cozum**: Streaming yaklasimi terk edildi. Batch modda tek seferde donusum.

### 7. BatchedInferencePipeline Baglam Kaybi
**Problem**: `condition_on_previous_text=False` hardcoded — her segment bagimsiz.
**Cozum**: Sequential `model.transcribe()` ile gecis (condition_on_previous_text=True).

### 8. Token Overflow (448 limit)
**Problem**: initial_prompt + hotwords + previous_text birlikte 448 token limitini asiyor.
**Cozum**: Kisa initial_prompt (~30 token) + prompt_reset_on_temperature=0.5.

### 9. Python __pycache__ Sorunu
**Problem**: Uvicorn --reload Windows'ta eski bytecode kullaniyor.
**Cozum**: Her restart'ta __pycache__ temizleme.

### 10. SPEAKER_00/01 Ters Mapping
**Problem**: pyannote SPEAKER_00'i rastgele atiyor — sabit mapping her zaman dogru degil.
**Durum**: Bilinen sinirlilik. Cozum icin speaker enrollment planlanıyor.

---

## Model Karsilastirma Testleri

### FLEURS Turkce Gercek Ses (5dk, normalized WER)

| Model | Mod | WER | Sure |
|-------|-----|-----|------|
| large-v3 | Batched | 21.6% | 6.1s |
| large-v3-turbo | Batched | 20.9% | 3.0s |
| erdiyalcin/large-v3-turkish | Batched | 29.6% | 5.9s |
| Sercan/distil-large-v3-tr | Batched | 24.2% | 2.6s |
| **large-v3-turbo** | **Sequential** | **18.3%** | **7.7s** |
| large-v3 | Sequential | 20.9% | 24.6s |

**Kazanan**: large-v3-turbo + sequential mode (WER %18.3, 7.7s)

### gTTS Sentetik Tibbi Diyalog (normalized WER)

| Test | WER |
|------|-----|
| Kardiyoloji | 10.8% |
| Ortopedi | 8.1% |
| Ortalama | ~10% |

### Diarization Testi (Edge-TTS 2 konusmaci)

| Metrik | Deger |
|--------|-------|
| Segment bolme | 20/20 (mukemmel) |
| Speaker dogrulugu | %100 (ters mapping duzeltildikten sonra) |

---

## Kurulu Ek Bagimliliklar

| Paket | Amac | Kurulum |
|-------|------|---------|
| `turkish-deasciifier` | ASCII→Turkce karakter donusumu | `pip install git+https://github.com/emres/turkish-deasciifier.git` |
| `zemberek-python` | Turkce morfolojik analiz | `pip install zemberek-python` |
| `symspellpy` | Hizli fuzzy matching | `pip install symspellpy` |
| `edge-tts` | Test ses dosyasi olusturma | `pip install edge-tts` |
| `librosa` | Ses isleme | `pip install librosa` |
| `pydantic-settings` | Yapilandirma yonetimi | `pip install pydantic-settings` |

---

## Dokunulmayan Dosyalar

CLAUDE.md kurallarina uygun olarak su dosyalar DEGISTIRILMEDI:
- `src/` dizini (eski ASR pipeline)
- `config/settings.py` (eski yapilandirma)
- `config/medical_terms.py` (ilk degistirildi, push oncesi revert edildi)
- Veritabani semasi (TranscriptionSegment, Session tablolari)
- Report generation (report_generator.py, ner_service.py, llm_service.py)

---

## Bilinen Sinirliliklar

1. **Gercek seste WER ~%18-20**: Sentetik seste %8-12, gercek seste daha yuksek
2. **SPEAKER mapping rastgele**: pyannote hangi konusmacinin doktor oldugunu bilmiyor
3. **Ust uste konusma (overlap)**: Whisper tek konusmaci icin tasarlanmis
4. **Zemberek SpellChecker crash**: numpy int8 overflow — sadece loglama modu
5. **Post-processing sinirli**: Baglama bagimli duzeltme yapamiyor
6. **Sequential mod 2-3x yavas**: Batched'a gore (ama dogruluk daha yuksek)

---

## Gelecek Iyilestirmeler (Planlanıyor)

1. **LoRA fine-tuning**: Turkce tibbi ses verisi ile model egitimi (%20-52 WER azalmasi)
2. **Speaker enrollment**: Doktor sesi onceden kaydedilip cosine similarity ile eslestirme
3. **KenLM n-gram rescoring**: Turkce tibbi metin uzerinde egitilmis dil modeli
4. **Hunspell Turkce**: Morfolojik kural bazli yazim kontrolu
5. **Mikrofon iyilestirme**: USB headset ile %20-40 WER azalmasi
6. **pyannote 3.3.x downgrade**: VRAM bug duzeltmesi (9.54GB→1.59GB)
