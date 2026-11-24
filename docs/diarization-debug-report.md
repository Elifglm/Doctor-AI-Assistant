# Diarization (Konusmaci Ayristirma) Hatasi - Arastirma Dokumani

## Problem Ozeti

Turkce klinik ASR uygulamasinda (doktor-hasta gorusmesi transkripsiyon) **speaker diarization** calismyor. Transkripsiyon basarili oluyor (metin dogru) ama tum segmentler "Doktor" olarak etiketleniyor, "Hasta" etiketi hic atanmiyor.

Backend logunda su hata gorunuyor:
```
Diarization hatasi: name 'AudioDecoder' is not defined
```

Onceki hata (artik cozuldu):
```
Diarization modeli yuklenemedi: Pipeline.from_pretrained() got an unexpected keyword argument 'use_auth_token'
```
Bu `use_auth_token` -> `token` olarak degistirilerek cozuldu. Simdi model YUKLENIYOR ama `diarize()` cagrisi sirasinda `AudioDecoder` hatasi veriyor.

---

## Sistem Bilgileri

### Donanim
- GPU: NVIDIA GeForce RTX 5080 Laptop GPU
- OS: Windows 11 Pro 10.0.26200

### Yazilim Ortami
- Python: 3.11.14 (miniconda3, `asr` conda env)
- Conda env path: `C:\Users\Huckleberry\miniconda3\envs\asr\`

### Kritik Kutuphane Versiyonlari
```
pyannote.audio:     4.0.4
torch:              2.8.0+cu128
torchaudio:         2.8.0+cu128
torchcodec:         KURULU AMA DLL'LER EKSIK (libtorchcodec_core*.dll bulunamiyor)
whisperx:           3.8.1
faster-whisper:     1.2.1
huggingface_hub:    0.32.2 (tahmini, guncel)
ffmpeg:             8.0.1-full_build (WinGet ile kurulu)
```

### Torchcodec DLL Sorunu
`pyannote.audio` import edildiginde su uyari cikyor:
```
torchcodec is not installed correctly so built-in audio decoding will fail.
Could not find module 'libtorchcodec_core8.dll' (or one of its dependencies)
```
Bu uyari tum FFmpeg versiyonlari (4, 5, 6, 7, 8) icin tekrarlaniyor. Hicbir `libtorchcodec_core*.dll` bulunamiyor.

---

## Proje Yapisi

```
KlinikAsistan/
├── apps/
│   ├── backend/
│   │   └── src/
│   │       ├── asr/                    # YENI - Hibrit ASR pipeline
│   │       │   ├── __init__.py
│   │       │   ├── settings.py         # ASR yapilandirmasi
│   │       │   ├── pipeline.py         # Ana orkestrator
│   │       │   ├── diarizer.py         # << SORUNLU DOSYA
│   │       │   ├── batch_transcriber.py
│   │       │   ├── streaming_transcriber.py
│   │       │   ├── vad.py
│   │       │   ├── noise_suppressor.py
│   │       │   ├── gpu_manager.py
│   │       │   ├── audio_utils.py
│   │       │   ├── output_formatter.py
│   │       │   └── exceptions.py
│   │       ├── services/
│   │       │   └── asr_service.py      # Pipeline'i async yoneten servis
│   │       ├── ws/
│   │       │   └── audio_handler.py    # WebSocket handler
│   │       └── routes/
│   │           └── transcription.py    # WS endpoint
│   └── frontend/                       # Electron + React
├── src/                                # ESKI ASR pipeline (dokunulmuyor)
├── config/
│   ├── settings.py
│   └── medical_terms.py
├── .env                                # HF_TOKEN burada
└── data/
    └── recordings/                     # WAV dosyalari
```

---

## Pipeline Akisi (Batch Isleme)

Kayit durduruldugunda sirayla su adimlar calisir:

```
1. Stage 0/5: Ses dosyasi dogrulama
2. Stage 1/5: DeepFilterNet3 gurultu bastirma
3. Stage 2/5: faster-whisper large-v3 batch transkripsiyon (WhisperX)
4. Stage 3/5: wav2vec2 kelime hizalama (WhisperX align)
5. Stage 4/5: pyannote speaker diarization  << BURADA PATLIYOR
6. Stage 5/5: Sonuclari formatlama + DB kayit
```

Stage 1-3 basariyla tamamlaniyor. Stage 4'te `diarize()` cagrisi `AudioDecoder` hatasi veriyor, diarization atlanıyor, tum segmentler varsayilan olarak "Doktor" etiketleniyor.

---

## Sorunlu Kod: diarizer.py

Dosya: `apps/backend/src/asr/diarizer.py`

### load_model() - CALISIYOR
```python
def load_model(self) -> None:
    from pyannote.audio import Pipeline

    model_name = self._settings.model_name  # "pyannote/speaker-diarization-3.1"
    self._pipeline = Pipeline.from_pretrained(
        model_name,
        token=self._hf_token,  # HF_TOKEN .env'den okunuyor
    )

    # GPU'ya tasi
    if self._gpu.cuda_available:
        import torch
        self._pipeline.to(torch.device("cuda"))
```

Bu kisim CALISIYOR. Model basariyla yukleniyor.

### diarize() - BURADA PATLIYOR
```python
def diarize(self, audio_path: str) -> Any:
    if self._pipeline is None:
        return None
    try:
        diarization = self._pipeline(
            audio_path,           # WAV dosyasi yolu (string)
            num_speakers=2,
            min_speakers=2,
            max_speakers=2,
        )
        return diarization
    except Exception as e:
        logger.error("Diarization hatasi: %s", e)  # << "name 'AudioDecoder' is not defined"
        return None
```

Hata: `self._pipeline(audio_path, ...)` cagrildiginda pyannote icinde `AudioDecoder` isimli bir sinif bulunamiyor.

### assign_speakers() - HICBIR ZAMAN CALISMIYOR
diarize() None dondurdugu icin varsayilan etiketleme yapiliyor:
```python
def _assign_default_labels(self, aligned_result: dict) -> dict:
    for seg in aligned_result.get("segments", []):
        if "speaker" not in seg:
            seg["speaker"] = "SPEAKER_00"
        seg["speaker_label"] = "Doktor"  # Hepsi "Doktor" oluyor
    return aligned_result
```

---

## Pipeline'dan diarizer cagirma kodu

Dosya: `apps/backend/src/asr/pipeline.py` (satirlar 490-507)

```python
async def _run_diarization(self, wav_path: str, aligned_result: dict) -> dict:
    diarizer = SpeakerDiarizer(
        settings=self._settings.diarization,
        hf_token=self._settings.hf_token,
        gpu_manager=self._gpu,
    )
    await asyncio.to_thread(diarizer.load_model)        # CALISIYOR
    diarization = await asyncio.to_thread(diarizer.diarize, wav_path)  # PATLIYOR
    result = await asyncio.to_thread(
        diarizer.assign_speakers, diarization, aligned_result
    )
    await asyncio.to_thread(diarizer.unload)
    return result
```

---

## Diarization Ayarlari

Dosya: `apps/backend/src/asr/settings.py`

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

## .env Dosyasi

```
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx
ASR_LOG_LEVEL=INFO
```

---

## Yapilan Testler

### Test 1: Pipeline.from_pretrained dogrudan cagirma
```python
from pyannote.audio import Pipeline
p = Pipeline.from_pretrained('pyannote/speaker-diarization-3.1', token='hf_...')
print(p)  # CALISIYOR - SpeakerDiarization objesi doner
```
**Sonuc: BASARILI**

### Test 2: diarizer.load_model() cagirma
```python
from apps.backend.src.asr.diarizer import SpeakerDiarizer
from apps.backend.src.asr.settings import DiarizationSettings
from apps.backend.src.asr.gpu_manager import ASRGPUManager

diarizer = SpeakerDiarizer(DiarizationSettings(), 'hf_...', ASRGPUManager())
diarizer.load_model()
print(diarizer.is_loaded)  # True
```
**Sonuc: BASARILI**

### Test 3: diarize() cagirma (YAPILMADI)
Bu test henuz yapilmadi. Muhtemelen `self._pipeline(audio_path, ...)` cagrisi sirasinda pyannote dahili olarak ses dosyasini yuklerken `AudioDecoder` sinifini bulamiyor.

---

## Hipotezler

### Hipotez 1: torchcodec DLL eksikligi
pyannote.audio 4.0 ses dosyalarini yuklemek icin `torchcodec` kullanmaya calisiyor. Ama Windows'ta `libtorchcodec_core*.dll` dosyalari bulunamiyor. `AudioDecoder` sinifi torchcodec'in bir parcasi olabilir.

pyannote uyarisi:
```
torchcodec is not installed correctly so built-in audio decoding will fail.
Solutions are:
* use audio preloaded in-memory as {'waveform': torch.Tensor, 'sample_rate': int} dictionary
* fix torchcodec installation
```

**Olasi cozum**: Ses dosyasini string path yerine `{'waveform': tensor, 'sample_rate': int}` dict olarak gecirmek.

### Hipotez 2: pyannote 4.0 API degisikligi
pyannote 4.0'da `pipeline(audio_path)` yerine farkli bir cagri yontemi gerekiyor olabilir. Belki `pipeline({"waveform": waveform, "sample_rate": sr})` seklinde in-memory audio gecirmek gerekiyor.

### Hipotez 3: torchaudio backend sorunu
`torchaudio` Windows'ta DLL yukleme sorunu yasiyor (`OSError: [WinError 4551]`). Bu pyannote'un ses yuklemesini etkiliyor olabilir.

### Hipotez 4: pyannote versiyonunu dusurme
pyannote.audio 3.x (3.1 veya 3.3) versiyonunda bu sorun yoktu. 4.0'a geciste torchcodec bagimliligi eklenmis olabilir.

---

## Arastirilmasi Gereken Sorular

1. **pyannote.audio 4.0.4'te `AudioDecoder` nedir ve nereden geliyor?**
   - torchcodec'in bir sinifi mi?
   - torchaudio'nun bir sinifi mi?
   - pyannote'un kendi sinifi mi?

2. **torchcodec DLL'leri Windows'ta nasil duzeltilir?**
   - PyTorch 2.8.0 ile uyumlu torchcodec versiyonu hangisi?
   - FFmpeg 8.0 DLL'leri nereye konulmali?

3. **pyannote 4.0'da ses dosyasi yerine in-memory waveform gecmek mumkun mu?**
   - `pipeline({"waveform": tensor, "sample_rate": 16000}, num_speakers=2)` calisiyor mu?
   - Eger calisiyorsa, WAV dosyasini once torch ile yukleyip dict olarak gecebiliriz.

4. **pyannote'u 3.x'e dusurmek bir cozum mu?**
   - pyannote 3.1 veya 3.3 ile torch 2.8 uyumlu mu?
   - Eski versiyonda `AudioDecoder` bagimliligı var mi?

5. **WhisperX'in kendi DiarizationPipeline sinifi bu sorunu bypass ediyor mu?**
   - `from whisperx.diarize import DiarizationPipeline` kullanmak fark yaratir mi?
   - WhisperX pyannote'u nasil cagiriyor?

---

## WhisperX'in Diarization Kodu (Referans)

Dosya: `C:\Users\Huckleberry\miniconda3\envs\asr\Lib\site-packages\whisperx\diarize.py`

WhisperX kendi `DiarizationPipeline` sinifini kullaniyor:
```python
class DiarizationPipeline:
    def __init__(self, model_name=None, token=None, device="cpu", cache_dir=None):
        model_config = model_name or "pyannote/speaker-diarization-community-1"
        self.model = Pipeline.from_pretrained(model_config, token=token, cache_dir=cache_dir).to(device)

    def __call__(self, audio, min_speakers=None, max_speakers=None):
        # audio: Union[str, np.ndarray] - dosya yolu veya numpy array
        segments = self.model(audio, min_speakers=min_speakers, max_speakers=max_speakers)
        ...
```

WhisperX varsayilan olarak `pyannote/speaker-diarization-community-1` modelini kullaniyor (gated access gerektirmiyor). Bizim kodumuz `pyannote/speaker-diarization-3.1` kullaniyor.

---

## Eski Calisan Sistem (Referans)

`src/diarizer.py` dosyasinda (eski pipeline, degistirilmiyor) WhisperX'in DiarizationPipeline sinifi kullaniliyordu:
```python
from whisperx.diarize import DiarizationPipeline

class Diarizer:
    def load_model(self):
        self.pipeline = DiarizationPipeline(
            model_name="pyannote/speaker-diarization-3.1",
            token=self.hf_token,
            device="cuda",
        )
```

Bu eski kod **calisiyordu** (pyannote 3.x zamaninda). Simdi ayni model pyannote 4.0 ile yuklendiginde `AudioDecoder` hatasi veriyor.

---

## Onerilen Cozum Yollari (Arastirilacak)

### Yol 1: In-memory waveform gecme
```python
import torchaudio

waveform, sample_rate = torchaudio.load(audio_path)
diarization = self._pipeline(
    {"waveform": waveform, "sample_rate": sample_rate},
    num_speakers=2,
)
```

### Yol 2: WhisperX DiarizationPipeline kullanma
```python
from whisperx.diarize import DiarizationPipeline

pipeline = DiarizationPipeline(
    model_name="pyannote/speaker-diarization-3.1",
    token=hf_token,
    device="cuda",
)
diarization = pipeline(audio_path, min_speakers=2, max_speakers=2)
```

### Yol 3: torchcodec duzeltme
Windows'ta FFmpeg shared DLL'lerini torchcodec'in buldugu yere koymak.

### Yol 4: pyannote downgrade
```bash
pip install pyannote.audio==3.3.2
```

---

## Log Ornekleri

### Model Yukleme (BASARILI)
```
Diarization modeli yukleniyor: pyannote/speaker-diarization-3.1
Diarization modeli GPU'ya tasindi
Diarization modeli yuklendi
```

### Diarize Cagrisi (BASARISIZ)
```
Diarization basliyor: C:\Users\...\data\recordings\session_1743800535.wav
Diarization hatasi: name 'AudioDecoder' is not defined
Diarization modeli yuklu degil, atlaniyor
Varsayilan konusmaci etiketleri atandi (diarization atlanmis)
```

### Onceki Hata (COZULDU)
```
Diarization modeli yuklenemedi: Pipeline.from_pretrained() got an unexpected keyword argument 'use_auth_token'
```
Cozum: `use_auth_token=` -> `token=` olarak degistirildi.
