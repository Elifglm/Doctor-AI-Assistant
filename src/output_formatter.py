"""JSON/TXT cikti formatlama modulu."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from config.settings import OutputSettings

logger = logging.getLogger(__name__)


class OutputFormatter:
    """Transkripsiyon sonuclarini JSON ve TXT formatinda kaydet."""

    def __init__(self, settings: OutputSettings):
        self.settings = settings

    def format_result(self, segments: list[dict], metadata: dict) -> dict:
        """
        Tam JSON yapisi olustur.

        Args:
            segments: Konusmaci etiketli segmentler.
            metadata: Ust veri (dosya adi, sure, dil vb.).

        Returns:
            Formatlanmis sonuc sozlugu.
        """
        formatted_segments = []
        for i, seg in enumerate(segments):
            formatted_seg = {
                "id": i,
                "start": round(seg.get("start", 0.0), 3),
                "end": round(seg.get("end", 0.0), 3),
                "text": seg.get("text", "").strip(),
                "speaker": seg.get("speaker", "UNKNOWN"),
                "speaker_label": seg.get("speaker_label", "Bilinmiyor"),
            }

            if "words" in seg:
                formatted_seg["words"] = [
                    {
                        "word": w.get("word", ""),
                        "start": round(w.get("start", 0.0), 3),
                        "end": round(w.get("end", 0.0), 3),
                        "score": round(w.get("score", 0.0), 3),
                    }
                    for w in seg["words"]
                ]

            formatted_segments.append(formatted_seg)

        full_text = self._build_full_text(formatted_segments)

        metadata["created_at"] = datetime.now(timezone.utc).isoformat()

        return {
            "version": "1.0.0",
            "metadata": metadata,
            "segments": formatted_segments,
            "full_text": full_text,
        }

    def save_json(self, result: dict, output_path: str) -> str:
        """Sonucu JSON dosyasina kaydet."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        logger.info("JSON kaydedildi: %s", path)
        return str(path)

    def save_txt(self, result: dict, output_path: str) -> str:
        """Sonucu okunabilir TXT dosyasina kaydet."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        lines = []
        meta = result.get("metadata", {})
        lines.append(f"Dosya: {meta.get('audio_file', 'Bilinmiyor')}")
        lines.append(f"Sure: {meta.get('audio_duration_seconds', 0):.1f} saniye")
        lines.append(f"Konusmaci sayisi: {meta.get('num_speakers', 0)}")
        lines.append(f"Tarih: {meta.get('created_at', '')}")
        lines.append("=" * 60)
        lines.append("")

        for seg in result.get("segments", []):
            start_ts = self._format_timestamp(seg["start"])
            end_ts = self._format_timestamp(seg["end"])
            label = seg.get("speaker_label", "Bilinmiyor")
            text = seg.get("text", "")
            lines.append(f"[{start_ts} - {end_ts}] {label}: {text}")

        lines.append("")
        lines.append("=" * 60)
        lines.append("Tam Metin:")
        lines.append(result.get("full_text", ""))

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        logger.info("TXT kaydedildi: %s", path)
        return str(path)

    def _build_full_text(self, segments: list[dict]) -> str:
        """Konusmaci etiketli tam metin olustur."""
        lines = []
        current_speaker = None

        for seg in segments:
            label = seg.get("speaker_label", "Bilinmiyor")
            text = seg.get("text", "").strip()

            if not text:
                continue

            if label != current_speaker:
                current_speaker = label
                lines.append(f"{label}: {text}")
            else:
                lines.append(f"  {text}")

        return "\n".join(lines)

    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        """Saniyeyi HH:MM:SS formatina cevir."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
