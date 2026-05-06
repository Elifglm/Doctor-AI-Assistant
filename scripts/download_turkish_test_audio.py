"""
Turkish ASR Test Audio Downloader
=================================
Downloads Turkish audio clips from public datasets (FLEURS, Common Voice,
MediaSpeech) and concatenates short clips into 3+ minute test files with
ground-truth transcriptions.

Usage:
    pip install datasets soundfile pydub
    python scripts/download_turkish_test_audio.py

Output:
    data/test_audio/
        test_1_fleurs.wav          (~3-4 min)
        test_1_fleurs.txt          (ground truth transcription)
        test_2_fleurs.wav
        test_2_fleurs.txt
        test_3_mediaspeech.wav
        test_3_mediaspeech.txt
        test_4_commonvoice.wav
        test_4_commonvoice.txt
        test_5_commonvoice.wav
        test_5_commonvoice.txt
        manifest.json              (metadata for all files)
"""

import json
import os
import struct
import sys
import wave
from pathlib import Path

# Minimum duration target per concatenated file (seconds)
MIN_DURATION_SEC = 180  # 3 minutes


def ensure_output_dir() -> Path:
    out = Path(__file__).resolve().parent.parent / "data" / "test_audio"
    out.mkdir(parents=True, exist_ok=True)
    return out


def load_fleurs_turkish():
    """Load Google FLEURS Turkish split (CC-BY-4.0)."""
    from datasets import load_dataset

    print("[1/3] Loading FLEURS Turkish (tr_tr) ...")
    ds = load_dataset("google/fleurs", "tr_tr", split="test", trust_remote_code=True)
    return ds


def load_mediaspeech_turkish():
    """Load MediaSpeech / Open SLR108 Turkish (CC-BY-4.0)."""
    from datasets import load_dataset

    print("[2/3] Loading MediaSpeech Turkish (Open SLR108) ...")
    try:
        ds = load_dataset(
            "emre/Open_SLR108_Turkish_10_hours", split="train", trust_remote_code=True
        )
        return ds
    except Exception as e:
        print(f"  WARNING: MediaSpeech load failed ({e}), skipping.")
        return None


def load_commonvoice_turkish():
    """Load Mozilla Common Voice Turkish (CC-0).
    Requires accepting terms at https://huggingface.co/datasets/mozilla-foundation/common_voice_17_0
    """
    from datasets import load_dataset

    print("[3/3] Loading Common Voice 17.0 Turkish ...")
    try:
        ds = load_dataset(
            "mozilla-foundation/common_voice_17_0",
            "tr",
            split="test",
            trust_remote_code=True,
        )
        return ds
    except Exception as e:
        print(f"  WARNING: Common Voice load failed ({e}).")
        print(
            "  You may need to accept terms at: "
            "https://huggingface.co/datasets/mozilla-foundation/common_voice_17_0"
        )
        print("  Falling back to FLEURS extra splits...")
        return None


def extract_audio_and_text(sample, dataset_name: str):
    """Extract (audio_array, sampling_rate, transcription) from a dataset sample."""
    if dataset_name == "fleurs":
        audio = sample["audio"]
        return audio["array"], audio["sampling_rate"], sample["transcription"]
    elif dataset_name == "mediaspeech":
        audio = sample["audio"]
        text_key = "text" if "text" in sample else "sentence" if "sentence" in sample else "transcription"
        return audio["array"], audio["sampling_rate"], sample.get(text_key, "")
    elif dataset_name == "commonvoice":
        audio = sample["audio"]
        return audio["array"], audio["sampling_rate"], sample["sentence"]
    else:
        raise ValueError(f"Unknown dataset: {dataset_name}")


def concatenate_to_wav(
    samples, dataset_name: str, output_path: Path, txt_path: Path, target_sr: int = 16000
):
    """Concatenate samples into a single WAV file >= MIN_DURATION_SEC.
    Returns (duration_sec, num_clips, transcription).
    """
    import numpy as np

    all_audio = []
    all_text = []
    total_samples = 0

    for sample in samples:
        try:
            audio_array, sr, text = extract_audio_and_text(sample, dataset_name)
        except Exception:
            continue

        audio_np = np.array(audio_array, dtype=np.float32)

        # Resample if needed
        if sr != target_sr:
            try:
                import librosa
                audio_np = librosa.resample(audio_np, orig_sr=sr, target_sr=target_sr)
            except ImportError:
                # Simple linear interpolation fallback
                ratio = target_sr / sr
                new_len = int(len(audio_np) * ratio)
                indices = np.linspace(0, len(audio_np) - 1, new_len)
                audio_np = np.interp(indices, np.arange(len(audio_np)), audio_np)

        all_audio.append(audio_np)
        # Add small silence between clips (0.5 sec)
        all_audio.append(np.zeros(int(target_sr * 0.5), dtype=np.float32))
        all_text.append(text.strip())
        total_samples += len(audio_np) + int(target_sr * 0.5)

        duration = total_samples / target_sr
        if duration >= MIN_DURATION_SEC:
            break

    if not all_audio:
        return 0, 0, ""

    combined = np.concatenate(all_audio)
    duration_sec = len(combined) / target_sr

    # Write WAV (16-bit PCM)
    pcm_data = (combined * 32767).astype(np.int16)
    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(target_sr)
        wf.writeframes(pcm_data.tobytes())

    # Write transcription
    full_text = " ".join(all_text)
    txt_path.write_text(full_text, encoding="utf-8")

    return duration_sec, len(all_text), full_text


def main():
    import numpy as np

    output_dir = ensure_output_dir()
    manifest = []
    file_index = 1

    # --- FLEURS (2 files from different parts of the dataset) ---
    fleurs = load_fleurs_turkish()
    if fleurs is not None and len(fleurs) > 0:
        total = len(fleurs)
        # Split dataset into 2 non-overlapping chunks
        mid = total // 2
        for chunk_start, chunk_end, label in [
            (0, mid, "fleurs_part1"),
            (mid, total, "fleurs_part2"),
        ]:
            wav_path = output_dir / f"test_{file_index}_fleurs.wav"
            txt_path = output_dir / f"test_{file_index}_fleurs.txt"

            print(f"  Building test_{file_index}_fleurs from indices {chunk_start}-{chunk_end} ...")
            samples = [fleurs[i] for i in range(chunk_start, min(chunk_end, total))]
            dur, n_clips, text = concatenate_to_wav(
                samples, "fleurs", wav_path, txt_path
            )

            if dur > 0:
                entry = {
                    "file": wav_path.name,
                    "transcript_file": txt_path.name,
                    "duration_sec": round(dur, 1),
                    "num_clips": n_clips,
                    "source": "google/fleurs tr_tr",
                    "license": "CC-BY-4.0",
                }
                manifest.append(entry)
                print(f"    => {wav_path.name}: {dur:.1f}s ({n_clips} clips)")
                file_index += 1

    # --- MediaSpeech (1 file) ---
    mediaspeech = load_mediaspeech_turkish()
    if mediaspeech is not None and len(mediaspeech) > 0:
        wav_path = output_dir / f"test_{file_index}_mediaspeech.wav"
        txt_path = output_dir / f"test_{file_index}_mediaspeech.txt"

        print(f"  Building test_{file_index}_mediaspeech ...")
        samples = [mediaspeech[i] for i in range(len(mediaspeech))]
        dur, n_clips, text = concatenate_to_wav(
            samples, "mediaspeech", wav_path, txt_path
        )
        if dur > 0:
            entry = {
                "file": wav_path.name,
                "transcript_file": txt_path.name,
                "duration_sec": round(dur, 1),
                "num_clips": n_clips,
                "source": "emre/Open_SLR108_Turkish_10_hours",
                "license": "CC-BY-4.0",
            }
            manifest.append(entry)
            print(f"    => {wav_path.name}: {dur:.1f}s ({n_clips} clips)")
            file_index += 1

    # --- Common Voice (2 files from different parts) ---
    cv = load_commonvoice_turkish()
    if cv is not None and len(cv) > 0:
        total = len(cv)
        mid = total // 2
        for chunk_start, chunk_end, label in [
            (0, mid, "cv_part1"),
            (mid, total, "cv_part2"),
        ]:
            wav_path = output_dir / f"test_{file_index}_commonvoice.wav"
            txt_path = output_dir / f"test_{file_index}_commonvoice.txt"

            print(f"  Building test_{file_index}_commonvoice from indices {chunk_start}-{chunk_end} ...")
            samples = [cv[i] for i in range(chunk_start, min(chunk_end, total))]
            dur, n_clips, text = concatenate_to_wav(
                samples, "commonvoice", wav_path, txt_path
            )

            if dur > 0:
                entry = {
                    "file": wav_path.name,
                    "transcript_file": txt_path.name,
                    "duration_sec": round(dur, 1),
                    "num_clips": n_clips,
                    "source": "mozilla-foundation/common_voice_17_0 tr",
                    "license": "CC-0",
                }
                manifest.append(entry)
                print(f"    => {wav_path.name}: {dur:.1f}s ({n_clips} clips)")
                file_index += 1
    else:
        # Fallback: use FLEURS dev/validation splits for extra files
        print("  Falling back to FLEURS dev split for additional files...")
        from datasets import load_dataset

        for split_name in ["validation", "train"]:
            if file_index > 5:
                break
            try:
                ds_extra = load_dataset(
                    "google/fleurs", "tr_tr", split=split_name, trust_remote_code=True
                )
            except Exception:
                continue

            wav_path = output_dir / f"test_{file_index}_fleurs_{split_name}.wav"
            txt_path = output_dir / f"test_{file_index}_fleurs_{split_name}.txt"

            print(f"  Building test_{file_index}_fleurs_{split_name} ...")
            samples = [ds_extra[i] for i in range(len(ds_extra))]
            dur, n_clips, text = concatenate_to_wav(
                samples, "fleurs", wav_path, txt_path
            )
            if dur > 0:
                entry = {
                    "file": wav_path.name,
                    "transcript_file": txt_path.name,
                    "duration_sec": round(dur, 1),
                    "num_clips": n_clips,
                    "source": f"google/fleurs tr_tr ({split_name})",
                    "license": "CC-BY-4.0",
                }
                manifest.append(entry)
                print(f"    => {wav_path.name}: {dur:.1f}s ({n_clips} clips)")
                file_index += 1

    # --- Write manifest ---
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"Done! {len(manifest)} test files created in: {output_dir}")
    print(f"Manifest: {manifest_path}")
    for m in manifest:
        print(f"  {m['file']}: {m['duration_sec']}s, {m['num_clips']} clips, {m['source']}")


if __name__ == "__main__":
    main()
