"""Gercek Turkce ses dosyalari hazirla (FLEURS parquet'tan) - 3dk'lik dosyalar."""

import json
import io
import numpy as np
import soundfile as sf
from pathlib import Path

OUTPUT_DIR = Path("data/test_audio")
SR = 16000
SILENCE_SAMPLES = 8000  # 0.5s
TARGET_DURATION = 180   # 3 dakika

print("FLEURS parquet okunuyor...")
import pandas as pd
df = pd.read_parquet("data/test_audio/fleurs_tr_test.parquet")
print(f"  {len(df)} klip yuklendi")

# Eski dosyalari temizle
for old in OUTPUT_DIR.glob("fleurs_real_*.wav"):
    old.unlink()
for old in OUTPUT_DIR.glob("fleurs_real_*.txt"):
    old.unlink()

manifest = []
file_idx = 0
audio_parts = []
texts = []
current_duration = 0.0

for _, row in df.iterrows():
    audio_data = row["audio"]
    audio_bytes = audio_data["bytes"]
    audio_array, sample_rate = sf.read(io.BytesIO(audio_bytes))

    if audio_array.ndim > 1:
        audio_array = audio_array.mean(axis=1)

    if sample_rate != SR:
        ratio = SR / sample_rate
        new_len = int(len(audio_array) * ratio)
        indices = np.linspace(0, len(audio_array) - 1, new_len).astype(int)
        audio_array = audio_array[indices]

    clip_duration = len(audio_array) / SR
    audio_parts.append(audio_array.astype(np.float32))
    audio_parts.append(np.zeros(SILENCE_SAMPLES, dtype=np.float32))
    current_duration += clip_duration + 0.5

    text = row.get("transcription", "")
    if text:
        texts.append(text.strip())

    # 3dk'ya ulasinca dosya kaydet
    if current_duration >= TARGET_DURATION:
        file_idx += 1
        combined = np.concatenate(audio_parts)
        duration = len(combined) / SR

        name = f"fleurs_real_{file_idx}"
        wav_path = OUTPUT_DIR / f"{name}.wav"
        txt_path = OUTPUT_DIR / f"{name}.txt"

        sf.write(str(wav_path), combined, SR, subtype="PCM_16")
        txt_path.write_text(" ".join(texts), encoding="utf-8")

        manifest.append({
            "name": name,
            "wav": str(wav_path),
            "txt": str(txt_path),
            "duration_s": round(duration, 1),
            "clips": len(texts),
            "source": "google/fleurs tr_tr test (real speech)",
        })
        print(f"  {name}: {duration:.0f}s ({len(texts)} klip)")

        # Reset
        audio_parts = []
        texts = []
        current_duration = 0.0

        if file_idx >= 5:
            break

# Manifest kaydet
manifest_path = OUTPUT_DIR / "manifest.json"
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

print(f"\nToplam: {len(manifest)} gercek ses test dosyasi")
total_dur = sum(m["duration_s"] for m in manifest)
print(f"Toplam sure: {total_dur:.0f}s ({total_dur/60:.1f}dk)")
