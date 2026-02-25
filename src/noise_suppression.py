"""DeepFilterNet3 gurultu bastirma sarmalayicisi."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from config.settings import DeepFilterSettings
from src.exceptions import NoiseSuppressionError
from src.gpu_manager import GPUManager

logger = logging.getLogger(__name__)


class NoiseSuppressor:
    """DeepFilterNet3 ile gurultu bastirma."""

    def __init__(self, settings: DeepFilterSettings, gpu_manager: GPUManager):
        self.settings = settings
        self.gpu = gpu_manager
        self.model = None
        self.df_state = None

    def load_model(self) -> None:
        """DeepFilterNet3 modelini yukle."""
        try:
            from df.enhance import init_df

            self.model, self.df_state, _ = init_df()
            self.gpu.register_model("deepfilternet", self.model)
            logger.info("DeepFilterNet3 modeli yuklendi")
        except Exception as e:
            raise NoiseSuppressionError(
                f"DeepFilterNet3 yuklenemedi: {e}"
            ) from e

    def process(self, input_path: str) -> str:
        """
        Ses dosyasini 48kHz'de isle ve temizlenmis dosyayi dondur.

        Args:
            input_path: Giris ses dosyasi yolu.

        Returns:
            Temizlenmis WAV dosyasinin yolu.
        """
        if self.model is None or self.df_state is None:
            raise NoiseSuppressionError("Model yuklenmemis, once load_model() cagirilmali")

        try:
            from df.enhance import enhance, load_audio, save_audio

            logger.info("Gurultu bastirma basliyor: %s", input_path)
            audio, _ = load_audio(input_path, sr=self.df_state.sr())
            enhanced = enhance(self.model, self.df_state, audio)

            output_dir = Path(tempfile.gettempdir())
            output_path = str(
                output_dir / f"{Path(input_path).stem}_enhanced.wav"
            )
            save_audio(output_path, enhanced, sr=self.df_state.sr())

            logger.info("Gurultu bastirma tamamlandi: %s", output_path)
            return output_path

        except Exception as e:
            raise NoiseSuppressionError(
                f"Gurultu bastirma hatasi: {e}"
            ) from e

    def unload_model(self) -> None:
        """Model ve VRAM bosalt."""
        self.gpu.unload_model("deepfilternet")
        self.model = None
        self.df_state = None
        self.gpu.cleanup()
        logger.info("DeepFilterNet3 modeli bosaltildi")
