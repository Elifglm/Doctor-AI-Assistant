"""Report generation pipeline -- orchestrates NER -> RAG -> LLM -> Validation."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, AsyncIterator, Callable, Awaitable

from apps.backend.src.prompts.section_prompts import (
    ANAMNESIS_SECTIONS,
    NUMERIC_FIELDS,
    OPTIONAL_FIELDS,
    build_section_prompt,
)
from apps.backend.src.prompts.system_prompt import SYSTEM_PROMPT
from apps.backend.src.services.llm_base import LLMProvider
from apps.backend.src.services.ner_service import MedicalEntity, NERService
from apps.backend.src.services.rag_service import RAGResult, RAGService

logger = logging.getLogger(__name__)

EMPTY_MARKERS = {
    "", "Belirtilmedi", "Belirtilmedi.", "Bilgi yok", "Bilgi yok.",
    "BELIRTILMEDI", "BELIRTILMEDI.", "BILGI YOK", "BILGI YOK.",
}

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
    content: str, entities: list[MedicalEntity], section_key: str
) -> str:
    """Score confidence for a generated section."""
    stripped = content.strip()

    # Numeric fields: if value present and looks numeric, high confidence
    if section_key in NUMERIC_FIELDS:
        if not stripped:
            return "low"
        try:
            float(stripped.replace(",", "."))
            return "high"
        except ValueError:
            return "low"

    # Optional empty fields are acceptable
    if not stripped and section_key in OPTIONAL_FIELDS:
        return "medium"

    if not stripped or stripped in EMPTY_MARKERS:
        return "low"

    if entities and any(e.text.lower() in content.lower() for e in entities):
        return "high"
    if entities:
        return "medium"
    if stripped not in EMPTY_MARKERS:
        return "medium"
    return "low"


class ReportGenerator:
    """Orchestrates the full NER -> RAG -> LLM -> Validation pipeline."""

    def __init__(
        self,
        ner: NERService,
        rag: RAGService,
        llm: LLMProvider,
        icd10_suggestion_service: Any | None = None,
    ) -> None:
        self.ner = ner
        self.rag = rag
        self.llm = llm
        self.icd10 = icd10_suggestion_service

    # ------------------------------------------------------------------
    # Batch prompt helpers
    # ------------------------------------------------------------------

    def _build_batch_prompt(
        self,
        transcript: str,
        entities: list[MedicalEntity],
        grouped: dict[str, list[MedicalEntity]],
    ) -> str:
        """Build a compact prompt — only list field names, let LLM fill from transcript."""
        # Only send field key: title pairs, no lengthy instructions per field
        fields = ", ".join(
            f'"{k}": "{v["title"]}"' for k, v in ANAMNESIS_SECTIONS.items()
        )

        return (
            f"<TRANSKRIPT>\n{transcript}\n</TRANSKRIPT>\n\n"
            f"Yukaridaki transkriptten HBYS anamnez raporu olustur.\n"
            f"SADECE transkriptte gecen bilgileri yaz. Transkriptte olmayan bilgi EKLEME.\n"
            f"BUYUK HARF kullan. Bilgi parcalarini '----' ile ayir.\n"
            f"Bilgi yoksa bos string ver.\n"
            f"Vital degerler (sistolik, diyastolik, nabiz, ates, so2, kilo, boy) icin SADECE sayi yaz.\n"
            f"icd10_list alani icin: transkriptteki semptom ve tanilardan ICD-10 kodlari oner. "
            f"Format: (KOD) - Tani Adi (On Tani) seklinde, her satira bir kod yaz. "
            f"Ornek: (I10) - Esansiyel hipertansiyon (On Tani)\n\n"
            f"Alanlar: {{{fields}}}\n\n"
            f"SADECE JSON yanit ver: {{\"alan_key\": \"icerik\", ...}}"
        )

    @staticmethod
    def _parse_batch_response(
        raw: str, section_keys: list[str]
    ) -> dict[str, str]:
        """Parse the batch JSON response from the LLM."""
        import json as _json
        import re as _re

        # Strip markdown code blocks (```json ... ```)
        cleaned = raw.strip()
        if "```" in cleaned:
            cleaned = _re.sub(r"```(?:json)?\s*", "", cleaned)
            cleaned = cleaned.strip()

        # Extract JSON object from response
        match = _re.search(r"\{.*\}", cleaned, _re.DOTALL)
        if not match:
            logger.warning("Could not find JSON in batch response: %s", raw[:200])
            return {}

        try:
            parsed = _json.loads(match.group(0))
        except (_json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse batch JSON: %s", raw[:200])
            return {}

        result: dict[str, str] = {}
        for key in section_keys:
            val = parsed.get(key, "")
            if isinstance(val, str):
                result[key] = val.strip()
            else:
                result[key] = str(val).strip() if val else ""
        return result

    # ------------------------------------------------------------------
    # RAG helper
    # ------------------------------------------------------------------

    async def _retrieve_rag(
        self, query_text: str
    ) -> list[RAGResult]:
        """Retrieve diverse RAG results using query_diverse."""
        if not self.rag.is_ready or self.rag.doc_count == 0:
            return []
        try:
            return await self.rag.query_diverse(
                query_text, n_results=50, top_k=5
            )
        except Exception:
            logger.exception("RAG query_diverse failed")
            return []

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

        # 3. Batch generation — all sections in a single LLM call
        section_keys = list(ANAMNESIS_SECTIONS.keys())
        sections: list[dict[str, Any]] = []

        await _progress("generating", "Tum alanlar olusturuluyor...", 0.3)

        # Build a single prompt for all sections
        batch_prompt = self._build_batch_prompt(full_text, entities, grouped)
        batch_result: dict[str, str] = {}

        for attempt in range(3):
            try:
                raw = await self.llm.generate(batch_prompt, SYSTEM_PROMPT)
                batch_result = self._parse_batch_response(raw, section_keys)
                break
            except Exception as e:
                error_str = str(e).lower()
                if "rate" in error_str or "429" in error_str or "limit" in error_str:
                    wait = 5 * (attempt + 1)
                    logger.warning("Rate limit on batch, retrying in %ds", wait)
                    await asyncio.sleep(wait)
                else:
                    logger.exception("Batch LLM generation failed")
                    break

        await _progress("generating", "Alanlar ayristiriliyor...", 0.7)

        for key in section_keys:
            meta = ANAMNESIS_SECTIONS[key]
            content = batch_result.get(key, "").strip()
            # LLM'den boş geldiyse ve sayısal alan değilse BELIRTILMEDI yaz
            if not content and key not in NUMERIC_FIELDS:
                content = "BELIRTILMEDI"
            section_entities = grouped.get(key, [])
            confidence = _score_confidence(content, section_entities, key)

            sections.append(
                {
                    "key": key,
                    "title": meta["title"],
                    "content": content,
                    "status": "draft",
                    "confidence": confidence,
                }
            )

        await _progress("validating", "Rapor dogrulaniyor...", 0.9)

        # 4. ICD-10: NER → Vector DB → LLM selection pipeline
        await self._generate_icd10(sections, full_text)

        # 5. Validation
        sections = self._validate(sections, entities, full_text)

        await _progress("done", "Rapor hazir", 1.0)

        return {
            "sections": sections,
            "approved_sections": 0,
            "total_sections": len(sections),
        }

    # ------------------------------------------------------------------
    # ICD-10: NER → Vector DB → LLM selection
    # ------------------------------------------------------------------

    async def _generate_icd10(
        self, sections: list[dict[str, Any]], transcript: str
    ) -> None:
        """Generate ICD-10 suggestions using NER → Vector DB → LLM pipeline."""
        if self.icd10 is None:
            return

        # Find the icd10_list section
        icd10_section: dict[str, Any] | None = None
        for section in sections:
            if section["key"] == "icd10_list":
                icd10_section = section
                break

        if icd10_section is None:
            return

        try:
            suggestions = await self.icd10.suggest(transcript)
            if suggestions:
                icd10_text = "\n".join(
                    f"({s.icd_kodu}) - {s.tani} (Ön Tanı) [%{int(s.confidence * 100)}]"
                    for s in suggestions
                )
                icd10_section["content"] = icd10_text
                icd10_section["confidence"] = (
                    "high" if suggestions[0].confidence >= 0.7 else "medium"
                )
                logger.info(
                    "ICD-10 pipeline generated %d suggestions", len(suggestions)
                )
            else:
                logger.info("ICD-10 pipeline returned no suggestions")
        except Exception:
            logger.exception("ICD-10 pipeline failed")

    # ------------------------------------------------------------------
    # ICD-10 batch validation (legacy, kept for fallback)
    # ------------------------------------------------------------------

    # Pattern: "(I10) - Esansiyel (primer) hipertansiyon (On Tani)"
    _ICD10_LINE_RE = re.compile(
        r"\(([A-Z]\d[\dA-Z]{0,5}(?:\.\d{1,2})?)\)"
        r"\s*-\s*"
        r"(.+?)"
        r"(?:\s*\(("
        r"[OoÖö][Nn]\s*[Tt]an[iıİ]"
        r"|[Kk]esin\s*[Tt]an[iıİ]"
        r")\))?\s*$"
    )

    @staticmethod
    def _parse_icd10_lines(content: str) -> list[dict[str, str]]:
        """Parse ICD-10 entries from batch-generated icd10_list content.

        Expected format per line:
            (CODE) - Diagnosis Name (On Tani)
        Also handles lines without parenthesised type suffix.
        Returns list of dicts with keys: code, tani_text, tani_tipi.
        """
        results: list[dict[str, str]] = []
        if not content or not content.strip():
            return results

        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            m = ReportGenerator._ICD10_LINE_RE.match(line)
            if m:
                code = m.group(1).strip().upper()
                tani_text = m.group(2).strip()
                tani_tipi = m.group(3) or "Ön Tanı"
                results.append({
                    "code": code,
                    "tani_text": tani_text,
                    "tani_tipi": tani_tipi,
                })
            else:
                logger.debug("ICD-10 line did not match pattern: %s", line)
        return results

    async def _validate_batch_icd10(self, sections: list[dict[str, Any]]) -> None:
        """Validate and enrich ICD-10 codes from batch LLM output against DB.

        Operates in-place on the sections list.  No additional LLM call is made.
        The icd10_suggestion_service holds a reference to the ICD10Service (DB)
        via its ``_icd10`` attribute.
        """
        # Find the icd10_list section
        icd10_section: dict[str, Any] | None = None
        for section in sections:
            if section["key"] == "icd10_list":
                icd10_section = section
                break

        if icd10_section is None:
            return

        raw_content = icd10_section.get("content", "").strip()
        if not raw_content or raw_content in EMPTY_MARKERS:
            return

        # Get the DB-only ICD10Service for validation
        icd10_db = None
        if self.icd10 is not None:
            # self.icd10 is ICD10SuggestionService which has _icd10 (ICD10Service)
            icd10_db = getattr(self.icd10, "_icd10", None)

        if icd10_db is None:
            # No DB service available; keep batch content as-is
            logger.warning(
                "ICD10Service not available for validation, keeping raw batch content"
            )
            return

        parsed_lines = self._parse_icd10_lines(raw_content)
        if not parsed_lines:
            logger.info(
                "Could not parse any ICD-10 codes from batch content: %s",
                raw_content[:200],
            )
            return

        from apps.backend.src.services.icd10_service import normalize_turkish

        validated_lines: list[str] = []
        seen_codes: set[str] = set()

        for entry in parsed_lines:
            code = entry["code"]
            tani_text = entry["tani_text"]
            tani_tipi = entry["tani_tipi"]

            # 1. Try exact code lookup
            result = await icd10_db.get_by_code(code)

            # 2. Try parent code (e.g. "I10.0" -> "I10")
            if result is None and "." in code:
                result = await icd10_db.get_by_code(code.split(".")[0])

            # 3. Search by diagnosis name if code not found
            if result is None and tani_text:
                search_results = await icd10_db.search(tani_text, limit=3)
                if search_results:
                    best_match = None
                    best_score = 0.0
                    tani_norm = set(normalize_turkish(tani_text).split())
                    tani_norm = {w for w in tani_norm if len(w) > 2}
                    for candidate in search_results:
                        cand_norm = set(normalize_turkish(candidate.tani).split())
                        cand_norm = {w for w in cand_norm if len(w) > 2}
                        if not tani_norm or not cand_norm:
                            continue
                        overlap = len(tani_norm & cand_norm) / len(
                            tani_norm | cand_norm
                        )
                        if overlap > best_score:
                            best_score = overlap
                            best_match = candidate
                    if best_match and best_score >= 0.3:
                        result = best_match

            # Normalize tani_tipi display
            tipi_lower = tani_tipi.lower()
            tipi = (
                "Ön Tanı"
                if "on" in tipi_lower or "ön" in tipi_lower
                else "Kesin Tanı"
            )

            if result and result.icd_kodu not in seen_codes:
                seen_codes.add(result.icd_kodu)
                validated_lines.append(
                    f"({result.icd_kodu}) - {result.tani} ({tipi})"
                )
            elif code not in seen_codes:
                # Code not in DB -- keep the LLM's version but log warning
                seen_codes.add(code)
                logger.warning(
                    "ICD-10 code %s not found in DB, keeping LLM output: %s",
                    code,
                    tani_text,
                )
                validated_lines.append(f"({code}) - {tani_text} ({tipi})")

        if validated_lines:
            icd10_section["content"] = "\n".join(validated_lines)
            icd10_section["confidence"] = "high"
            logger.info(
                "ICD-10 batch validation: %d codes validated from batch response",
                len(validated_lines),
            )
        else:
            logger.info("No ICD-10 codes validated from batch content")

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

            # RAG with diversity
            query_text = f"{meta['title']} {' '.join(e.text for e in section_entities)}"
            rag_results = await self._retrieve_rag(query_text)

            # LLM streaming (with retry and rate-limit pacing)
            prompt = build_section_prompt(key, full_text, section_entities, rag_results)
            accumulated = ""
            for attempt in range(3):
                try:
                    async for token in self.llm.generate_stream(prompt, SYSTEM_PROMPT):
                        accumulated += token
                        yield {
                            "event": "token",
                            "data": {"section": key, "token": token},
                        }
                    await asyncio.sleep(2.5)
                    break
                except Exception as e:
                    error_str = str(e).lower()
                    if "rate" in error_str or "429" in error_str or "limit" in error_str:
                        wait = 5 * (attempt + 1)
                        logger.warning(
                            "Rate limit for section %s stream, retrying in %ds (attempt %d/3)",
                            key, wait, attempt + 1,
                        )
                        accumulated = ""
                        await asyncio.sleep(wait)
                    else:
                        logger.exception("LLM streaming failed for section %s", key)
                        accumulated = "BELIRTILMEDI"
                        break

            content = accumulated.strip()
            # Boş gelen sayısal olmayan alanlar için BELIRTILMEDI yaz
            if not content and key not in NUMERIC_FIELDS:
                content = "BELIRTILMEDI"
            confidence = _score_confidence(content, section_entities, key)
            section_data = {
                "key": key,
                "title": meta["title"],
                "content": content,
                "status": "draft",
                "confidence": confidence,
            }
            sections.append(section_data)

            yield {
                "event": "section_done",
                "data": {
                    "section": key,
                    "content": content,
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

    # Common filler words that are acceptable even if not in transcript
    _FILLER_WORDS: set[str] = frozenset({
        "----", "///", "MEVCUT", "DOGAL", "DOĞAL", "BELIRTILMEDI",
        "BILINEN", "KRONIK", "HASTALIK", "KULLANMIYOR", "KULLANIYOR",
        "BIRAKMIS", "SAGLIKLI", "OLUMSUZ", "OLUMLU", "NORMAL",
        "DOGAL", "ESLIK", "EDIYOR", "TARZDA", "BELIRGIN",
        "BILATERAL", "RAHAT", "DEFANS", "BASICA", "BOYUN",
    })

    @staticmethod
    def _clean_inline_belirtilmedi(content: str) -> str:
        """Remove inline BELIRTILMEDI entries when real content exists.

        Example: "BELIRTILMEDI ---- BABA HT ---- BELIRTILMEDI" -> "BABA HT"
        """
        parts = [p.strip() for p in content.split("----")]
        cleaned = [p for p in parts if p and p not in EMPTY_MARKERS]
        if cleaned:
            return " ---- ".join(cleaned)
        return content

    @staticmethod
    def _validate(
        sections: list[dict[str, Any]],
        entities: list[MedicalEntity],
        transcript: str,
    ) -> list[dict[str, Any]]:
        """Apply hallucination checks and optional-field cleanup."""
        transcript_lower = transcript.lower()

        for section in sections:
            key = section.get("key", "")
            content = section.get("content", "").strip()

            # Skip numeric fields — no hallucination check needed
            if key in NUMERIC_FIELDS:
                continue

            # Skip icd10_list — already validated against DB, formal
            # diagnosis names won't appear verbatim in the transcript
            if key == "icd10_list":
                continue

            # --- Clean inline BELIRTILMEDI entries ---
            # Remove "BELIRTILMEDI" fragments mixed with real content
            if content and "BELIRTILMEDI" in content and content not in EMPTY_MARKERS:
                content = ReportGenerator._clean_inline_belirtilmedi(content)
                section["content"] = content

            # --- Empty marker handling ---
            # For non-numeric fields, preserve "BELIRTILMEDI" so the UI
            # shows it instead of a blank placeholder.
            if content in EMPTY_MARKERS:
                section["content"] = "BELIRTILMEDI"
                section["confidence"] = "medium" if key in OPTIONAL_FIELDS else "low"
                continue

            # Empty section check — set BELIRTILMEDI for non-numeric empty fields
            if not content:
                section["content"] = "BELIRTILMEDI"
                section["confidence"] = "medium" if key in OPTIONAL_FIELDS else "low"
                continue

            # --- Hallucination grounding check ---
            # Check that key medical terms from the content appear in transcript.
            # Use both absolute threshold (>1) and proportional threshold (>20%).
            words = content.split()
            significant_words = [
                w for w in words
                if len(w) > 3
                and w not in ReportGenerator._FILLER_WORDS
                and w.upper() not in ReportGenerator._FILLER_WORDS
            ]
            if not significant_words:
                continue

            ungrounded = [
                w for w in significant_words
                if w.lower() not in transcript_lower
            ]

            ungrounded_count = len(ungrounded)
            ungrounded_ratio = ungrounded_count / len(significant_words)

            if ungrounded_count > 1 and ungrounded_ratio > 0.20:
                section["confidence"] = "low"
                section["warning"] = (
                    f"Transkriptte bulunmayan terimler tespit edildi: "
                    f"{', '.join(ungrounded[:5])}"
                )
            elif ungrounded_count > 0 and ungrounded_ratio > 0.10:
                # Downgrade to medium if some terms are ungrounded
                if section.get("confidence") == "high":
                    section["confidence"] = "medium"

        return sections
