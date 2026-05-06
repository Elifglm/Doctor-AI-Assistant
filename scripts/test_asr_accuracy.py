"""ASR dogruluk testi: test dosyalari ile pipeline calistir, WER olc."""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os
os.chdir(str(Path(__file__).resolve().parents[1]))

TEST_DIR = Path("data/test_audio")
RESULTS_DIR = Path("data/test_results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def compute_wer(reference: str, hypothesis: str) -> dict:
    """Word Error Rate hesapla."""
    ref_words = reference.lower().split()
    hyp_words = hypothesis.lower().split()

    # Levenshtein mesafesi (kelime seviyesi)
    d = [[0] * (len(hyp_words) + 1) for _ in range(len(ref_words) + 1)]
    for i in range(len(ref_words) + 1):
        d[i][0] = i
    for j in range(len(hyp_words) + 1):
        d[0][j] = j

    for i in range(1, len(ref_words) + 1):
        for j in range(1, len(hyp_words) + 1):
            if ref_words[i-1] == hyp_words[j-1]:
                d[i][j] = d[i-1][j-1]
            else:
                d[i][j] = min(
                    d[i-1][j] + 1,      # silme
                    d[i][j-1] + 1,      # ekleme
                    d[i-1][j-1] + 1,    # degistirme
                )

    errors = d[len(ref_words)][len(hyp_words)]
    total = len(ref_words)
    wer = errors / total if total > 0 else 0.0

    return {
        "wer": round(wer * 100, 2),
        "errors": errors,
        "ref_words": total,
        "hyp_words": len(hyp_words),
    }


async def test_single(pipeline, wav_path: str, ref_text: str, name: str) -> dict:
    """Tek dosya test et."""
    print(f"\n{'='*60}")
    print(f"Test: {name}")
    print(f"WAV: {wav_path}")

    t0 = time.time()

    async def progress(stage, msg, prog):
        pass  # sessiz

    result = await pipeline.process(wav_path, progress)
    elapsed = time.time() - t0

    # Transkripsiyon birlestir
    segments = result.get("segments", [])
    hyp_text = " ".join(seg.get("text", "") for seg in segments)

    # WER hesapla
    wer_result = compute_wer(ref_text, hyp_text)

    # Speaker dagilimi
    speakers = {}
    for seg in segments:
        spk = seg.get("speaker_label", "?")
        speakers[spk] = speakers.get(spk, 0) + 1

    duration = result.get("metadata", {}).get("audio_duration_seconds", 0)
    timings = result.get("metadata", {}).get("processing_times", {})

    test_result = {
        "name": name,
        "duration_s": round(duration, 1),
        "processing_s": round(elapsed, 1),
        "rtf": round(elapsed / duration, 3) if duration > 0 else 0,
        "segments": len(segments),
        "speakers": speakers,
        "wer": wer_result["wer"],
        "wer_errors": wer_result["errors"],
        "wer_ref_words": wer_result["ref_words"],
        "timings": timings,
        "reference": ref_text[:200] + "...",
        "hypothesis": hyp_text[:200] + "...",
    }

    print(f"  Sure: {duration:.0f}s ses, {elapsed:.1f}s islem (RTF={test_result['rtf']:.3f})")
    print(f"  Segment: {len(segments)}, Speakers: {speakers}")
    print(f"  WER: {wer_result['wer']:.1f}% ({wer_result['errors']} hata / {wer_result['ref_words']} kelime)")
    print(f"  Timings: {timings}")

    # Ilk birkac segment goster
    for seg in segments[:3]:
        spk = seg.get("speaker_label", "?")
        txt = seg.get("text", "")[:80]
        print(f"  [{spk}] {txt}")
    if len(segments) > 3:
        print(f"  ... +{len(segments)-3} segment daha")

    return test_result


async def main():
    from apps.backend.src.asr.pipeline import BatchASRPipeline
    from apps.backend.src.asr.settings import ASRSettings

    # Manifest oku
    manifest_path = TEST_DIR / "manifest.json"
    if not manifest_path.exists():
        print("manifest.json bulunamadi! Once test dosyalarini olusturun.")
        return

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    if not manifest:
        print("Manifest bos!")
        return

    print(f"Test dosyalari: {len(manifest)}")
    for m in manifest:
        print(f"  {m['name']}: {m['duration_s']}s")

    # Pipeline olustur
    settings = ASRSettings()
    pipeline = BatchASRPipeline(settings)

    all_results = []

    for m in manifest:
        wav_path = m["wav"]
        txt_path = m["txt"]

        if not Path(wav_path).exists():
            print(f"  ATLANIR: {wav_path} bulunamadi")
            continue

        ref_text = Path(txt_path).read_text(encoding="utf-8").strip()
        result = await test_single(pipeline, wav_path, ref_text, m["name"])
        all_results.append(result)

    # Ozet
    print(f"\n{'='*60}")
    print("OZET")
    print(f"{'='*60}")

    total_duration = sum(r["duration_s"] for r in all_results)
    total_processing = sum(r["processing_s"] for r in all_results)
    avg_wer = sum(r["wer"] for r in all_results) / len(all_results) if all_results else 0

    print(f"Toplam ses: {total_duration:.0f}s ({total_duration/60:.1f}dk)")
    print(f"Toplam islem: {total_processing:.0f}s ({total_processing/60:.1f}dk)")
    print(f"Ortalama RTF: {total_processing/total_duration:.3f}" if total_duration > 0 else "")
    print(f"Ortalama WER: {avg_wer:.1f}%")
    print()

    for r in all_results:
        print(f"  {r['name']}: WER={r['wer']:.1f}%, {r['duration_s']}s ses, {r['processing_s']}s islem")

    # Sonuclari kaydet
    results_path = RESULTS_DIR / "accuracy_report.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump({
            "summary": {
                "total_audio_s": round(total_duration, 1),
                "total_processing_s": round(total_processing, 1),
                "avg_rtf": round(total_processing / total_duration, 3) if total_duration > 0 else 0,
                "avg_wer": round(avg_wer, 1),
                "test_count": len(all_results),
            },
            "results": all_results,
        }, f, ensure_ascii=False, indent=2)

    print(f"\nRapor: {results_path}")


if __name__ == "__main__":
    asyncio.run(main())
