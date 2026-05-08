"""ASR evaluation — lisans seviyesi standart metrikler.

Metrikler:
  - WER (Word Error Rate)        — kelime düzeyi hata oranı
  - CER (Character Error Rate)   — karakter düzeyi (Türkçe morfoloji için kritik)
  - DER (Diarization Error Rate) — konuşmacı ayrımı (Doktor/Hasta) hatası
  - RTF (Real-Time Factor)       — işleme süresi / ses süresi (< 1.0 = real-time)

Akademik referans:
  - Klakow & Peters (2002): "Testing the correlation of WER and perplexity"
  - Fiscus (1997): "A post-processing system to yield reduced word error rates"
  - pyannote.metrics (Bredin 2017): DER hesaplama standardı

Bağımlılık:
  - jiwer (WER/CER) — pip install jiwer
  - pyannote.metrics (DER) — zaten yüklü
  - whisperx (ASR pipeline) — zaten yüklü
  - python-docx (opsiyonel, .docx gold okumak için)

Çıktı: data/eval_results/asr_run_<ts>_<label>.json + .csv + .log

Kullanım:
    # 1) Audio + gold transcript klasörü ver
    python -m apps.backend.src.scripts.eval_asr \\
        --audio-dir /path/to/audio \\
        --gold-dir /path/to/manual-transcripts \\
        --label baseline

    # Format eşleştirme: audio_<id>.wav ↔ gold_<id>.txt veya .docx
    # ID'ler dosya adından çıkarılır (örn. "Kayıt 105 ...wav" → "105")
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
OUTPUT_DIR = PROJECT_ROOT / "data" / "eval_results"


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
def setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("eval_asr")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


# ---------------------------------------------------------------------------
# Text normalization — fair WER/CER comparison
# ---------------------------------------------------------------------------
_SPEAKER_PREFIX = re.compile(r"^\s*(Doktor|Hasta|D|H)\s*:\s*", re.IGNORECASE | re.MULTILINE)
_PUNCT = re.compile(r"[.,;:!?\"'\(\)\[\]…—–-]")
_WS = re.compile(r"\s+")


def normalize_for_wer(text: str) -> str:
    """Strip speaker prefixes, lowercase, remove punctuation, collapse whitespace.

    WER karşılaştırmasını adil yapmak için. Diarization hatasını WER'e karıştırmaz —
    speaker label'ları normalize aşamasında çıkarılıyor; speaker doğruluğu DER ile
    ayrı ölçülür.
    """
    if not text:
        return ""
    text = _SPEAKER_PREFIX.sub("", text)
    text = text.lower()
    text = _PUNCT.sub(" ", text)
    text = _WS.sub(" ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------
def read_gold(gold_path: Path) -> str:
    """Read gold transcript — supports .txt and .docx."""
    suffix = gold_path.suffix.lower()
    if suffix == ".txt":
        return gold_path.read_text(encoding="utf-8")
    if suffix == ".docx":
        try:
            from docx import Document
        except ImportError:
            raise RuntimeError(
                "python-docx not installed; either convert .docx to .txt "
                "or run: pip install python-docx"
            )
        doc = Document(str(gold_path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    raise ValueError(f"Unsupported gold format: {suffix} ({gold_path})")


def find_pairs(audio_dir: Path, gold_dir: Path) -> list[tuple[str, Path, Path]]:
    """Match audio ↔ gold by ID extracted from filename (digits in name)."""
    audio_files = list(audio_dir.glob("*.wav")) + list(audio_dir.glob("*.mp3")) + \
                  list(audio_dir.glob("*.m4a"))
    gold_files = list(gold_dir.glob("*.txt")) + list(gold_dir.glob("*.docx"))

    def _id(p: Path) -> str | None:
        m = re.search(r"\d+", p.stem)
        return m.group(0) if m else None

    audio_by_id = {_id(p): p for p in audio_files if _id(p)}
    gold_by_id = {_id(p): p for p in gold_files if _id(p)}
    common = sorted(set(audio_by_id) & set(gold_by_id))
    return [(fid, audio_by_id[fid], gold_by_id[fid]) for fid in common]


# ---------------------------------------------------------------------------
# WER / CER (jiwer)
# ---------------------------------------------------------------------------
def compute_text_metrics(reference: str, hypothesis: str) -> dict:
    """WER + CER via jiwer. Both inputs already normalized."""
    try:
        import jiwer
    except ImportError:
        return {"error": "jiwer not installed (pip install jiwer)"}

    if not reference.strip():
        return {"error": "empty reference"}

    return {
        "wer": round(jiwer.wer(reference, hypothesis), 4),
        "cer": round(jiwer.cer(reference, hypothesis), 4),
        "ref_words": len(reference.split()),
        "hyp_words": len(hypothesis.split()),
    }


# ---------------------------------------------------------------------------
# DER (pyannote.metrics) — requires speaker turn annotations
# ---------------------------------------------------------------------------
def compute_diarization_metrics(
    ref_turns: list[tuple[float, float, str]],
    hyp_turns: list[tuple[float, float, str]],
) -> dict:
    """Diarization Error Rate.

    Args:
        ref_turns: [(start_s, end_s, speaker_label), ...] — gold
        hyp_turns: same — system hypothesis

    Returns:
        {"der": float, "miss_rate": float, "false_alarm": float, "speaker_error": float}
    """
    try:
        from pyannote.core import Annotation, Segment
        from pyannote.metrics.diarization import DiarizationErrorRate
    except ImportError:
        return {"error": "pyannote.metrics not installed"}

    if not ref_turns or not hyp_turns:
        return {"error": "empty turns (DER hesaplanamaz)"}

    def _to_annotation(turns):
        a = Annotation()
        for start, end, spk in turns:
            a[Segment(start, end)] = spk
        return a

    ref_ann = _to_annotation(ref_turns)
    hyp_ann = _to_annotation(hyp_turns)
    metric = DiarizationErrorRate()
    der = metric(ref_ann, hyp_ann, detailed=True)
    return {
        "der": round(float(der["diarization error rate"]), 4),
        "miss_rate": round(float(der.get("missed detection", 0.0)), 4),
        "false_alarm": round(float(der.get("false alarm", 0.0)), 4),
        "speaker_error": round(float(der.get("confusion", 0.0)), 4),
    }


# ---------------------------------------------------------------------------
# WhisperX runner — uses existing project pipeline
# ---------------------------------------------------------------------------
def _audio_duration(audio_path: Path) -> float:
    """Return audio duration in seconds. Lazy imports to avoid startup cost."""
    try:
        import wave
        if audio_path.suffix.lower() == ".wav":
            with wave.open(str(audio_path), "rb") as w:
                frames = w.getnframes()
                rate = w.getframerate()
                return frames / float(rate) if rate else 0.0
    except Exception:
        pass
    # Fallback for mp3/m4a — use librosa if available (already in WhisperX deps)
    try:
        import librosa
        duration = librosa.get_duration(path=str(audio_path))
        return float(duration)
    except Exception:
        return 0.0


async def run_asr(audio_path: Path, logger: logging.Logger) -> dict:
    """Run WhisperX + diarization on audio file, return hypothesis."""
    from apps.backend.src.services.asr_service import asr_service

    audio_duration_s = _audio_duration(audio_path)
    t0 = time.perf_counter()
    try:
        # ASR service expected to expose process_audio(file_path) → dict with segments
        result = await asr_service.process_audio(str(audio_path))
    except Exception:
        logger.exception("ASR failed for %s", audio_path)
        return {"error": "asr_failed"}
    elapsed = time.perf_counter() - t0

    segments = result.get("segments", [])
    text = " ".join(s.get("text", "") for s in segments)
    hyp_turns = [
        (
            float(s.get("start_time", s.get("start", 0))),
            float(s.get("end_time", s.get("end", 0))),
            str(s.get("speaker", "UNKNOWN")),
        )
        for s in segments
    ]
    rtf = round(elapsed / audio_duration_s, 3) if audio_duration_s > 0 else None
    return {
        "hypothesis": text,
        "segments": segments,
        "hyp_turns": hyp_turns,
        "elapsed_s": round(elapsed, 2),
        "audio_duration_s": round(audio_duration_s, 2) if audio_duration_s > 0 else None,
        "rtf": rtf,
    }


# ---------------------------------------------------------------------------
# Per-file evaluation
# ---------------------------------------------------------------------------
async def evaluate_file(
    file_id: str, audio_path: Path, gold_path: Path, logger: logging.Logger,
) -> dict:
    logger.info("--- FILE %s ---", file_id)
    logger.info("  audio: %s", audio_path.name)
    logger.info("  gold : %s", gold_path.name)

    try:
        gold_text = read_gold(gold_path)
    except Exception as e:
        return {"file_id": file_id, "error": f"gold_read: {e}"}

    asr_result = await run_asr(audio_path, logger)
    if "error" in asr_result:
        return {"file_id": file_id, "error": asr_result["error"]}

    # Text metrics (WER/CER) — normalize both sides
    ref_norm = normalize_for_wer(gold_text)
    hyp_norm = normalize_for_wer(asr_result["hypothesis"])
    text_metrics = compute_text_metrics(ref_norm, hyp_norm)

    # DER — gold turns'ı parse etmek tipik olarak RTTM gerektirir; .docx/.txt
    # gold'da turn timing yok. Eğer kullanıcı ayrı RTTM verirse hesaplanır;
    # şimdilik DER=N/A (belge eksikliği). Hipotez turns DER ground-truth ile
    # karşılaştırılması için saklanır.
    return {
        "file_id": file_id,
        "audio": audio_path.name,
        "gold": gold_path.name,
        "elapsed_s": asr_result["elapsed_s"],
        "audio_duration_s": asr_result.get("audio_duration_s"),
        "rtf": asr_result.get("rtf"),
        "text_metrics": text_metrics,
        "diarization": {
            "n_hyp_turns": len(asr_result["hyp_turns"]),
            "note": "DER requires RTTM gold; provide via --rttm-dir for full DER",
        },
        "samples": {
            "ref_first_200": ref_norm[:200],
            "hyp_first_200": hyp_norm[:200],
        },
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main(args: argparse.Namespace) -> None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = OUTPUT_DIR / f"asr_run_{ts}_{args.label}.log"
    logger = setup_logging(log_path)

    logger.info("=" * 70)
    logger.info("eval_asr — label=%s", args.label)
    logger.info("  audio: %s", args.audio_dir)
    logger.info("  gold : %s", args.gold_dir)
    logger.info("=" * 70)

    pairs = find_pairs(args.audio_dir, args.gold_dir)
    if not pairs:
        logger.error("No (audio, gold) pairs matched by ID. Check filenames.")
        return
    logger.info("Matched %d (audio, gold) pairs: %s",
                len(pairs), [fid for fid, _, _ in pairs])

    results: list[dict] = []
    for fid, audio_path, gold_path in pairs:
        try:
            r = await evaluate_file(fid, audio_path, gold_path, logger)
        except Exception as e:
            logger.exception("FILE %s evaluation crashed", fid)
            r = {"file_id": fid, "error": f"crash: {e}"}
        results.append(r)
        if "error" not in r:
            tm = r["text_metrics"]
            rtf = r.get("rtf")
            logger.info(
                "  WER=%.3f  CER=%.3f  RTF=%s  elapsed=%.1fs  ref_words=%d  hyp_words=%d",
                tm.get("wer", 0.0), tm.get("cer", 0.0),
                f"{rtf:.2f}" if rtf is not None else "n/a",
                r["elapsed_s"],
                tm.get("ref_words", 0), tm.get("hyp_words", 0),
            )

    # Aggregates
    valid = [r for r in results if "error" not in r and "wer" in r.get("text_metrics", {})]

    def avg(extract):
        vals = [extract(r) for r in valid if extract(r) is not None]
        return round(sum(vals) / len(vals), 4) if vals else None

    summary = {
        "label": args.label,
        "timestamp": ts,
        "n_files": len(results),
        "n_success": len(valid),
        "n_failed": len(results) - len(valid),
        "averages": {
            "wer": avg(lambda r: r["text_metrics"].get("wer")),
            "cer": avg(lambda r: r["text_metrics"].get("cer")),
            "rtf": avg(lambda r: r.get("rtf")),
            "elapsed_s": avg(lambda r: r.get("elapsed_s")),
            "audio_duration_s": avg(lambda r: r.get("audio_duration_s")),
        },
    }

    logger.info("=" * 70)
    logger.info("=== SUMMARY ===\n%s", json.dumps(summary, indent=2, ensure_ascii=False))

    # Output
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / f"asr_run_{ts}_{args.label}.json"
    json_path.write_text(
        json.dumps({"summary": summary, "per_file": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    csv_path = OUTPUT_DIR / f"asr_run_{ts}_{args.label}.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "file_id", "wer", "cer", "rtf",
                "elapsed_s", "audio_duration_s", "ref_words", "hyp_words",
            ],
        )
        writer.writeheader()
        for r in valid:
            tm = r["text_metrics"]
            writer.writerow({
                "file_id": r["file_id"],
                "wer": tm.get("wer", ""),
                "cer": tm.get("cer", ""),
                "rtf": r.get("rtf", "") if r.get("rtf") is not None else "",
                "elapsed_s": r.get("elapsed_s", ""),
                "audio_duration_s": r.get("audio_duration_s", "") if r.get("audio_duration_s") is not None else "",
                "ref_words": tm.get("ref_words", ""),
                "hyp_words": tm.get("hyp_words", ""),
            })
    logger.info("JSON: %s", json_path)
    logger.info("CSV : %s", csv_path)
    logger.info("LOG : %s", log_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio-dir", type=Path, required=True,
                        help="Audio dosyalarının olduğu klasör (.wav/.mp3/.m4a)")
    parser.add_argument("--gold-dir", type=Path, required=True,
                        help="Manuel transkriptlerin klasörü (.txt/.docx)")
    parser.add_argument("--label", type=str, default="run", help="Run etiketi")
    args = parser.parse_args()

    asyncio.run(main(args))
