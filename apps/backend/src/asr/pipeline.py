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

    def __init__(self, settings: ASRSettings, ner_service: Any = None) -> None:
        self._settings = settings
        self._gpu = ASRGPUManager()
        self._ner_service = ner_service  # Optional: NER-based speaker labeling

    @property
    def gpu_manager(self) -> ASRGPUManager:
        return self._gpu

    def set_ner_service(self, ner_service: Any) -> None:
        self._ner_service = ner_service

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

            # Stage 3b: NER-based speaker classification (Doktor vs Hasta)
            # pyannote SPEAKER_00/01 etiketlerini rastgele atar; entity dagilimi
            # ile dogru rolu (Doktor/Hasta) belirleriz.
            if self._ner_service is not None:
                await report("Stage 3/4", "Konusmacilar siniflandiriliyor...", 0.85)
                t0 = time.time()
                segments = await self._classify_speakers_with_ner(segments)
                timings["speaker_ner"] = round(time.time() - t0, 2)
                logger.info("NER speaker classification: %.1fs", timings["speaker_ner"])

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

    # ── NER-based speaker classification ────────────────────────────
    # Hybrid scoring (no LLM call): NER entities + Turkish keywords +
    # avg segment length + question ratio. Kalibrasyon Turk medikal anamnez
    # transkriptlerine gore: doktor kisa+sorgulayici konusur, hasta uzun
    # anlatim yapar; her iki taraf da medikal terim kullanir, bu yuzden NER
    # tek basina yetersiz — keyword'ler ayrim icin kritik.

    # NER entity weights (sadece dogrudan ayirici olanlar — semptom gibi
    # her iki tarafta da gecen entity'ler ETKIN DEGIL).
    _DOCTOR_ENTITY_WEIGHTS: dict[str, int] = {
        "ilac": 1,
        "dozaj": 2,        # "5 mg 1x1" — doz orderi doktordan
        "ameliyat": 1,
    }
    _PATIENT_ENTITY_WEIGHTS: dict[str, int] = {
        "aile_hastaligi": 3,  # "annemde tansiyon" — guclu hasta sinyali
        "sigara": 2,
        "alkol": 2,
    }

    # Turkish doctor speech markers (clinical interview phrases + action verbs).
    # Lowercase substring match. Phrases > tek kelimeler (daha az false positive).
    _DOCTOR_KEYWORDS: dict[str, int] = {
        "anlatır mısın": 3, "anlatır mısınız": 3,
        "yazalım": 3, "yazıyorum": 2, "yazayım": 2,
        "isteyelim": 3, "isteyeyim": 2,
        "çekelim": 3, "çekeyim": 2,
        "bakalım": 2, "bakayım": 2,
        "ölçelim": 2,
        "soruyorum": 2, "sorayım": 2, "soracağım": 2,
        "muayene edelim": 3, "kontrol edelim": 3,
        "geçmiş olsun": 2,
        "tedavi edelim": 3,
        "şikayetiniz": 2, "yakınmanız": 2,
        "buyurun": 1,
        "bir şey": 0,  # noise filtresi (nötr)
    }
    # Turkish patient speech markers — direct addresses + first-person symptom.
    _PATIENT_KEYWORDS: dict[str, int] = {
        "hocam": 2,
        "doktorum": 2,
        "evet hocam": 3, "yok hocam": 3, "var hocam": 3,
        "annem": 2, "annemde": 3, "annemin": 2,
        "babam": 2, "babamda": 3, "babamın": 2,
        "kardeşim": 2, "kardeşimde": 3,
        "anneannem": 2, "babaannem": 2, "dedem": 2,
        "ağrım": 2, "ağrılarım": 2,
        "kaldıramıyorum": 2, "yapamıyorum": 2, "uyuyamıyorum": 2,
        "yıllardır": 1, "aydır": 1, "haftadır": 1, "günlerdir": 1,
        "kullanıyorum": 1,  # "ilaç kullanıyorum"
    }

    _MIN_ENTITIES_FOR_CLASSIFICATION = 0  # keyword sinyali var, NER tek basina sart degil

    async def _classify_speakers_with_ner(
        self, segments: list[dict]
    ) -> list[dict]:
        """Re-label SPEAKER_00/01 as Doktor/Hasta using a hybrid signal.

        Hybrid score (no LLM):
          - NER entities (doctor: ilac/dozaj/ameliyat, patient: aile/sigara/alkol)
          - Turkish keywords (doctor: yazalım/anlatır mısınız, patient: hocam/annem)
          - Avg segment length (shorter = more doctor-like, asks questions)
          - Question count (more = more doctor-like)

        Each speaker gets a `doctor_likeness` float; the higher one is
        relabeled "Doktor", the other "Hasta".
        """
        # Group segment texts per speaker
        speaker_segs: dict[str, list[dict]] = {}
        for seg in segments:
            spk = seg.get("speaker") or "SPEAKER_00"
            txt = (seg.get("text") or "").strip()
            if txt:
                speaker_segs.setdefault(spk, []).append(seg)

        if len(speaker_segs) < 2:
            return segments  # tek konuşmacı

        # Compute per-speaker signals
        all_avg_lens: list[float] = []
        all_q_counts: list[int] = []
        per_speaker: dict[str, dict] = {}
        for spk, segs in speaker_segs.items():
            texts = [s.get("text", "") for s in segs]
            merged = " ".join(texts)
            merged_lower = merged.lower()
            q_count = merged.count("?")
            avg_len = sum(len(t) for t in texts) / max(len(texts), 1)
            all_avg_lens.append(avg_len)
            all_q_counts.append(q_count)

            # NER (optional — works without if NER not ready)
            ner_doc = ner_pat = 0
            if self._ner_service and getattr(self._ner_service, "is_ready", False):
                try:
                    entities = await self._ner_service.extract(merged)
                    ner_doc = sum(self._DOCTOR_ENTITY_WEIGHTS.get(e.label, 0) for e in entities)
                    ner_pat = sum(self._PATIENT_ENTITY_WEIGHTS.get(e.label, 0) for e in entities)
                except Exception as e:
                    logger.warning("NER fail for speaker %s: %s", spk, e)

            # Keyword signals
            kw_doc = sum(w * merged_lower.count(k) for k, w in self._DOCTOR_KEYWORDS.items())
            kw_pat = sum(w * merged_lower.count(k) for k, w in self._PATIENT_KEYWORDS.items())

            per_speaker[spk] = {
                "ner_diff": ner_doc - ner_pat,
                "kw_diff": kw_doc - kw_pat,
                "avg_len": avg_len,
                "q_count": q_count,
                "n_segments": len(segs),
            }

        # Normalize length & question signals across speakers (relative).
        # Doctor-like = SHORTER avg_len (asks questions, brief), MORE questions.
        max_len = max(all_avg_lens) or 1.0
        max_q = max(all_q_counts) or 1

        # Combine into a single "doctor_likeness" per speaker.
        # Weights tuned on Turkish medical interviews; keyword > NER > length > q.
        for spk, d in per_speaker.items():
            length_signal = 1.0 - (d["avg_len"] / max_len)   # short → 1, long → 0
            q_signal = d["q_count"] / max_q                  # 0..1
            d["doctor_likeness"] = (
                d["kw_diff"] * 1.0      # phrase keywords most reliable
                + d["ner_diff"] * 0.5   # entity sinyali (zayif ama yardimci)
                + length_signal * 3.0   # ~+3 if shortest, 0 if longest
                + q_signal * 2.0        # ~+2 if most questions
            )

        # Pick speaker with highest doctor_likeness as Doktor
        ranked = sorted(per_speaker.items(), key=lambda x: x[1]["doctor_likeness"], reverse=True)
        doctor_spk = ranked[0][0]
        patient_spk = ranked[-1][0]
        if doctor_spk == patient_spk:
            return segments

        # Confidence: if top vs bottom likeness gap is too small (< 1.0),
        # fall back to default labels — we're not confident.
        gap = per_speaker[doctor_spk]["doctor_likeness"] - per_speaker[patient_spk]["doctor_likeness"]
        if gap < 1.0:
            logger.info(
                "Speaker classification ambiguous (gap=%.2f), keeping default labels",
                gap,
            )
            return segments

        relabel = {doctor_spk: "Doktor", patient_spk: "Hasta"}
        logger.info(
            "Speaker classification: %s -> Doktor (likeness=%.2f, kw=%d, ner=%d), "
            "%s -> Hasta (likeness=%.2f, kw=%d, ner=%d)",
            doctor_spk, per_speaker[doctor_spk]["doctor_likeness"],
            per_speaker[doctor_spk]["kw_diff"], per_speaker[doctor_spk]["ner_diff"],
            patient_spk, per_speaker[patient_spk]["doctor_likeness"],
            per_speaker[patient_spk]["kw_diff"], per_speaker[patient_spk]["ner_diff"],
        )

        for seg in segments:
            spk = seg.get("speaker", "SPEAKER_00")
            if spk in relabel:
                seg["speaker_label"] = relabel[spk]

        return segments
