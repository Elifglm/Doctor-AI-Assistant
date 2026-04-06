"""Segment formatlama - WhisperX ciktisini DB-uyumlu formata donusturur."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

logger = logging.getLogger(__name__)


class SegmentOutput(TypedDict):
    """audio_handler._save_segments() ile uyumlu segment formati.

    Mevcut pipeline 'start'/'end' key'leri uretir,
    audio_handler bunlari 'start_time'/'end_time'a mapler.
    """

    text: str
    speaker: str         # "SPEAKER_00", "SPEAKER_01"
    speaker_label: str   # "Doktor", "Hasta"
    start: float         # saniye
    end: float           # saniye
    words: list[dict]    # kelime seviyesi timing/confidence


def format_segments(
    raw_result: dict,
    default_labels: dict[str, str] | None = None,
) -> list[SegmentOutput]:
    """WhisperX ciktisini DB-uyumlu segment listesine donustur.

    Args:
        raw_result: WhisperX aligned + diarized result dict
        default_labels: Konusmaci etiket haritasi (SPEAKER_00 -> "Doktor")

    Returns:
        SegmentOutput listesi
    """
    if default_labels is None:
        default_labels = {"SPEAKER_00": "Doktor", "SPEAKER_01": "Hasta"}

    segments: list[SegmentOutput] = []

    for seg in raw_result.get("segments", []):
        text = seg.get("text", "").strip()
        if not text:
            continue

        speaker = seg.get("speaker", "SPEAKER_00")
        speaker_label = seg.get(
            "speaker_label",
            default_labels.get(speaker, speaker),
        )

        # Kelime seviyesi veri
        words = seg.get("words", [])
        formatted_words = _format_words(words)

        segments.append(
            SegmentOutput(
                text=text,
                speaker=speaker,
                speaker_label=speaker_label,
                start=round(seg.get("start", 0.0), 3),
                end=round(seg.get("end", 0.0), 3),
                words=formatted_words,
            )
        )

    logger.info("Formatlandi: %d segment", len(segments))
    return segments


def build_full_text(segments: list[SegmentOutput]) -> str:
    """Segment'lerden tam metin olustur (konusmaci etiketli)."""
    parts: list[str] = []
    current_speaker = ""

    for seg in segments:
        if seg["speaker_label"] != current_speaker:
            current_speaker = seg["speaker_label"]
            parts.append(f"\n{current_speaker}: {seg['text']}")
        else:
            parts.append(seg["text"])

    return " ".join(parts).strip()


def build_metadata(
    audio_duration: float,
    timings: dict[str, float],
    models: dict[str, str],
    num_segments: int,
    num_speakers: int = 2,
) -> dict[str, Any]:
    """Pipeline metadata dict olustur."""
    return {
        "audio_duration_seconds": round(audio_duration, 2),
        "num_segments": num_segments,
        "num_speakers": num_speakers,
        "language": "tr",
        "models": models,
        "processing_times": timings,
    }


def _format_words(words: list[dict]) -> list[dict]:
    """Kelime listesini temizle ve standartlastir."""
    formatted = []
    for w in words:
        formatted.append({
            "word": w.get("word", ""),
            "start": round(w.get("start", 0.0), 3),
            "end": round(w.get("end", 0.0), 3),
            "score": round(w.get("score", 0.0), 3),
            "speaker": w.get("speaker", ""),
        })
    return formatted
