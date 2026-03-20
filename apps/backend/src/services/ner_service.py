"""GLiNER-based NER service for Turkish medical entity extraction."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from config.settings import AppSettings

logger = logging.getLogger(__name__)

settings = AppSettings()

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class MedicalEntity:
    text: str
    label: str
    score: float
    start: int = 0
    end: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "label": self.label,
            "score": round(self.score, 3),
            "start": self.start,
            "end": self.end,
        }


# Label -> HBYS anamnesis field mapping
_LABEL_SECTION_MAP: dict[str, list[str]] = {
    "semptom": ["hastanin_yakinmasi", "hastanin_oykusu"],
    "hastalik": ["hastanin_oykusu", "oz_gecmisi_soy_gecmisi", "icd10_list"],
    "ilac": ["tedavi", "oz_gecmisi_soy_gecmisi"],
    "dozaj": ["tedavi"],
    "alerji": ["alerji"],
    "ameliyat": ["oz_gecmisi_soy_gecmisi"],
    "tibbi_test": ["tedavi", "muayene_bulgulari"],
    "vucud_bolumu": ["muayene_bulgulari", "hastanin_oykusu"],
    "sure": ["hastanin_oykusu", "sikayet_baslangic_tarihi"],
    "aile_hastaligi": ["soy_gecmisi"],
    "sigara": ["sigara"],
    "alkol": ["alkol"],
    "meslek": ["hastanin_oykusu"],
}


class NERService:
    """Zero-shot Turkish medical NER using GLiNER."""

    MEDICAL_LABELS: list[str] = [
        "semptom",
        "hastalik",
        "ilac",
        "dozaj",
        "alerji",
        "ameliyat",
        "tibbi_test",
        "vucud_bolumu",
        "sure",
        "aile_hastaligi",
        "sigara",
        "alkol",
        "meslek",
    ]

    def __init__(self) -> None:
        self._model: Any = None

    async def initialize(self) -> None:
        """Lazy-load the GLiNER model (CPU, ~500 MB)."""
        if self._model is not None:
            return
        logger.info("Loading GLiNER model: %s ...", settings.ner.model_name)
        self._model = await asyncio.to_thread(self._load_model)
        logger.info("GLiNER model loaded.")

    def _load_model(self) -> Any:
        from gliner import GLiNER  # type: ignore[import-untyped]

        return GLiNER.from_pretrained(settings.ner.model_name)

    @property
    def is_ready(self) -> bool:
        return self._model is not None

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    async def extract(self, text: str) -> list[MedicalEntity]:
        """Extract medical entities from Turkish text."""
        if self._model is None:
            await self.initialize()

        raw = await asyncio.to_thread(
            self._model.predict_entities,
            text,
            self.MEDICAL_LABELS,
            threshold=settings.ner.threshold,
        )
        entities: list[MedicalEntity] = []
        for e in raw:
            entities.append(
                MedicalEntity(
                    text=e["text"],
                    label=e["label"],
                    score=e["score"],
                    start=e.get("start", 0),
                    end=e.get("end", 0),
                )
            )
        return entities

    # ------------------------------------------------------------------
    # Grouping
    # ------------------------------------------------------------------

    @staticmethod
    def group_by_section(
        entities: list[MedicalEntity],
    ) -> dict[str, list[MedicalEntity]]:
        """Group entities by anamnesis section key."""
        groups: dict[str, list[MedicalEntity]] = {}
        for entity in entities:
            sections = _LABEL_SECTION_MAP.get(entity.label, [])
            for section_key in sections:
                groups.setdefault(section_key, []).append(entity)
        return groups
