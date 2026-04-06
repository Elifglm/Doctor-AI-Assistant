# Diarization Hatasi v2 - WhisperX + pyannote 4.0 Uyumsuzlugu

## Problem Ozeti

Turkce klinik ASR uygulamasinda speaker diarization **kismen calisiyor**:
- pyannote pipeline YUKLENIYOR (token fix OK)
- pyannote `diarize()` CALISIYOR (waveform dict fix OK)
- Ama `whisperx.assign_word_speakers()` PATLIYOR

**Guncel hata:**
```
Konusmaci atama hatasi: 'Annotation' object has no attribute 'iterrows', varsayilan kullaniliyor
```

Bu hata, WhisperX 3.8.1'in pyannote ciktisini pandas DataFrame olarak islemesinden kaynaklaniyor. pyannote 4.0'dan donen `Annotation` objesi `iterrows()` metoduna sahip degil (bu pandas metodu).

---

## Onceki Hatalar (Cozuldu)

### Hata 1: `use_auth_token` (COZULDU)
```
Pipeline.from_pretrained() got an unexpected keyword argument 'use_auth_token'
```
Cozum: `use_auth_token=` -> `token=` olarak degistirildi.

### Hata 2: `AudioDecoder is not defined` (COZULDU)
```
Diarization hatasi: name 'AudioDecoder' is not defined
```
Cozum: Dosya yolu yerine in-memory waveform dict gecildi:
```python
waveform, sample_rate = torchaudio.load(audio_path)
result = self._pipeline({"waveform": waveform, "sample_rate": sample_rate}, ...)
```

### Hata 3: `DiarizeOutput` wrapper (COZULDU)
pyannote 4.0 `DiarizeOutput` objesi dondurur, WhisperX `Annotation` bekler.
Cozum: `result.speaker_diarization` ile Annotation cikarildi.

### Hata 4: `iterrows` (AKTIF PROBLEM)
```
'Annotation' object has no attribute 'iterrows'
```
WhisperX'in `assign_word_speakers()` fonksiyonu pyannote ciktisini pandas DataFrame'e cevirmesi gerekiyor ama bunu yapamıyor.

---

## Sistem Bilgileri

```
Python:             3.11.14
pyannote.audio:     4.0.4
whisperx:           3.8.1
torch:              2.8.0+cu128
torchaudio:         2.8.0+cu128
faster-whisper:     1.2.1
GPU:                NVIDIA RTX 5080 Laptop GPU
OS:                 Windows 11 Pro
```

---

## Pipeline Akisi (Kayit Sonrasi)

```
Kayit Durdur
  |
  v
Stage 0/5: Ses dosyasi dogrulama (format, boyut, sure)
  |
  v
Stage 1/5: DeepFilterNet3 gurultu bastirma
            (hastane ortam sesi temizleme, 48kHz islem)
  |
  v
Stage 2/5: faster-whisper large-v3 transkripsiyon
            (beam=5, batch_size=16, Turkce tibbi terim prompt)
            Cikti: {"segments": [{"text": "...", "start": 0.5, "end": 2.3}, ...]}
  |
  v
Stage 3/5: WhisperX wav2vec2 kelime hizalama
            (wav2vec2-xls-r-300m-cv7-turkish modeli)
            Cikti: Her kelimeye start/end zaman damgasi eklenir
  |
  v
Stage 4/5: Konusmaci ayristirma (2 adim)
            Adim 1: pyannote diarize() -> Kim ne zaman konustu
            Adim 2: whisperx.assign_word_speakers() -> Kelimelere konusmaci ata
            << ADIM 2'DE PATLIYOR >>
  |
  v
Stage 5/5: Rapor olusturma (NER + LLM)
            Segment'ler DB'ye kaydedilir
            Anamnez raporu otomatik olusturulur
```

---

## Sorunlu Kod Akisi

### 1. Pipeline orkestrator cagirisi
Dosya: `apps/backend/src/asr/pipeline.py` (satir 490-507)
```python
async def _run_diarization(self, wav_path, aligned_result):
    diarizer = SpeakerDiarizer(settings, hf_token, gpu_manager)
    
    await asyncio.to_thread(diarizer.load_model)        # OK
    diarization = await asyncio.to_thread(
        diarizer.diarize, wav_path                       # OK (waveform dict fix)
    )
    result = await asyncio.to_thread(
        diarizer.assign_speakers, diarization, aligned_result  # << PATLIYOR
    )
    await asyncio.to_thread(diarizer.unload)
    return result
```

### 2. diarize() metodu (CALISIYOR)
Dosya: `apps/backend/src/asr/diarizer.py` (satir 78-111)
```python
def diarize(self, audio_path: str) -> Any:
    import torchaudio
    waveform, sample_rate = torchaudio.load(audio_path)
    
    result = self._pipeline(
        {"waveform": waveform, "sample_rate": sample_rate},
        num_speakers=2, min_speakers=2, max_speakers=2,
    )
    
    # pyannote 4.0 DiarizeOutput wrapper -> Annotation cikar
    if hasattr(result, "speaker_diarization"):
        diarization = result.speaker_diarization
    else:
        diarization = result
    
    return diarization  # pyannote.core.annotation.Annotation objesi
```

### 3. assign_speakers() metodu (PATLIYOR)
Dosya: `apps/backend/src/asr/diarizer.py` (satir 113-148)
```python
def assign_speakers(self, diarization_result, aligned_result):
    if diarization_result is None:
        return self._assign_default_labels(aligned_result)
    
    try:
        import whisperx
        result = whisperx.assign_word_speakers(
            diarization_result,   # pyannote Annotation objesi
            aligned_result        # WhisperX aligned segments dict
        )
        # << BURADA PATLIYOR: 'Annotation' object has no attribute 'iterrows' >>
        
        for seg in result.get("segments", []):
            speaker = seg.get("speaker", "SPEAKER_00")
            seg["speaker_label"] = default_labels.get(speaker, speaker)
        
        return result
    except Exception as e:
        logger.error("Konusmaci atama hatasi: %s, varsayilan kullaniliyor", e)
        return self._assign_default_labels(aligned_result)  # Hepsi "Doktor" oluyor
```

### 4. Varsayilan etiketleme (fallback - suanki davranis)
```python
def _assign_default_labels(self, aligned_result):
    for seg in aligned_result.get("segments", []):
        if "speaker" not in seg:
            seg["speaker"] = "SPEAKER_00"
        seg["speaker_label"] = "Doktor"  # << HEPSI DOKTOR OLUYOR
    return aligned_result
```

---

## WhisperX assign_word_speakers Kodu

Dosya: `C:\Users\Huckleberry\miniconda3\envs\asr\Lib\site-packages\whisperx\diarize.py`

WhisperX'in `assign_word_speakers()` fonksiyonu pyannote ciktisini su sekilde isliyor:

```python
def assign_word_speakers(diarize_df, transcript_result, fill_nearest=False):
    # diarize_df'in bir pandas DataFrame olmasi bekleniyor!
    # Beklenen kolonlar: 'start', 'end', 'speaker'
    
    for seg in transcript_result["segments"]:
        # ...
        for _, row in diarize_df.iterrows():  # << BURADA PATLIYOR
            # Annotation objesinde iterrows() yok!
```

WhisperX `diarize_df` parametresine pandas DataFrame bekliyor. Ama biz pyannote Annotation objesi geciyoruz.

### WhisperX DiarizationPipeline nasil donusturuyor?

WhisperX kendi `DiarizationPipeline.__call__()` metodunda pyannote ciktisini DataFrame'e cevirir:

```python
class DiarizationPipeline:
    def __call__(self, audio, min_speakers=None, max_speakers=None):
        segments = self.model(audio, ...)
        # segments = pyannote Annotation objesi
        
        diarize_df = pd.DataFrame(
            segments.itertracks(yield_label=True),
            columns=['segment', 'label', 'speaker']
        )
        diarize_df['start'] = diarize_df['segment'].apply(lambda x: x.start)
        diarize_df['end'] = diarize_df['segment'].apply(lambda x: x.end)
        return diarize_df  # << DataFrame dondurur!
```

Yani WhisperX'in kendi pipeline'i `Annotation -> DataFrame` donusumu yapar. Ama biz bu donusumu atliyoruz cunku dogrudan pyannote kullaniyoruz.

---

## Cozum Hipotezleri

### Hipotez 1: Annotation'i DataFrame'e donusturmek
`assign_speakers()` metodunda, `whisperx.assign_word_speakers()`'i cagirmadan once Annotation objesini DataFrame'e cevirebiliriz:

```python
import pandas as pd

diarize_df = pd.DataFrame(
    diarization_result.itertracks(yield_label=True),
    columns=['segment', 'label', 'speaker']
)
diarize_df['start'] = diarize_df['segment'].apply(lambda x: x.start)
diarize_df['end'] = diarize_df['segment'].apply(lambda x: x.end)

result = whisperx.assign_word_speakers(diarize_df, aligned_result)
```

### Hipotez 2: WhisperX DiarizationPipeline kullanmak
Bizim SpeakerDiarizer sinifimiz yerine WhisperX'in kendi DiarizationPipeline'ini kullanmak:

```python
from whisperx.diarize import DiarizationPipeline

diarize_model = DiarizationPipeline(
    model_name="pyannote/speaker-diarization-3.1",
    token=hf_token,
    device="cuda",
)
# Bu otomatik olarak DataFrame dondurur
diarize_df = diarize_model(audio_path, min_speakers=2, max_speakers=2)
result = whisperx.assign_word_speakers(diarize_df, aligned_result)
```

Ama bu yaklasim pyannote 4.0'daki AudioDecoder sorununu tekrar getirebilir cunku WhisperX icinde audio_path string olarak geciliyor.

### Hipotez 3: WhisperX DiarizationPipeline + waveform dict
WhisperX DiarizationPipeline'a waveform dict gecmek:

```python
diarize_model = DiarizationPipeline(...)
waveform, sr = torchaudio.load(audio_path)
diarize_df = diarize_model({"waveform": waveform, "sample_rate": sr}, ...)
```

WhisperX DiarizationPipeline `audio` parametresine ne tip kabul ediyor kontrol edilmeli.

### Hipotez 4: Kendi donusum fonksiyonumuzu yazmak
WhisperX'e bagimli olmadan, Annotation objesinden dogrudan segment etiketleme yapmak. pyannote Annotation'dan zaman araliklarini okuyup, aligned_result segment'lerinin zamanlarina gore en yakin konusmaci atamak.

---

## Arastirilmasi Gereken Sorular

1. **WhisperX 3.8.1'in `assign_word_speakers()` fonksiyonu hangi tipte input bekliyor?**
   - Kesinlikle pandas DataFrame mi?
   - Hangi kolonlar gerekli? (start, end, speaker)
   - Annotation objesinden DataFrame'e dogru donusum nasil yapilir?

2. **WhisperX'in DiarizationPipeline.__call__() metodu pyannote 4.0 ile calisiyor mu?**
   - Iceride `self.model(audio)` cagirdiginda AudioDecoder hatasi alir mi?
   - Waveform dict gecince calisiyor mu?

3. **pyannote.core.Annotation objesinin API'si:**
   - `itertracks(yield_label=True)` nasil calisir?
   - Her track ne dondurur? (Segment, label, speaker)
   - `Segment` objesinin `.start` ve `.end` attribute'lari var mi?

4. **Annotation -> DataFrame donusumu WhisperX ile uyumlu mu?**
   - WhisperX'in beklledigi DataFrame formati tam olarak ne?
   - `fill_nearest` parametresi ne yapar?

5. **Alternatif: kendi speaker assignment fonksiyonumuzu yazmak mantikli mi?**
   - pyannote Annotation'dan zaman aralikli speaker bilgisi almak kolay mi?
   - Her aligned segment icin en cok konusan speaker'i atamak basit mi?

---

## Test Komutlari

### Diarization ciktisini incelemek icin:
```python
import torch, torchaudio
from pyannote.audio import Pipeline

pipeline = Pipeline.from_pretrained(
    "pyannote/speaker-diarization-3.1", 
    token="HF_TOKEN"
)
pipeline.to(torch.device("cuda"))

waveform, sr = torchaudio.load("data/recordings/SOME_FILE.wav")
result = pipeline({"waveform": waveform, "sample_rate": sr}, num_speakers=2)

annotation = result.speaker_diarization
print(type(annotation))  # pyannote.core.annotation.Annotation

# Track'leri listele
for turn, _, speaker in annotation.itertracks(yield_label=True):
    print(f"{turn.start:.1f}s - {turn.end:.1f}s: {speaker}")

# DataFrame'e cevir
import pandas as pd
df = pd.DataFrame(
    annotation.itertracks(yield_label=True),
    columns=['segment', 'label', 'speaker']
)
df['start'] = df['segment'].apply(lambda x: x.start)
df['end'] = df['segment'].apply(lambda x: x.end)
print(df.head())
print(df.columns.tolist())  # Beklenen: ['segment', 'label', 'speaker', 'start', 'end']
```

### WhisperX assign_word_speakers'in beklentisini kontrol:
```python
import whisperx, inspect
src = inspect.getsource(whisperx.assign_word_speakers)
print(src)
```

---

## Mevcut Dosya Icerikleri

### apps/backend/src/asr/diarizer.py (TAM KOD)

```python
"""Konusmaci ayristirma: pyannote community-1 + WhisperX speaker assignment."""

from __future__ import annotations

import logging
from typing import Any

from apps.backend.src.asr.exceptions import DiarizationError
from apps.backend.src.asr.gpu_manager import ASRGPUManager
from apps.backend.src.asr.settings import DiarizationSettings

logger = logging.getLogger(__name__)


class SpeakerDiarizer:
    def __init__(self, settings, hf_token, gpu_manager):
        self._settings = settings
        self._hf_token = hf_token
        self._gpu = gpu_manager
        self._pipeline = None

    @property
    def is_loaded(self):
        return self._pipeline is not None

    def load_model(self):
        if not self._hf_token:
            logger.warning("HF_TOKEN bulunamadi, diarization atlanacak")
            return
        try:
            from pyannote.audio import Pipeline
            model_name = self._settings.model_name
            self._pipeline = Pipeline.from_pretrained(model_name, token=self._hf_token)
            if self._gpu.cuda_available:
                import torch
                self._pipeline.to(torch.device("cuda"))
            self._gpu.register_model("pyannote", self._pipeline)
        except Exception as e:
            logger.warning("Diarization modeli yuklenemedi: %s", e)
            self._pipeline = None

    def diarize(self, audio_path):
        if self._pipeline is None:
            return None
        try:
            import torchaudio
            waveform, sample_rate = torchaudio.load(audio_path)
            result = self._pipeline(
                {"waveform": waveform, "sample_rate": sample_rate},
                num_speakers=self._settings.num_speakers,
                min_speakers=self._settings.min_speakers,
                max_speakers=self._settings.max_speakers,
            )
            if hasattr(result, "speaker_diarization"):
                diarization = result.speaker_diarization
            else:
                diarization = result
            return diarization  # pyannote.core.annotation.Annotation
        except Exception as e:
            logger.error("Diarization hatasi: %s", e)
            return None

    def assign_speakers(self, diarization_result, aligned_result):
        if diarization_result is None:
            return self._assign_default_labels(aligned_result)
        try:
            import whisperx
            result = whisperx.assign_word_speakers(
                diarization_result,  # Annotation objesi
                aligned_result       # WhisperX aligned dict
            )
            # << BURADA PATLIYOR: 'Annotation' has no attribute 'iterrows' >>
            
            default_labels = self._settings.default_labels
            for seg in result.get("segments", []):
                speaker = seg.get("speaker", "SPEAKER_00")
                seg["speaker_label"] = default_labels.get(speaker, speaker)
            return result
        except Exception as e:
            logger.error("Konusmaci atama hatasi: %s, varsayilan kullaniliyor", e)
            return self._assign_default_labels(aligned_result)

    def _assign_default_labels(self, aligned_result):
        for seg in aligned_result.get("segments", []):
            if "speaker" not in seg:
                seg["speaker"] = "SPEAKER_00"
            seg["speaker_label"] = "Doktor"
        return aligned_result

    def unload(self):
        self._gpu.unload_model("pyannote")
        self._pipeline = None
        self._gpu.cleanup()
```

### apps/backend/src/asr/settings.py (Diarization kismi)

```python
class DiarizationSettings(BaseModel):
    model_name: str = "pyannote/speaker-diarization-3.1"
    use_community_model: bool = True
    num_speakers: int = 2
    min_speakers: int = 2
    max_speakers: int = 2
    default_labels: dict[str, str] = {
        "SPEAKER_00": "Doktor",
        "SPEAKER_01": "Hasta",
    }
```

---

## WhisperX DiarizationPipeline Kodu (Referans)

Dosya: `C:\Users\Huckleberry\miniconda3\envs\asr\Lib\site-packages\whisperx\diarize.py`

Bu kodda WhisperX kendi Annotation -> DataFrame donusumunu yapar:

```python
class DiarizationPipeline:
    def __init__(self, model_name=None, token=None, device="cpu", cache_dir=None):
        model_config = model_name or "pyannote/speaker-diarization-community-1"
        self.model = Pipeline.from_pretrained(model_config, token=token, cache_dir=cache_dir).to(device)

    def __call__(self, audio, min_speakers=None, max_speakers=None):
        segments = self.model(audio, min_speakers=min_speakers, max_speakers=max_speakers)
        
        # KRITIK: Annotation -> DataFrame donusumu
        diarize_df = pd.DataFrame(
            segments.itertracks(yield_label=True),
            columns=['segment', 'label', 'speaker']
        )
        diarize_df['start'] = diarize_df['segment'].apply(lambda x: x.start)
        diarize_df['end'] = diarize_df['segment'].apply(lambda x: x.end)
        return diarize_df
```

Ve `assign_word_speakers()` bu DataFrame'i bekliyor:

```python
def assign_word_speakers(diarize_df, transcript_result, fill_nearest=False):
    # diarize_df: pandas DataFrame with columns [segment, label, speaker, start, end]
    transcript_segments = transcript_result["segments"]
    
    for seg_idx, seg in enumerate(transcript_segments):
        # ...
        for _, row in diarize_df.iterrows():  # DataFrame.iterrows() kullanir!
            # row['start'], row['end'], row['speaker']
```

---

## Ozet

Sorun net: `whisperx.assign_word_speakers()` pandas DataFrame bekliyor, biz pyannote Annotation objesi geciyoruz. WhisperX'in kendi DiarizationPipeline sinifi icinde bu donusum yapiliyor ama biz dogrudan pyannote kullandigimiz icin bu adimi atliyoruz.

En basit cozum: `assign_speakers()` metodunda, `whisperx.assign_word_speakers()` cagirmadan once Annotation'i DataFrame'e cevirmek.
