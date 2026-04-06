"""Konusmaci ayristirma: pyannote community-1 + WhisperX speaker assignment."""

from __future__ import annotations

import logging
from typing import Any

from apps.backend.src.asr.exceptions import DiarizationError
from apps.backend.src.asr.gpu_manager import ASRGPUManager
from apps.backend.src.asr.settings import DiarizationSettings

logger = logging.getLogger(__name__)


class SpeakerDiarizer:
    """pyannote.audio ile 2 konusmacili diarization (Doktor/Hasta).

    Kullanim:
        diarizer = SpeakerDiarizer(settings, hf_token, gpu)
        diarizer.load_model()
        diarization = diarizer.diarize("audio.wav")
        result = diarizer.assign_speakers(diarization, aligned_result)
        diarizer.unload()
    """

    def __init__(
        self,
        settings: DiarizationSettings,
        hf_token: str,
        gpu_manager: ASRGPUManager,
    ) -> None:
        self._settings = settings
        self._hf_token = hf_token
        self._gpu = gpu_manager
        self._pipeline: Any = None

    @property
    def is_loaded(self) -> bool:
        return self._pipeline is not None

    def load_model(self) -> None:
        """pyannote diarization pipeline yukle."""
        if not self._hf_token:
            logger.warning(
                "HF_TOKEN bulunamadi, diarization atlanacak"
            )
            return

        try:
            from pyannote.audio import Pipeline

            model_name = self._settings.model_name
            logger.info("Diarization modeli yukleniyor: %s", model_name)

            self._pipeline = Pipeline.from_pretrained(
                model_name,
                token=self._hf_token,
            )

            # GPU'ya tasi (varsa)
            if self._gpu.cuda_available:
                try:
                    import torch
                    self._pipeline.to(torch.device("cuda"))
                    logger.info("Diarization modeli GPU'ya tasindi")
                except Exception as e:
                    logger.warning(
                        "Diarization GPU'ya tasinamadi, CPU'da devam: %s", e
                    )

            self._gpu.register_model("pyannote", self._pipeline)
            logger.info("Diarization modeli yuklendi")

        except Exception as e:
            logger.warning("Diarization modeli yuklenemedi: %s", e)
            self._pipeline = None

    def diarize(self, audio_path: str) -> Any:
        """Ses dosyasinda konusmaci ayristirmasi yap.

        Args:
            audio_path: WAV dosyasi yolu

        Returns:
            pyannote diarization sonucu veya None (model yuklu degilse)
        """
        if self._pipeline is None:
            logger.warning("Diarization modeli yuklu degil, atlanıyor")
            return None

        try:
            import torchaudio

            logger.info("Diarization basliyor: %s", audio_path)

            # torchcodec DLL sorunu nedeniyle dosya yolu yerine
            # in-memory waveform dict geciyoruz (pyannote 4.0 resmi workaround)
            waveform, sample_rate = torchaudio.load(audio_path)

            result = self._pipeline(
                {"waveform": waveform, "sample_rate": sample_rate},
                num_speakers=self._settings.num_speakers,
                min_speakers=self._settings.min_speakers,
                max_speakers=self._settings.max_speakers,
            )

            # pyannote 4.0 DiarizeOutput -> Annotation cikar
            # exclusive: ortusme yok, her zaman araligina tek konusmaci (daha temiz alignment)
            if hasattr(result, "exclusive_speaker_diarization"):
                diarization = result.exclusive_speaker_diarization
            elif hasattr(result, "speaker_diarization"):
                diarization = result.speaker_diarization
            else:
                diarization = result  # pyannote 3.x uyumluluk

            logger.info("Diarization tamamlandi")
            return diarization

        except Exception as e:
            logger.error("Diarization hatasi: %s", e)
            return None

    def assign_speakers_by_time(
        self,
        diarization_result: Any,
        segments: list[dict],
    ) -> list[dict]:
        """Kelime seviyesinde speaker atama + speaker degisiminde segment bolme.

        Whisper uzun segmentler uretebilir (30s+). Bu metod her kelimeye
        diarization'dan speaker atar, speaker degistiginde yeni segment olusturur.

        Args:
            diarization_result: pyannote Annotation objesi (veya None)
            segments: [{"text": ..., "start_time": ..., "end_time": ..., "words": [...]}, ...]

        Returns:
            Speaker label eklenmiş, konuşmacı değişiminde bölünmüş segment listesi
        """
        if diarization_result is None or not segments:
            return self._apply_default_labels_to_list(segments)

        try:
            import numpy as np

            # Diarization turn'lerini cikart
            diar_turns: list[tuple[float, float, str]] = []
            for seg, _, spk in diarization_result.itertracks(yield_label=True):
                diar_turns.append((seg.start, seg.end, spk))

            if not diar_turns:
                return self._apply_default_labels_to_list(segments)

            d_starts = np.array([t[0] for t in diar_turns])
            d_ends = np.array([t[1] for t in diar_turns])
            d_speakers = [t[2] for t in diar_turns]
            default_labels = self._settings.default_labels

            def get_speaker_for_time(t_start: float, t_end: float) -> str:
                """Zaman araligina en cok ortüsen speaker'i bul."""
                intersections = np.minimum(d_ends, t_end) - np.maximum(d_starts, t_start)
                best_idx = -1
                best_val = 0.0
                for i, val in enumerate(intersections):
                    if val > best_val:
                        best_val = val
                        best_idx = i
                return d_speakers[best_idx] if best_idx >= 0 else "SPEAKER_00"

            # Her kelimeye speaker ata, speaker degisiminde yeni segment olustur
            result_segments: list[dict] = []

            for seg in segments:
                words = seg.get("words", [])

                if not words:
                    # Kelime bilgisi yoksa segment seviyesinde ata
                    s_start = seg.get("start_time", seg.get("start", 0.0))
                    s_end = seg.get("end_time", seg.get("end", 0.0))
                    speaker = get_speaker_for_time(s_start, s_end)
                    seg["speaker"] = speaker
                    seg["speaker_label"] = default_labels.get(speaker, speaker)
                    result_segments.append(seg)
                    continue

                # Kelime seviyesinde speaker atama
                current_speaker = None
                current_words: list[str] = []
                current_start = 0.0
                current_end = 0.0

                for word in words:
                    w_start = word.get("start", word.get("start_time", 0.0))
                    w_end = word.get("end", word.get("end_time", w_start + 0.1))
                    w_text = word.get("word", "")
                    w_speaker = get_speaker_for_time(w_start, w_end)

                    if current_speaker is None:
                        current_speaker = w_speaker
                        current_start = w_start

                    if w_speaker != current_speaker:
                        # Speaker degisti — onceki segmenti kaydet
                        if current_words:
                            result_segments.append({
                                "text": " ".join(current_words).strip(),
                                "start_time": round(current_start, 3),
                                "end_time": round(current_end, 3),
                                "speaker": current_speaker,
                                "speaker_label": default_labels.get(
                                    current_speaker, current_speaker
                                ),
                                "words": [],
                            })
                        # Yeni segment basla
                        current_speaker = w_speaker
                        current_words = []
                        current_start = w_start

                    current_words.append(w_text.strip())
                    current_end = w_end

                # Son segmenti kaydet
                if current_words and current_speaker:
                    result_segments.append({
                        "text": " ".join(current_words).strip(),
                        "start_time": round(current_start, 3),
                        "end_time": round(current_end, 3),
                        "speaker": current_speaker,
                        "speaker_label": default_labels.get(
                            current_speaker, current_speaker
                        ),
                        "words": [],
                    })

            logger.info(
                "Speaker atama: %d segment -> %d segment (kelime bazli bolme)",
                len(segments), len(result_segments),
            )
            return result_segments

        except Exception as e:
            logger.error("Zaman-ortusme speaker atama hatasi: %s", e)
            return self._apply_default_labels_to_list(segments)

    def _apply_default_labels_to_list(self, segments: list[dict]) -> list[dict]:
        """Segment listesine varsayilan etiket ata."""
        default_labels = self._settings.default_labels
        for seg in segments:
            if "speaker" not in seg:
                seg["speaker"] = "SPEAKER_00"
            seg["speaker_label"] = default_labels.get(
                seg.get("speaker", "SPEAKER_00"), "Doktor"
            )
        return segments

    def unload(self) -> None:
        """Diarization modelini bosalt."""
        self._gpu.unload_model("pyannote")
        self._pipeline = None
        self._gpu.cleanup()
        logger.info("Diarization modeli bosaltildi")

