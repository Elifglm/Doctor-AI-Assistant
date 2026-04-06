"""Batch ASR Pipeline - Turkce Klinik Transkripsiyon.

Kullanim:
    from apps.backend.src.asr import BatchASRPipeline, ASRSettings

    settings = ASRSettings()
    pipeline = BatchASRPipeline(settings)
"""

from apps.backend.src.asr.settings import ASRSettings

__all__ = ["ASRSettings", "BatchASRPipeline"]


def __getattr__(name: str):
    if name == "BatchASRPipeline":
        from apps.backend.src.asr.pipeline import BatchASRPipeline
        return BatchASRPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
