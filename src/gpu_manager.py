"""VRAM izleme ve model yasam dongusu yoneticisi."""

from __future__ import annotations

import gc
import logging
from contextlib import contextmanager
from typing import Any

import torch

logger = logging.getLogger(__name__)


class GPUManager:
    """GPU bellek yonetimi ve model kayit defteri."""

    def __init__(self):
        self._registry: dict[str, Any] = {}

    def log_vram(self, stage: str) -> dict[str, float]:
        """Mevcut VRAM kullanimini logla ve dondur."""
        if not torch.cuda.is_available():
            logger.warning("CUDA mevcut degil, VRAM bilgisi alinamiyor")
            return {"allocated_gb": 0.0, "reserved_gb": 0.0, "total_gb": 0.0}

        allocated = torch.cuda.memory_allocated() / (1024**3)
        reserved = torch.cuda.memory_reserved() / (1024**3)
        total = torch.cuda.get_device_properties(0).total_memory / (1024**3)

        info = {
            "allocated_gb": round(allocated, 2),
            "reserved_gb": round(reserved, 2),
            "total_gb": round(total, 2),
        }
        logger.info(
            "[%s] VRAM - Ayrilan: %.2f GB, Rezerve: %.2f GB, Toplam: %.2f GB",
            stage,
            allocated,
            reserved,
            total,
        )
        return info

    def register_model(self, name: str, model: Any) -> None:
        """Modeli kayit defterine ekle."""
        self._registry[name] = model
        logger.debug("Model kaydedildi: %s", name)

    def unload_model(self, name: str) -> None:
        """Modeli kayit defterinden cikar ve bellekten sil."""
        if name in self._registry:
            del self._registry[name]
            logger.debug("Model silindi: %s", name)

    def unload_all(self) -> None:
        """Tum modelleri bosalt."""
        names = list(self._registry.keys())
        for name in names:
            del self._registry[name]
            logger.debug("Model silindi: %s", name)
        self.cleanup()

    def cleanup(self) -> None:
        """Garbage collection ve CUDA onbellek temizligi."""
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        logger.debug("GPU bellegi temizlendi")

    @contextmanager
    def stage_context(self, stage_name: str):
        """Otomatik VRAM loglama ve hata durumunda temizlik."""
        self.log_vram(f"{stage_name} - baslangic")
        try:
            yield
        except Exception:
            logger.error("Hata olustu: %s, temizlik yapiliyor", stage_name)
            self.unload_all()
            raise
        finally:
            self.log_vram(f"{stage_name} - bitis")
