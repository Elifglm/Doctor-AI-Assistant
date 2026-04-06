"""Hibrit ASR pipeline hata hiyerarsisi."""


class ASRError(Exception):
    """Tum ASR hatalarinin temel sinifi."""


class StreamingError(ASRError):
    """Streaming transkripsiyon sirasinda olusan hata."""


class BatchProcessingError(ASRError):
    """Batch isleme sirasinda olusan hata."""


class VADError(ASRError):
    """Voice Activity Detection hatasi."""


class DiarizationError(ASRError):
    """Konusmaci ayristirma hatasi."""


class GPUMemoryError(ASRError):
    """Yetersiz GPU bellegi hatasi."""


class AudioConversionError(ASRError):
    """Ses format donusturme hatasi (FFmpeg)."""


class AudioValidationError(ASRError):
    """Ses dosyasi dogrulama hatasi."""
