"""Report generation pipeline -- orchestrates NER -> RAG -> LLM -> Validation."""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Callable, Awaitable

from apps.backend.src.prompts.section_prompts import ANAMNESIS_SECTIONS, build_section_prompt
from apps.backend.src.prompts.system_prompt import SYSTEM_PROMPT
from apps.backend.src.services.llm_service import LLMService
from apps.backend.src.services.ner_service import MedicalEntity, NERService
from apps.backend.src.services.rag_service import RAGResult, RAGService

logger = logging.getLogger(__name__)

EMPTY_MARKERS = {"", "Belirtilmedi", "Belirtilmedi.", "Bilgi yok", "Bilgi yok."}

ProgressCallback = Callable[[str, str, float], Awaitable[None]]


def _merge_segments(segments: list[dict[str, Any]]) -> str:
    """Combine transcript segments into a single text block."""
    lines: list[str] = []
    for seg in segments:
        speaker = seg.get("speaker_label", seg.get("speaker", ""))
        text = seg.get("text", "")
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines)


def _score_confidence(
    content: str, entities: list[MedicalEntity]
) -> str:
    """Score confidence for a generated section."""
    stripped = content.strip()
    if not entities and stripped in EMPTY_MARKERS:
        return "low"
    if entities and any(e.text.lower() in content.lower() for e in entities):
        return "high"
    if entities:
        return "medium"
    if stripped and stripped not in EMPTY_MARKERS:
        return "medium"
    return "low"


def _format_entities(entities: list[MedicalEntity]) -> str:
    """Format entities for prompt injection."""
    if not entities:
        return "Tespit edilen tibbi bilgi yok."
    lines: list[str] = []
    for e in entities:
        lines.append(f"- [{e.label}] {e.text} (guven: {e.score:.2f})")
    return "\n".join(lines)


def _format_rag_context(results: list[RAGResult]) -> str:
    """Format RAG results for prompt injection."""
    if not results:
        return "Ek referans bilgisi yok."
    lines: list[str] = []
    for r in results:
        source = r.metadata.get("source", "bilinmiyor")
        lines.append(f"- [{source}] {r.content}")
    return "\n".join(lines)


class ReportGenerator:
    """Orchestrates the full NER -> RAG -> LLM -> Validation pipeline."""

    def __init__(
        self,
        ner: NERService,
        rag: RAGService,
        llm: LLMService,
    ) -> None:
        self.ner = ner
        self.rag = rag
        self.llm = llm

    # ------------------------------------------------------------------
    # Full pipeline (non-streaming)
    # ------------------------------------------------------------------

    async def generate_report(
        self,
        segments: list[dict[str, Any]],
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Run the complete pipeline and return structured report content."""

        async def _progress(stage: str, message: str, pct: float) -> None:
            if on_progress:
                await on_progress(stage, message, pct)

        # 1. Merge transcript
        full_text = _merge_segments(segments)
        await _progress("ner", "Tibbi bilgiler cikariliyor...", 0.1)

        # 2. NER extraction
        entities: list[MedicalEntity] = []
        if self.ner.is_ready:
            try:
                entities = await self.ner.extract(full_text)
            except Exception:
                logger.exception("NER extraction failed, continuing without entities")
        grouped = NERService.group_by_section(entities)
        await _progress(
            "ner_done",
            f"{len(entities)} tibbi bilgi tespit edildi",
            0.2,
        )

        # 3. Section-by-section generation
        section_keys = list(ANAMNESIS_SECTIONS.keys())
        sections: list[dict[str, Any]] = []

        for i, key in enumerate(section_keys):
            meta = ANAMNESIS_SECTIONS[key]
            progress = 0.2 + (i / len(section_keys)) * 0.6
            await _progress(
                "generating",
                f"Bolum olusturuluyor: {meta['title']}",
                progress,
            )

            section_entities = grouped.get(key, [])

            # RAG retrieval
            rag_results: list[RAGResult] = []
            if self.rag.is_ready and self.rag.doc_count > 0:
                query_text = f"{meta['title']} {' '.join(e.text for e in section_entities)}"
                try:
                    rag_results = await self.rag.query(query_text)
                except Exception:
                    logger.exception("RAG query failed for section %s", key)

            # LLM generation
            prompt = build_section_prompt(
                key, full_text, section_entities, rag_results
            )
            try:
                content = await self.llm.generate(prompt, SYSTEM_PROMPT)
            except Exception:
                logger.exception("LLM generation failed for section %s", key)
                content = "Belirtilmedi"

            confidence = _score_confidence(content, section_entities)

            sections.append(
                {
                    "key": key,
                    "title": meta["title"],
                    "content": content.strip(),
                    "status": "draft",
                    "confidence": confidence,
                }
            )

        await _progress("validating", "Rapor dogrulaniyor...", 0.9)

        # 4. Validation
        sections = self._validate(sections, entities, full_text)

        await _progress("done", "Rapor hazir", 1.0)

        approved_count = sum(1 for s in sections if s["confidence"] == "high")
        return {
            "sections": sections,
            "approved_sections": 0,
            "total_sections": len(sections),
        }

    # ------------------------------------------------------------------
    # Streaming generation (yields SSE events)
    # ------------------------------------------------------------------

    async def generate_report_stream(
        self,
        segments: list[dict[str, Any]],
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream report generation events for SSE."""

        full_text = _merge_segments(segments)

        yield {"event": "progress", "data": {"stage": "ner", "message": "Tibbi bilgiler cikariliyor...", "progress": 0.1}}

        # NER
        entities: list[MedicalEntity] = []
        if self.ner.is_ready:
            try:
                entities = await self.ner.extract(full_text)
            except Exception:
                logger.exception("NER extraction failed during streaming")
        grouped = NERService.group_by_section(entities)

        yield {
            "event": "progress",
            "data": {
                "stage": "ner_done",
                "message": f"{len(entities)} tibbi bilgi tespit edildi",
                "progress": 0.2,
                "entities": [e.to_dict() for e in entities],
            },
        }

        # Section-by-section
        section_keys = list(ANAMNESIS_SECTIONS.keys())
        sections: list[dict[str, Any]] = []

        for i, key in enumerate(section_keys):
            meta = ANAMNESIS_SECTIONS[key]
            progress = 0.2 + (i / len(section_keys)) * 0.6
            section_entities = grouped.get(key, [])

            yield {
                "event": "section_start",
                "data": {"section": key, "title": meta["title"], "progress": progress},
            }

            # RAG
            rag_results: list[RAGResult] = []
            if self.rag.is_ready and self.rag.doc_count > 0:
                query_text = f"{meta['title']} {' '.join(e.text for e in section_entities)}"
                try:
                    rag_results = await self.rag.query(query_text)
                except Exception:
                    pass

            # LLM streaming
            prompt = build_section_prompt(key, full_text, section_entities, rag_results)
            accumulated = ""
            try:
                async for token in self.llm.generate_stream(prompt, SYSTEM_PROMPT):
                    accumulated += token
                    yield {
                        "event": "token",
                        "data": {"section": key, "token": token},
                    }
            except Exception:
                logger.exception("LLM streaming failed for section %s", key)
                accumulated = "Belirtilmedi"

            confidence = _score_confidence(accumulated, section_entities)
            section_data = {
                "key": key,
                "title": meta["title"],
                "content": accumulated.strip(),
                "status": "draft",
                "confidence": confidence,
            }
            sections.append(section_data)

            yield {
                "event": "section_done",
                "data": {
                    "section": key,
                    "content": accumulated.strip(),
                    "confidence": confidence,
                },
            }

        # Validation
        yield {"event": "progress", "data": {"stage": "validating", "message": "Rapor dogrulaniyor...", "progress": 0.9}}
        sections = self._validate(sections, entities, full_text)

        yield {
            "event": "done",
            "data": {
                "sections": sections,
                "approved_sections": 0,
                "total_sections": len(sections),
            },
        }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate(
        sections: list[dict[str, Any]],
        entities: list[MedicalEntity],
        transcript: str,
    ) -> list[dict[str, Any]]:
        """Apply hallucination checks to generated sections."""
        transcript_lower = transcript.lower()

        for section in sections:
            content = section.get("content", "").strip()

            # Empty section check
            if not content or content in EMPTY_MARKERS:
                section["confidence"] = "low"
                continue

            # Check that key medical terms from the content appear in transcript
            # (simple grounding check)
            words = content.split()
            medical_words = [
                w for w in words
                if len(w) > 4 and w[0].isupper() and w.lower() not in transcript_lower
            ]
            if len(medical_words) > 3:
                section["confidence"] = "low"
                section["warning"] = "Transkriptte bulunmayan tibbi terimler tespit edildi"

        return sections
