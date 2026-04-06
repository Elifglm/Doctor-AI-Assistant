"""Ses isleme yardimcilari: audio biriktirici ve dosya dogrulama."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import tempfile
from pathlib import Path

from apps.backend.src.asr.exceptions import AudioConversionError, AudioValidationError

logger = logging.getLogger(__name__)

# FFmpeg path — Windows WinGet kurulumunu auto-detect
import glob as _glob

FFMPEG_PATH = "ffmpeg"
_ffmpeg_pattern = os.path.expandvars(
    r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"
    r"\Gyan.FFmpeg_Microsoft.Winget.Source_*"
    r"\ffmpeg-*-full_build\bin\ffmpeg.exe"
)
_ffmpeg_matches = _glob.glob(_ffmpeg_pattern)
if _ffmpeg_matches:
    FFMPEG_PATH = _ffmpeg_matches[0]
    _ffmpeg_dir = os.path.dirname(FFMPEG_PATH)
    if _ffmpeg_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")


class AudioAccumulator:
    """WebM/Opus chunk'lari biriktirir, WAV olarak kaydeder.

    Kayit sirasinda chunk'lar add_raw() ile biriktirilir.
    Kayit bitince save_wav() ile FFmpeg'e tek seferde donusturulur.
    """

    def __init__(self, max_duration_s: float = 3600.0) -> None:
        self._max_duration_s = max_duration_s
        self._raw_chunks: list[bytes] = []
        self._total_bytes: int = 0

    @property
    def has_data(self) -> bool:
        return self._total_bytes > 0

    def add_raw(self, webm_data: bytes) -> None:
        """Ham WebM/Opus chunk ekle."""
        self._raw_chunks.append(webm_data)
        self._total_bytes += len(webm_data)

    async def save_wav(self, path: str) -> str:
        """Biriktirilmis WebM chunk'lari FFmpeg ile WAV'a donustur.

        Args:
            path: Cikti WAV dosyasi yolu

        Returns:
            Kaydedilen WAV dosyasinin yolu

        Raises:
            AudioConversionError: FFmpeg basarisiz olursa
        """
        if not self._raw_chunks:
            raise AudioValidationError("Kaydedilecek ses verisi yok")

        Path(path).parent.mkdir(parents=True, exist_ok=True)

        # Ham WebM'i gecici dosyaya yaz
        temp_webm = tempfile.NamedTemporaryFile(
            suffix=".webm", delete=False, dir=str(Path(path).parent)
        )
        try:
            for chunk in self._raw_chunks:
                temp_webm.write(chunk)
            temp_webm.close()

            # FFmpeg ile WAV'a donustur (16kHz mono PCM)
            cmd = [
                FFMPEG_PATH, "-y",
                "-i", temp_webm.name,
                "-ar", "16000",
                "-ac", "1",
                "-c:a", "pcm_s16le",
                path,
            ]
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, timeout=120
            )
            if result.returncode != 0:
                error_msg = result.stderr.decode("utf-8", errors="replace")
                raise AudioConversionError(
                    f"FFmpeg donusumu basarisiz: {error_msg[:1000]}"
                )

            logger.info("WAV kaydedildi: %s (%d chunk, %d bytes)",
                        path, len(self._raw_chunks), self._total_bytes)
            return path
        finally:
            try:
                os.unlink(temp_webm.name)
            except OSError:
                pass

    def reset(self) -> None:
        """Tum biriktirilmis veriyi temizle."""
        self._raw_chunks.clear()
        self._total_bytes = 0


def load_and_validate_audio(
    path: str, supported_formats: list[str] | None = None
) -> float:
    """Ses dosyasini dogrula ve suresini dondur (saniye).

    Raises:
        AudioValidationError: Dosya gecersizse
    """
    file_path = Path(path)
    if not file_path.exists():
        raise AudioValidationError(f"Ses dosyasi bulunamadi: {path}")

    if supported_formats and file_path.suffix.lower() not in supported_formats:
        raise AudioValidationError(
            f"Desteklenmeyen format: {file_path.suffix}"
        )

    if file_path.stat().st_size == 0:
        raise AudioValidationError(f"Bos ses dosyasi: {path}")

    # Sure hesapla
    try:
        import wave
        with wave.open(str(file_path), "rb") as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:
        try:
            cmd = [
                FFMPEG_PATH.replace("ffmpeg", "ffprobe"),
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                str(file_path),
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=10)
            if result.returncode == 0:
                return float(result.stdout.decode().strip())
        except Exception:
            pass

    raise AudioValidationError(f"Ses suresi alinamadi: {path}")
