"""Ana boru hatti orkestratoru - tum modulleri birlestiren pipeline."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from config.medical_terms import MEDICAL_INITIAL_PROMPT
from config.settings import AppSettings
from src.audio_utils import get_audio_duration, load_and_validate, load_audio_for_whisperx
from src.diarizer import Diarizer
from src.gpu_manager import GPUManager
from src.noise_suppression import NoiseSuppressor
from src.output_formatter import OutputFormatter
from src.transcriber import Transcriber

logger = logging.getLogger(__name__)


class ASRPipeline:
    """Poliklinik ASR - tam boru hatti."""

    def __init__(self, settings: AppSettings | None = None):
        self.settings = settings or AppSettings()
        self.gpu = GPUManager()
        self.noise_suppressor = NoiseSuppressor(self.settings.deepfilter, self.gpu)
        self.transcriber = Transcriber(
            self.settings.whisper, MEDICAL_INITIAL_PROMPT, self.gpu
        )
        self.diarizer = Diarizer(
            self.settings.diarization, self.settings.hf_token, self.gpu
        )
        self.formatter = OutputFormatter(self.settings.output)

    def process(self, audio_path: str, progress_callback=None) -> dict:
        """
        Tek fonksiyon ile tum boru hattini calistir.

        Args:
            audio_path: Giris ses dosyasi yolu.
            progress_callback: Ilerleme bildirimi icin callable(stage, message).

        Returns:
            Formatlanmis sonuc sozlugu.
        """
        timings = {}

        def _report(stage: str, message: str):
            logger.info("[%s] %s", stage, message)
            if progress_callback:
                progress_callback(stage, message)

        # Stage 0: Dosya dogrulama
        _report("Stage 0/4", "Dosya dogrulaniyor...")
        validated_path = load_and_validate(audio_path)
        duration = get_audio_duration(str(validated_path))
        _report("Stage 0/4", f"Dosya dogrulandi: {duration:.1f} saniye")

        # Stage 1: Gurultu bastirma
        enhanced_path = str(validated_path)
        if self.settings.deepfilter.enabled:
            with self.gpu.stage_context("noise_suppression"):
                _report("Stage 1/4", "Gurultu bastirma basliyor...")
                t0 = time.time()
                self.noise_suppressor.load_model()
                enhanced_path = self.noise_suppressor.process(str(validated_path))
                self.noise_suppressor.unload_model()
                timings["noise_suppression"] = round(time.time() - t0, 2)
                _report("Stage 1/4", f"Gurultu bastirma tamamlandi ({timings['noise_suppression']:.1f}s)")
        else:
            _report("Stage 1/4", "Gurultu bastirma atlandi (devre disi)")

        # Stage 2: Transkripsiyon + Hizalama
        with self.gpu.stage_context("transcription"):
            _report("Stage 2/4", "Transkripsiyon basliyor...")
            t0 = time.time()

            audio = load_audio_for_whisperx(enhanced_path)

            self.transcriber.load_whisper_model()
            raw_result = self.transcriber.transcribe(audio)

            self.transcriber.load_align_model()
            aligned_result = self.transcriber.align(raw_result, audio)

            self.transcriber.unload_all()
            timings["transcription"] = round(time.time() - t0, 2)
            _report("Stage 2/4", f"Transkripsiyon tamamlandi ({timings['transcription']:.1f}s)")

        # Stage 3: Konusmaci ayristirma
        with self.gpu.stage_context("diarization"):
            _report("Stage 3/4", "Konusmaci ayristirma basliyor...")
            t0 = time.time()

            self.diarizer.load_model()
            diarize_segments = self.diarizer.diarize(enhanced_path)
            final_result = self.diarizer.assign_speakers(diarize_segments, aligned_result)
            self.diarizer.unload_model()

            timings["diarization"] = round(time.time() - t0, 2)
            _report("Stage 3/4", f"Konusmaci ayristirma tamamlandi ({timings['diarization']:.1f}s)")

        # Stage 4: Formatlama ve kaydetme
        _report("Stage 4/4", "Sonuclar kaydediliyor...")
        timings["total"] = round(sum(timings.values()), 2)

        speakers = set(s.get("speaker") for s in final_result.get("segments", []))
        metadata = {
            "audio_file": Path(audio_path).name,
            "audio_duration_seconds": round(duration, 2),
            "language": "tr",
            "num_speakers": len(speakers),
            "models": {
                "whisper": self.settings.whisper.model_name,
                "compute_type": self.settings.whisper.compute_type,
                "alignment": "wav2vec2-xls-r-300m-cv7-turkish",
                "diarization": "pyannote/speaker-diarization-3.1",
                "noise_suppression": "DeepFilterNet3" if self.settings.deepfilter.enabled else "disabled",
            },
            "processing": timings,
        }

        output = self.formatter.format_result(final_result.get("segments", []), metadata)

        # Ciktilari kaydet
        output_dir = Path(self.settings.output.output_dir)
        output_base = output_dir / Path(audio_path).stem

        saved_files = {}
        if self.settings.output.save_json:
            json_path = self.formatter.save_json(output, f"{output_base}.json")
            saved_files["json"] = json_path

        if self.settings.output.save_txt:
            txt_path = self.formatter.save_txt(output, f"{output_base}.txt")
            saved_files["txt"] = txt_path

        output["saved_files"] = saved_files

        # Gecici dosyalari temizle
        if enhanced_path != str(validated_path):
            try:
                Path(enhanced_path).unlink(missing_ok=True)
            except OSError:
                logger.warning("Gecici dosya silinemedi: %s", enhanced_path)

        _report("Stage 4/4", "Islem tamamlandi!")
        return output
