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


# Label -> anamnesis section mapping
_LABEL_SECTION_MAP: dict[str, list[str]] = {
    "semptom": ["chief_complaint", "history_present"],
    "hastalik": ["history_present", "past_medical", "assessment"],
    "ilac": ["medications"],
    "dozaj": ["medications"],
    "alerji": ["allergies"],
    "ameliyat": ["past_medical"],
    "tibbi_test": ["review_systems", "assessment"],
    "vucud_bolumu": ["physical_exam", "history_present"],
    "sure": ["history_present"],
    "aile_hastaligi": ["family_history"],
    "sigara": ["social_history"],
    "alkol": ["social_history"],
    "meslek": ["social_history"],
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
