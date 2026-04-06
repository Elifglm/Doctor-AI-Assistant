"""Gelismis GPU bellek yonetimi - streaming/batch mod gecisi destekli."""

from __future__ import annotations

import gc
import logging
import threading
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)


class ASRGPUManager:
    """GPU bellek yonetimi ve model yasam dongusu.

    Streaming ve batch modelleri asla ayni anda yuklenmez.
    Mod gecisinde tum modeller bosaltilir.
    """

    def __init__(self) -> None:
        self._registry: dict[str, Any] = {}
        self._active_mode: str | None = None  # "streaming" | "batch" | None
        self._lock = threading.Lock()
        self._cuda_available: bool = False

        try:
            import torch
            self._cuda_available = torch.cuda.is_available()
        except ImportError:
            pass

    @property
    def active_mode(self) -> str | None:
        return self._active_mode

    @property
    def cuda_available(self) -> bool:
        return self._cuda_available

    def ensure_mode(self, mode: str) -> None:
        """Hedef moda gec. Farkli moddaki modelleri bosalt.

        Args:
            mode: "streaming" veya "batch"
        """
        with self._lock:
            if self._active_mode == mode:
                return

            if self._active_mode is not None and self._registry:
                logger.info(
                    "Mod gecisi: %s -> %s, %d model bosaltiliyor",
                    self._active_mode,
                    mode,
                    len(self._registry),
                )
                self._unload_all_locked()

            self._active_mode = mode
            logger.info("ASR modu aktif: %s", mode)

    def register_model(self, name: str, model: Any) -> None:
        """Modeli kayit defterine ekle."""
        with self._lock:
            self._registry[name] = model
            logger.debug("Model kaydedildi: %s (mod: %s)", name, self._active_mode)

    def unload_model(self, name: str) -> None:
        """Tek bir modeli bosalt."""
        with self._lock:
            if name in self._registry:
                del self._registry[name]
                logger.debug("Model bosaltildi: %s", name)
                self._cleanup_locked()

    def unload_all(self) -> None:
        """Tum modelleri bosalt ve GPU bellegini temizle."""
        with self._lock:
            self._unload_all_locked()

    def cleanup(self) -> None:
        """Garbage collection ve CUDA onbellek temizligi."""
        gc.collect()
        if self._cuda_available:
            try:
                import torch
                torch.cuda.empty_cache()
            except Exception:
                pass
        logger.debug("GPU bellegi temizlendi")

    def get_vram_info(self) -> dict[str, float]:
        """Mevcut VRAM kullanimini dondur."""
        if not self._cuda_available:
            return {"allocated_gb": 0.0, "reserved_gb": 0.0, "total_gb": 0.0}

        try:
            import torch
            allocated = torch.cuda.memory_allocated() / (1024**3)
            reserved = torch.cuda.memory_reserved() / (1024**3)
            total = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            return {
                "allocated_gb": round(allocated, 2),
                "reserved_gb": round(reserved, 2),
                "total_gb": round(total, 2),
            }
        except Exception:
            return {"allocated_gb": 0.0, "reserved_gb": 0.0, "total_gb": 0.0}

    def log_vram(self, label: str) -> None:
        """VRAM durumunu logla."""
        info = self.get_vram_info()
        if info["total_gb"] > 0:
            logger.info(
                "[%s] VRAM - Ayrilan: %.2f GB, Rezerve: %.2f GB, Toplam: %.2f GB",
                label,
                info["allocated_gb"],
                info["reserved_gb"],
                info["total_gb"],
            )

    @contextmanager
    def mode_context(self, mode: str):
        """Context manager: moda gec, cikista bosalt.

        with gpu.mode_context("batch"):
            # batch modelleri yukle ve kullan
        # cikista tum modeller bosaltilir
        """
        self.ensure_mode(mode)
        self.log_vram(f"{mode} - baslangic")
        try:
            yield
        except Exception:
            logger.error("Hata olustu mod=%s, temizlik yapiliyor", mode)
            self.unload_all()
            raise
        finally:
            self.unload_all()
            self.log_vram(f"{mode} - bitis")

    # ── Private ──────────────────────────────────────────────────────

    def _unload_all_locked(self) -> None:
        """Lock altinda tum modelleri bosalt (tekrar lock almaz)."""
        names = list(self._registry.keys())
        for name in names:
            del self._registry[name]
            logger.debug("Model bosaltildi: %s", name)
        self._registry.clear()
        self._active_mode = None
        self._cleanup_locked()

    def _cleanup_locked(self) -> None:
        """Lock altinda gc + CUDA temizlik."""
        gc.collect()
        if self._cuda_available:
            try:
                import torch
                torch.cuda.empty_cache()
                # VRAM < 2GB kalirsa force temizlik
                free = (
                    torch.cuda.get_device_properties(0).total_memory
                    - torch.cuda.memory_reserved()
                ) / (1024**3)
                if free < 2.0:
                    logger.warning(
                        "Dusuk VRAM: %.2f GB, ekstra temizlik yapiliyor", free
                    )
                    gc.collect()
                    torch.cuda.empty_cache()
            except Exception:
                pass
