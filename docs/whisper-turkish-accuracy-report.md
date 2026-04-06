# Whisper Turkce Tibbi Transkripsiyon Dogruluk Sorunlari - Arastirma Dokumani

## Problem Ozeti

Turkce klinik ASR uygulamasinda Whisper large-v3 modeli ile streaming transkripsiyon yapilmaktadir. Model genel olarak iyi calismakta ancak **Turkce'ye ozgu sistematik hatalar** yapmaktadir. Bu hatalar LLM post-correction veya LoRA fine-tuning **olmadan** cozulmek istenmektedir.

### Gozlemlenen Hata Turleri

#### 1. Turkce Ek Hatalari (Agglutinative Morphology)
Turkce bitisken bir dildir - kelime kokleri uzerine ekler eklenir. Whisper ekleri yanlis duyar:

| Soylenen | Transkript | Hata Turu |
|----------|-----------|-----------|
| Agrilar**im** genellikle | Agrilar**in** genellikle | -im → -in (iyelik eki hatasi) |
| hissed**iyorum** | hissed**iyor** | -iyorum → -iyor (kisi eki dusmesi) |
| kolumda | kulumda | o→u sesli harf karisikligi |
| agriniz mi | haram mi | tam kelime yanlis tanima |

#### 2. Kelime Dusmeleri
| Soylenen | Transkript | Hata |
|----------|-----------|------|
| **son** birkac haftadir | birkac haftadir | "son" kelimesi dusmus |

#### 3. Sesli Harf Karisikliklari (Vowel Confusion)
Turkce'de o/u, i/ı, e/a sesleri benzerdir. Whisper bunlari karistirir:
- kol**u**mda → kul**u**mda (o→u)
- g**o**gus → g**o**gus (dogru ama bazen g**u**gus olur)

---

## Sistem Bilgileri

```
GPU:                NVIDIA RTX 5080 Laptop GPU (16GB VRAM)
OS:                 Windows 11 Pro
Python:             3.11.14
faster-whisper:     1.2.1 (CTranslate2 backend)
whisperx:           3.8.1
Model:              Whisper large-v3 (1.55B parametre)
Streaming:          ufal/whisper_streaming (LocalAgreement)
Beam size:          5
Language:           tr (Turkce)
```

---

## Mevcut Pipeline Mimarisi

```
KAYIT SIRASINDA (gercek zamanli):
  Frontend 250ms WebM chunks → WebSocket → Backend
    → FFmpeg pipe (WebM → PCM 16kHz float32)
    → OnlineTranscriber (LocalAgreement + faster-whisper large-v3 beam=5)
      → hotwords parametresi (tibbi terimler listesi)
      → temperature=0.0 (greedy, halusinasyon onleme)
      → condition_on_previous_text=False
    → TurkishPostProcessor (deASCIIfication + tibbi terim sozlugu)
    → SegmentMerger (kisa parcalari cumle seviyesinde birlestir)
    → DB'ye kaydet + Frontend'e gonder

KAYIT SONRASI (~30-60 saniye):
  → Diarization (pyannote) → Doktor/Hasta ayirimi
  → Rapor olusturma (NER + LLM)
```

---

## Halihazirda Uygulanan Optimizasyonlar

### 1. Hotwords Parametresi
faster-whisper 1.2.1'in `hotwords` parametresi ile tibbi terimler decoder'a bias olarak veriliyor. Her 30 saniyelik window'da yeniden inject edilir (initial_prompt'tan farkli olarak kaybolmaz).

Dosya: `apps/backend/src/asr/online_transcriber.py`
```python
self._asr.transcribe_kargs = {
    "condition_on_previous_text": False,
    "temperature": 0.0,
    "hallucination_silence_threshold": 2.0,
    "hotwords": (
        "kol kolunda kolumda kolunuzda bacak bacağında göğüs göğsünde "
        "baş başında bel belinde omuz omzunda diz dizinde kalça dirsek bilek "
        "ayak boyun karın karnında ağrı ağrısı ağrınız sızı şişlik "
        "tansiyon nabız ateş solunum bulantı kusma ishal kabızlık "
        "halsizlik yorgunluk nefes darlığı öksürük balgam "
        "diyabet hipertansiyon astım KOAH tiroid epilepsi "
        "hemogram biyokimya sedimentasyon CRP kreatinin üre "
        "ekokardiyografi elektrokardiyografi EKG ultrasonografi tomografi "
        "miyokard enfarktüsü pnömoni bronşit gastrit kolesistit "
        "parasetamol amoksisilin metformin atorvastatin ramipril "
        "muayene şikayet öykü anamnez fizik muayene inspeksiyon "
        "palpasyon oskültasyon perküsyon"
    ),
}
```

### 2. Medical Initial Prompt
Dosya: `config/medical_terms.py`
```python
MEDICAL_INITIAL_PROMPT = (
    "Doktor hasta muayenesi. Hosgeldiniz, sikayetiniz nedir? "
    "Kolumda agri var, basim agriyor, karnimda agri var, gogsum agriyor. "
    "Tansiyon degerleriniz nasil? Nabiz, ates, solunum sayisi. "
    "Ne zamandir devam ediyor? Surekli mi aralikli mi? "
    "Daha once ameliyat oldunuz mu? Bilinen hastalik var mi? "
    "Diyabet, hipertansiyon, astim, KOAH, tiroid, epilepsi. "
    "Kullandiginiz ilac var mi? Alerjiniz var mi? "
    "Hemogram, biyokimya, tam kan sayimi, sedimentasyon. "
    "Ekokardiyografi, elektrokardiyografi, EKG, EEG, EMG. "
    "Bilgisayarli tomografi, manyetik rezonans, ultrasonografi, rontgen. "
    "Miyokard enfarktusu, pnomoni, bronsit, gastrit, kolesistit. "
    "Parasetamol, amoksisilin, metformin, atorvastatin, ramipril. "
    "Omuz, dirsek, bilek, kalca, diz, ayak bilegi. "
    "Bas agrisi, bel agrisi, boyun agrisi, goz agrisi. "
    "Bulanti, kusma, ishal, kabizlik, halsizlik, yorgunluk. "
    "Nefes darligi, oksuruk, bogaz agrisi, burun tikaniikligi. "
    "Doktor muayene bulgulari kaydediyor."
)
```

### 3. Post-Processor (Statik Sozluk)
Dosya: `apps/backend/src/asr/post_processor.py`
```python
class TurkishPostProcessor:
    def process(self, text: str) -> str:
        text = self._deasciify(text)           # gogus → göğüs
        text = self._apply_medical_corrections(text)  # kulumda → kolumda
        return text

MEDICAL_CORRECTIONS = {
    "kulunuzda": "kolunuzda",
    "kulumda": "kolumda",
    "haram mi": "ağrınız mı",
    "haram mı": "ağrınız mı",
    # ... diger bilinen hatalar
}
```

### 4. Temperature = 0.0
Greedy decoding - rastgele sampling kapatildi. Deterministic output.

### 5. Hallucination Silence Threshold = 2.0
Sessiz bolumlerde hayalet metin uretimini onler.

---

## Neden Bu Optimizasyonlar Yeterli Degil?

### Hotwords Sinirlamasi
- Hotwords sadece **kelime seviyesinde** bias verir
- **Ek seviyesinde** (suffix) etki etmez: "kolumda" vs "kulumda" icin "kol" hotword olsa bile model "-umda" ekini yanlis duyabilir
- Fonetik benzerlik cok yuksek oldugundan decoder hala yanlis secim yapabilir

### Post-Processor Sinirlamasi
- Statik sozluk sadece **onceden bilinen** hatalari duzeltir
- "Agrilarim" → "Agrilarin" gibi **baglama bagimli** hatalari yakalayamaz (cunku "agrilarin" de gecerli Turkce)
- Her yeni hata icin manuel ekleme gerekir

### Initial Prompt Sinirlamasi
- Sadece ilk 224 token (LocalAgreement'ta ilk window)
- Sonraki window'larda etkisini kaybeder
- Ek seviyesinde (morphological) etki sinirli

---

## Arastirilmasi Gereken Konular

### 1. Whisper Decoder'a Turkce Morfolojik Bias Vermek
- Whisper'in CTC/attention decoder'ina Turkce morfolojik kurallar inject edilebilir mi?
- Turkce sesli harf uyumu (vowel harmony) kurallari decoder'a constraint olarak eklenebilir mi?
- Ornegin: "kol" kokunden sonra sadece "-um, -unda, -umu" gelebilir, "-un, -unda" gelemez

### 2. Shallow Fusion ile N-gram Language Model
- Whisper beam search sirasinda harici bir Turkce LM ile log-linear interpolasyon yapilabilir mi?
- `faster-whisper` CTranslate2 backend'i shallow fusion destekliyor mu?
- Turkce tibbi metin uzerinde egitilmis bir KenLM modeli beam search'u yonlendirebilir mi?
- Bu yaklasim ek hatalarina nasil yardimci olur?

### 3. Trie-based Hotword Boosting
- Mevcut `hotwords` parametresi yeterince guclu mu?
- Trie (prefix tree) yapisinda hotword boosting implementasyonu var mi?
- Her hotword icin farkli boost degeri atanabilir mi?
- Turkce eklenmis formlar icin trie olusturulabilir mi? (kol, kolum, kolumda, kolumdan, kolunda, kolundaki...)

### 4. CTranslate2 Seviyesinde Customization
- faster-whisper'in kullandigi CTranslate2 backend'inde decoder parametreleri var mi?
- `suppress_tokens` ile belirli token'lar bastiriilabilir mi?
- `prefix` parametresi ile decoder zorunlu baslangic metni verilebilir mi?
- `logprob_threshold` ile dusuk guvenli ciktilar filtrelenebilir mi?

### 5. Whisper'in Turkce Tokenizer'i
- Whisper hangi tokenizer kullaniyor? (tiktoken, sentencepiece?)
- Turkce kelimeler nasil tokenize ediliyor?
- "kolumda" ve "kulumda" farkli token'lara mi karsilik geliyor?
- Token seviyesinde bias vermek mumkun mu?

### 6. Acoustic Model Adaptasyonu (Fine-tuning Olmadan)
- Test-Time Adaptation (TTA) Whisper'a uygulanabilir mi?
- Prompt tuning / prefix tuning (model agirliklarini degistirmeden) mumkun mu?
- Adapter katmanlari (LoRA gibi ama inference-time) eklenebilir mi?

### 7. Multi-pass Decoding
- Ilk geciste hizli transkripsiyon, ikinci geciste sadece dusuk guvenli bolumleri tekrar isle
- avg_logprob veya word-level confidence score'lari ile "dusuk guvenli" kelimeleri tespit et
- Bu kelimeleri daha buyuk beam size veya farkli temperature ile tekrar transkribe et
- Bu yaklasim streaming pipeline'a nasil entegre edilir?

### 8. Ses On-Isleme (Pre-processing)
- Mikrofon kalitesi etkiliyor mu? Farkli sample rate, bit depth?
- Ses normalizasyonu (volume normalization) dogrulugu arttirir mi?
- Frequency filtering (bandpass) ile belirli frekanslari vurgulamak yardimci olur mu?
- WebM/Opus codec'i kalite kaybi yapiyor mu? Daha iyi codec secenegi var mi?

### 9. Alternative Turkce ASR Modelleri
- `mpoyraz/wav2vec2-xls-r-300m-cv7-turkish` (%8.62 WER) Whisper'dan daha iyi mi?
- Whisper + wav2vec2 ensemble (iki modelin ciktilarini birlestirmek) mumkun mu?
- NVIDIA NeMo Canary gibi alternatif modeller Turkce'de nasil?
- Google Cloud Speech-to-Text Chirp 3 Turkce performansi nasil? (karsilastirma baseline'i olarak)

### 10. Turkce'ye Ozgu Cozumler
- Turkce sesli harf uyumu (vowel harmony) kurallarini post-processing'te kullanmak
  - "kol" koku kalin unlu → ekleri de kalin olmali: kolumda, kolunda (dogru), kulumda (yanlis - ince unlu)
  - Bu kural ile "kulumda" otomatik "kolumda" olarak duzeltilebilir
- Turkce unsuz yumusaklama/sertlesme kurallari
- Zemberek morfolojik analizor ile gecersiz ek kombinasyonlarini tespit etmek

---

## Mevcut Kod Dosyalari

### Proje Yapisi (ASR ile ilgili)
```
apps/backend/src/asr/
  online_transcriber.py   # LocalAgreement streaming motoru
  post_processor.py       # deASCIIfication + statik sozluk duzeltme
  segment_merger.py       # Kisa parcalari cumle seviyesinde birlestir
  pipeline.py             # Ana orkestrator
  diarizer.py             # Konusmaci ayristirma (pyannote)
  audio_utils.py          # FFmpeg pipe, AudioAccumulator
  gpu_manager.py          # GPU bellek yonetimi
  settings.py             # Yapilandirma
  vendor/
    whisper_online.py      # ufal/whisper_streaming (LocalAgreement)

config/
  medical_terms.py         # Tibbi terim prompt'u
```

### OnlineTranscriber - Tam Kod
Dosya: `apps/backend/src/asr/online_transcriber.py`
```python
class OnlineTranscriber:
    """LocalAgreement streaming transkripsiyon motoru."""

    def __init__(self, settings, medical_prompt, gpu_manager):
        self._settings = settings
        self._medical_prompt = medical_prompt
        self._gpu = gpu_manager

    def load(self):
        from apps.backend.src.asr.vendor.whisper_online import (
            FasterWhisperASR, OnlineASRProcessor,
        )
        self._asr = FasterWhisperASR(
            lan=self._settings.language,      # "tr"
            modelsize=self._settings.model_name,  # "large-v3"
        )
        self._asr.transcribe_kargs = {
            "condition_on_previous_text": False,
            "temperature": 0.0,
            "hallucination_silence_threshold": 2.0,
            "hotwords": "kol kolunda kolumda ... (tibbi terimler)",
        }
        self._asr.use_vad()
        self._processor = OnlineASRProcessor(
            self._asr,
            buffer_trimming=("segment", 15),
        )
        # Medical prompt seed
        if self._medical_prompt:
            self._processor.commited = [(0, 0, self._medical_prompt)]

    def insert_audio_chunk(self, pcm):
        self._processor.insert_audio_chunk(pcm)

    def process_iter(self):
        beg, end, text = self._processor.process_iter()
        if text and text.strip():
            text = self._post_processor.process(text.strip())
            return ConfirmedSegment(text=text, start=beg, end=end)
        return None
```

### whisper_online.py - Transcribe Metodu (vendor)
```python
class FasterWhisperASR(ASRBase):
    def transcribe(self, audio, init_prompt=""):
        _defaults = dict(beam_size=5, word_timestamps=True,
                        condition_on_previous_text=True, initial_prompt=init_prompt)
        _defaults.update(self.transcribe_kargs)
        segments, info = self.model.transcribe(
            audio, language=self.original_language, **_defaults
        )
        return list(segments)
```

### Post-Processor - Tam Kod
```python
class TurkishPostProcessor:
    def process(self, text):
        text = self._deasciify(text)
        text = self._apply_medical_corrections(text)
        return text

    def _deasciify(self, text):
        from turkish.deasciifier import Deasciifier
        return Deasciifier(text).convert_to_turkish()

    def _apply_medical_corrections(self, text):
        for wrong, correct in MEDICAL_CORRECTIONS.items():
            if wrong != correct and wrong in text.lower():
                pattern = re.compile(re.escape(wrong), re.IGNORECASE)
                text = pattern.sub(correct, text)
        return text
```

---

## Kisitlamalar

- **LLM kullanmadan** cozum isteniyor (gecikme ekler)
- **Fine-tuning yapmadan** cozum isteniyor (veri hazirlamak zaman alir)
- Cozum **streaming pipeline icinde** calisabilmeli (dusuk gecikme)
- Sub-saniye icerisinde islenmeli (post-processing)
- Turkce'ye ozgu morfolojik kurallari kullanabilir
- Python kutuphaneleri kullanilabilir (pip install)
- GPU mevcut (RTX 5080 16GB) ama streaming model zaten ~5GB kullaniyor

---

## Beklenen Cikti

1. **Hangi yaklasim en etkili?** (shallow fusion, trie hotwords, morfolojik post-processing, vb.)
2. **faster-whisper/CTranslate2 ile uyumlu mu?**
3. **Streaming pipeline'a nasil entegre edilir?**
4. **Tahmini dogruluk iyilesmesi ne kadar?**
5. **Implementasyon detaylari** (kod ornekleri, kutuphane onerileri)
6. **Turkce sesli harf uyumu kurallari ile post-correction ne kadar etkili olur?**
