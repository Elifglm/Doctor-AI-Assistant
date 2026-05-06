"""Turkce test ses dosyalarini indir (Common Voice / MediaSpeech)."""

import json
import numpy as np
import soundfile as sf
from pathlib import Path

OUTPUT_DIR = Path("data/test_audio")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SR = 16000
SILENCE_SAMPLES = 8000  # 0.5s
manifest = []


def concat_clips_from_dataset(dataset, name, source, text_key, max_clips=200):
    """Dataset kliplerini birlestir."""
    audio_parts = []
    texts = []

    for i, clip in enumerate(dataset):
        if i >= max_clips:
            break
        audio = clip["audio"]["array"]
        sr = clip["audio"]["sampling_rate"]

        if sr != SR:
            # Basit resample (librosa olmadan)
            ratio = SR / sr
            new_len = int(len(audio) * ratio)
            indices = np.linspace(0, len(audio) - 1, new_len).astype(int)
            audio = audio[indices]

        audio_parts.append(audio.astype(np.float32))
        audio_parts.append(np.zeros(SILENCE_SAMPLES, dtype=np.float32))

        text = clip.get(text_key, "")
        if text:
            texts.append(text.strip())

    if not audio_parts:
        print(f"  {name}: klip yok, atlaniyor")
        return

    combined = np.concatenate(audio_parts)
    duration = len(combined) / SR

    if duration < 30:
        print(f"  {name}: cok kisa ({duration:.0f}s), atlaniyor")
        return

    wav_path = OUTPUT_DIR / f"{name}.wav"
    txt_path = OUTPUT_DIR / f"{name}.txt"

    sf.write(str(wav_path), combined, SR, subtype="PCM_16")
    txt_path.write_text(" ".join(texts), encoding="utf-8")

    entry = {
        "name": name,
        "wav": str(wav_path),
        "txt": str(txt_path),
        "duration_s": round(duration, 1),
        "clips": len(texts),
        "source": source,
    }
    manifest.append(entry)
    print(f"  {name}: {duration:.0f}s, {len(texts)} cumle")


# --- Dataset 1: MediaSpeech Turkish ---
print("MediaSpeech Turkish yukleniyor...")
try:
    from datasets import load_dataset
    ds = load_dataset("Nexdata/Turkish_Speech_2000h_Subset", split="train", streaming=True)
    clips = []
    for i, item in enumerate(ds):
        clips.append(item)
        if i >= 150:
            break

    # 3 dosyaya bol
    per_file = len(clips) // 3
    for i in range(3):
        batch = clips[i*per_file:(i+1)*per_file]
        # Simdi dict formatinda concat
        audio_parts = []
        texts = []
        for clip in batch:
            audio = clip["audio"]["array"]
            sr = clip["audio"]["sampling_rate"]
            if sr != SR:
                ratio = SR / sr
                new_len = int(len(audio) * ratio)
                indices = np.linspace(0, len(audio) - 1, new_len).astype(int)
                audio = audio[indices]
            audio_parts.append(audio.astype(np.float32))
            audio_parts.append(np.zeros(SILENCE_SAMPLES, dtype=np.float32))
            text = clip.get("transcription", clip.get("sentence", clip.get("text", "")))
            if text:
                texts.append(text.strip())

        if audio_parts:
            combined = np.concatenate(audio_parts)
            duration = len(combined) / SR
            name = f"turkish_test_{i+1}"
            wav_path = OUTPUT_DIR / f"{name}.wav"
            txt_path = OUTPUT_DIR / f"{name}.txt"
            sf.write(str(wav_path), combined, SR, subtype="PCM_16")
            txt_path.write_text(" ".join(texts), encoding="utf-8")
            manifest.append({
                "name": name, "wav": str(wav_path), "txt": str(txt_path),
                "duration_s": round(duration, 1), "clips": len(texts),
                "source": "Nexdata/Turkish_Speech",
            })
            print(f"  {name}: {duration:.0f}s, {len(texts)} cumle")

except Exception as e:
    print(f"  MediaSpeech hatasi: {e}")
    print("  Alternatif deneniyor: Common Voice...")

    try:
        from datasets import load_dataset
        ds = load_dataset("mozilla-foundation/common_voice_17_0", "tr",
                         split="test", streaming=True)
        clips = []
        for i, item in enumerate(ds):
            clips.append(item)
            if i >= 200:
                break

        per_file = max(1, len(clips) // 4)
        for i in range(min(4, len(clips) // per_file)):
            batch = clips[i*per_file:(i+1)*per_file]
            audio_parts = []
            texts = []
            for clip in batch:
                audio = clip["audio"]["array"]
                sr = clip["audio"]["sampling_rate"]
                if sr != SR:
                    ratio = SR / sr
                    new_len = int(len(audio) * ratio)
                    indices = np.linspace(0, len(audio) - 1, new_len).astype(int)
                    audio = audio[indices]
                audio_parts.append(audio.astype(np.float32))
                audio_parts.append(np.zeros(SILENCE_SAMPLES, dtype=np.float32))
                text = clip.get("sentence", "")
                if text:
                    texts.append(text.strip())

            if audio_parts:
                combined = np.concatenate(audio_parts)
                duration = len(combined) / SR
                name = f"cv_test_{i+1}"
                wav_path = OUTPUT_DIR / f"{name}.wav"
                txt_path = OUTPUT_DIR / f"{name}.txt"
                sf.write(str(wav_path), combined, SR, subtype="PCM_16")
                txt_path.write_text(" ".join(texts), encoding="utf-8")
                manifest.append({
                    "name": name, "wav": str(wav_path), "txt": str(txt_path),
                    "duration_s": round(duration, 1), "clips": len(texts),
                    "source": "mozilla-foundation/common_voice_17_0 tr test",
                })
                print(f"  {name}: {duration:.0f}s, {len(texts)} cumle")
    except Exception as e2:
        print(f"  Common Voice hatasi: {e2}")

# Manifest kaydet
manifest_path = OUTPUT_DIR / "manifest.json"
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

print(f"\nToplam: {len(manifest)} test dosyasi")
for m in manifest:
    print(f"  {m['name']}: {m['duration_s']}s ({m['clips']} cumle)")
