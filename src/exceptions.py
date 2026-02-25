"""ASR Pipeline ozel hata siniflari."""


class ASRPipelineError(Exception):
    """Tum pipeline hatalari icin temel sinif."""


class AudioLoadError(ASRPipelineError):
    """Ses dosyasi yuklenirken olusan hatalar."""


class NoiseSuppressionError(ASRPipelineError):
    """Gurultu bastirma isleminde olusan hatalar."""


class TranscriptionError(ASRPipelineError):
    """Transkripsiyon isleminde olusan hatalar."""


class DiarizationError(ASRPipelineError):
    """Konusmaci ayristirma isleminde olusan hatalar."""


class ConfigurationError(ASRPipelineError):
    """Konfigurasyon hatalari (eksik token, yanlis ayar vb.)."""
