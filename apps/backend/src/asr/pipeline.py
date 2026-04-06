"""Batch ASR Pipeline: transkripsiyon + diarization + post-processing."""

from __future__ import annotations

import asyncio
import gc
import logging
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from apps.backend.src.asr.audio_utils import load_and_validate_audio
from apps.backend.src.asr.diarizer import SpeakerDiarizer
from apps.backend.src.asr.exceptions import ASRError, BatchProcessingError
from apps.backend.src.asr.gpu_manager import ASRGPUManager
from apps.backend.src.asr.output_formatter import build_metadata
from apps.backend.src.asr.settings import ASRSettings

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str, float], Awaitable[None]] | None


class BatchASRPipeline:
    """Batch-only ASR pipeline: kaydet, sonra isle.

    Kullanim:
        pipeline = BatchASRPipeline(settings)
        result = await pipeline.process("recording.wav", progress_cb)
    """

    def __init__(self, settings: ASRSettings) -> None:
        self._settings = settings
        self._gpu = ASRGPUManager()

    @property
    def gpu_manager(self) -> ASRGPUManager:
        return self._gpu

    async def process(
        self,
        wav_path: str,
        progress_callback: ProgressCallback = None,
    ) -> dict:
        """Tam batch pipeline: transcribe + post-process + diarize.

        Args:
            wav_path: 16kHz mono WAV dosyasi yolu
            progress_callback: async(stage, message, progress)

        Returns:
            {"segments": list[dict], "metadata": dict}
        """
        timings: dict[str, float] = {}

        async def report(stage: str, message: str, progress: float) -> None:
            if progress_callback:
                await progress_callback(stage, message, progress)

        try:
            # Stage 0: Validate
            await report("Stage 0/4", "Ses dosyasi dogrulaniyor...", 0.0)
            duration = load_and_validate_audio(
                wav_path, self._settings.audio.supported_formats
            )
            logger.info("Ses dogrulandi: %.1f saniye", duration)

            # Stage 1: Transcription (faster-whisper sequential)
            await report("Stage 1/4", "Transkripsiyon...", 0.10)
            t0 = time.time()
            segments = await self._transcribe(wav_path)
            timings["transcription"] = round(time.time() - t0, 2)
            logger.info(
                "Transkripsiyon tamamlandi: %d segment, %.1fs",
                len(segments), timings["transcription"],
            )

            # Stage 2: Post-processing (Turkce duzeltme)
            await report("Stage 2/4", "Metin duzeltme...", 0.50)
            t0 = time.time()
            segments = await asyncio.to_thread(self._post_process, segments)
            timings["post_processing"] = round(time.time() - t0, 2)

            # Stage 3: Diarization (pyannote)
            await report("Stage 3/4", "Konusmaci ayristirma...", 0.55)
            t0 = time.time()
            segments = await self._diarize(wav_path, segments)
            timings["diarization"] = round(time.time() - t0, 2)
            logger.info("Diarization tamamlandi: %.1fs", timings["diarization"])

            # Finalize
            self._gpu.unload_all()
            self._gpu.cleanup()

            timings["total"] = round(sum(timings.values()), 2)
            metadata = build_metadata(
                audio_duration=duration,
                timings=timings,
                models={
                    "whisper": self._settings.transcription.model_name,
                    "diarization": self._settings.diarization.model_name,
                },
                num_segments=len(segments),
            )

            await report("Stage 4/4", "Islem tamamlandi!", 1.0)

            logger.info(
                "Pipeline tamamlandi: %d segment, %.1fs ses, %.1fs islem",
                len(segments), duration, timings["total"],
            )

            return {"segments": segments, "metadata": metadata}

        except ASRError:
            self._gpu.unload_all()
            self._gpu.cleanup()
            raise
        except Exception as e:
            self._gpu.unload_all()
            self._gpu.cleanup()
            raise BatchProcessingError(f"Pipeline hatasi: {e}") from e

    # ── Transcription ───────────────────────────────────────────────

    async def _transcribe(self, wav_path: str) -> list[dict]:
        """faster-whisper sequential model.transcribe() — dogruluk odakli.

        condition_on_previous_text=True ile baglam tasinir.
        initial_prompt ile tibbi terim priming yapilir.
        prompt_reset_on_temperature=0.5 ile halusinasyon onlenir.
        """
        from faster_whisper import WhisperModel

        settings = self._settings.transcription
        self._gpu.ensure_mode("transcription")

        logger.info(
            "Whisper yukleniyor: %s (device=%s, compute=%s, beam=%d)",
            settings.model_name, settings.device, settings.compute_type,
            settings.beam_size,
        )

        model = WhisperModel(
            settings.model_name,
            device=settings.device,
            compute_type=settings.compute_type,
        )
        self._gpu.register_model("whisper", model)
        self._gpu.log_vram("whisper yuklendi")

        # Kisa initial_prompt (~30 token — tasmamasi icin)
        initial_prompt = "Doktor hasta muayenesi. Tansiyon, diyabet, ağrı, hemogram."

        segments_iter, info = model.transcribe(
            wav_path,
            language=settings.language,
            beam_size=settings.beam_size,
            temperature=settings.temperature,
            word_timestamps=settings.word_timestamps,
            vad_filter=settings.vad_filter,
            initial_prompt=initial_prompt,
            condition_on_previous_text=True,
            prompt_reset_on_temperature=0.5,
            hallucination_silence_threshold=settings.hallucination_silence_threshold,
            vad_parameters=dict(
                min_silence_duration_ms=500,
                speech_pad_ms=400,
            ),
        )

        # Generator'i materialize et
        raw_segments = list(segments_iter)

        # Dict formatina donustur
        segments = []
        for seg in raw_segments:
            words = []
            for w in (seg.words or []):
                words.append({
                    "word": w.word,
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                    "probability": round(w.probability, 3) if w.probability else 0.0,
                })
            segments.append({
                "text": seg.text.strip(),
                "start_time": round(seg.start, 3),
                "end_time": round(seg.end, 3),
                "words": words,
            })

        # Whisper modelini bosalt (diarization icin yer ac)
        del model
        self._gpu.unload_model("whisper")
        gc.collect()
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass

        self._gpu.log_vram("whisper bosaltildi")
        return segments

    # ── Post-processing ─────────────────────────────────────────────

    def _post_process(self, segments: list[dict]) -> list[dict]:
        """Turkce post-processing uygula."""
        try:
            from apps.backend.src.asr.post_processor import TurkishPostProcessor
            processor = TurkishPostProcessor()
            for seg in segments:
                seg["text"] = processor.process(seg["text"])
        except Exception as e:
            logger.warning("Post-processing hatasi: %s", e)
        return segments

    # ── Diarization ─────────────────────────────────────────────────

    async def _diarize(
        self, wav_path: str, segments: list[dict]
    ) -> list[dict]:
        """pyannote diarization + speaker assignment."""
        diarizer = SpeakerDiarizer(
            settings=self._settings.diarization,
            hf_token=self._settings.hf_token,
            gpu_manager=self._gpu,
        )

        await asyncio.to_thread(diarizer.load_model)
        diarization = await asyncio.to_thread(diarizer.diarize, wav_path)
        segments = await asyncio.to_thread(
            diarizer.assign_speakers_by_time, diarization, segments
        )
        await asyncio.to_thread(diarizer.unload)

        return segments
