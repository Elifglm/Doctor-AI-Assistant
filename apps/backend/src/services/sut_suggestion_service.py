"""SUT tetkik suggestion service: NER → Vector DB → LLM selection pipeline."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from apps.backend.src.schemas.sut_tetkik import SUTSuggestion
from apps.backend.src.services.sut_service import SUTService
from apps.backend.src.services.sut_vector_service import SUTVectorService
from apps.backend.src.services.llm_base import LLMProvider

logger = logging.getLogger(__name__)

SUT_SELECTION_PROMPT = """\
Sen bir Turkce tibbi tetkik/tahlil uzmanisisin. Asagida bir doktor-hasta gorusme \
transkripti ve SUT tetkik/tahlil aday kodlari verilmistir.

GOREV: Aday tetkiklerden transkripte en uygun olanlari sec. Uygun olmayanları SECME.

KURALLAR:
- SADECE transkriptte doktorun istedigi veya bahsettiğı tetkikleri sec.
- Transkriptle ilgisi olmayan tetkikleri SECME.
- Doktorun kullandigi halk dilindeki ifadeleri dogru tetkikle esle \
  (ornek: "kan sayimi" = Hemogram, "seker" = Aclik kan sekeri).
- Branşa uygun tetkikleri oncelikle sec.
- Maksimum 10 tetkik sec.
- Her tetkik icin guven skoru (0.0-1.0) ver.
- Sadece JSON formatinda yanit ver.

TRANSKRIPT:
{transcript}

ADAY TETKIKLER:
{candidates}

Yanit (sadece JSON, baska bir sey yazma):
[
  {{"kodu": "902050", "adi": "Hemogram", "confidence": 0.90, "reasoning": "Doktor kan sayimi istedi"}}
]

Hicbir aday uygun degilse bos liste don: []
"""

SUT_REPORT_SELECTION_PROMPT = """\
Sen bir Turkce tibbi tetkik/tahlil uzmanisin. Asagida bir anamnez raporunun ilgili \
alanlari ve SUT tetkik/tahlil aday kodlari verilmistir.

GOREV: Aday tetkiklerden rapora en uygun olanlari sec.

KURALLAR:
- Rapordaki tani, sikayet ve bulgulara uygun tetkikleri sec.
- Klinik pratikte bu tani icin standart olarak istenen tetkikleri tercih et.
- Maksimum 10 tetkik sec.
- Her tetkik icin guven skoru (0.0-1.0) ver.
- Sadece JSON formatinda yanit ver.

ANAMNEZ RAPORU:
{report_text}

ADAY TETKIKLER:
{candidates}

Yanit (sadece JSON, baska bir sey yazma):
[
  {{"kodu": "902050", "adi": "Hemogram", "confidence": 0.90, "reasoning": "HT tanisi icin rutin kan tahlili"}}
]

Hicbir aday uygun degilse bos liste don: []
"""


class SUTSuggestionService:
    """NER → Vector DB search → LLM selection pipeline for SUT tetkik codes.

    Pipeline:
    1. NER extracts medical/test terms from transcript
    2. Vector DB finds candidate SUT tetkik codes for each term
    3. LLM selects the most appropriate tetkik from candidates
    """

    def __init__(
        self,
        llm: LLMProvider,
        sut_service: SUTService,
        vector_service: SUTVectorService | None = None,
        ner_service: Any | None = None,
    ) -> None:
        self._llm = llm
        self._sut = sut_service
        self._vectors = vector_service
        self._ner = ner_service

    async def suggest(
        self, transcript: str, brans: str | None = None
    ) -> list[SUTSuggestion]:
        """Full pipeline: NER → Vector DB → LLM selection."""
        ner_terms = await self._extract_ner_terms(transcript)
        logger.info("NER extracted %d terms: %s", len(ner_terms), ner_terms[:5])

        candidates = await self._find_vector_candidates(ner_terms, brans=brans)
        # Always add text search results for better coverage
        text_candidates = await self._text_search_fallback(ner_terms, brans=brans)
        seen = {c["kodu"] for c in candidates}
        for tc in text_candidates:
            if tc["kodu"] not in seen:
                seen.add(tc["kodu"])
                candidates.append(tc)
        print(f"[SUT-DEBUG] suggest: {len(candidates)} total candidates (vector+text)", flush=True)

        if not candidates:
            logger.warning("No SUT tetkik candidates found")
            return []

        suggestions = await self._llm_select(transcript, candidates)
        logger.info("LLM selected %d SUT tetkik", len(suggestions))

        return suggestions

    _RELEVANT_KEYS = {
        "hastanin_yakinmasi", "hastanin_oykusu", "fizik_muayene",
        "oz_gecmisi_soy_gecmisi", "on_tani", "istenen_tetkikler",
        "tedavi", "oneri", "sut_tetkik_list",
    }

    async def suggest_from_report(
        self, report_sections: dict[str, str], brans: str | None = None
    ) -> list[SUTSuggestion]:
        """Generate SUT tetkik suggestions from structured report fields."""
        print(f"[SUT-DEBUG] suggest_from_report called with {len(report_sections)} sections", flush=True)
        search_parts: list[str] = []
        for key in self._RELEVANT_KEYS:
            val = report_sections.get(key, "").strip()
            print(f"[SUT-DEBUG]   key={key} val={val[:60]!r} included={bool(val and val not in {'BELIRTILMEDI', 'BELIRTILMEDI.', ''})}", flush=True)
            if val and val not in {"BELIRTILMEDI", "BELIRTILMEDI.", ""}:
                search_parts.append(val)

        # Fallback: use ALL non-empty report sections
        if not search_parts:
            print("[SUT-DEBUG]   No relevant keys matched, trying ALL sections...", flush=True)
            for key, val in report_sections.items():
                val = val.strip()
                if val and val not in {"BELIRTILMEDI", "BELIRTILMEDI.", ""}:
                    search_parts.append(val)
                    print(f"[SUT-DEBUG]   FALLBACK key={key} val={val[:60]!r}", flush=True)

        if not search_parts:
            print("[SUT-DEBUG] NO search_parts found, returning empty", flush=True)
            return []

        print(f"[SUT-DEBUG] search_parts count: {len(search_parts)}", flush=True)

        logger.info("search_parts count: %d", len(search_parts))

        report_text = "\n".join(search_parts)

        ner_terms = await self._extract_ner_terms(report_text)
        logger.info("Report NER extracted %d terms: %s", len(ner_terms), ner_terms[:5])

        candidates = await self._find_vector_candidates(ner_terms, brans=brans)
        text_candidates = await self._text_search_fallback(ner_terms, brans=brans)
        seen = {c["kodu"] for c in candidates}
        for tc in text_candidates:
            if tc["kodu"] not in seen:
                seen.add(tc["kodu"])
                candidates.append(tc)
        logger.info("Report combined %d candidates (vector + text)", len(candidates))

        if not candidates:
            return []

        suggestions = await self._llm_select_from_report(report_text, candidates)
        logger.info("Report LLM selected %d SUT tetkik", len(suggestions))

        return suggestions

    async def _llm_select_from_report(
        self, report_text: str, candidates: list[dict[str, Any]]
    ) -> list[SUTSuggestion]:
        """Ask LLM to select SUT tetkik codes based on structured report."""
        candidates_text = "\n".join(
            f"({c['kodu']}) - {c['adi']} [{c['brans']}] [skor: {c['score']:.2f}]"
            for c in candidates
        )

        prompt = SUT_REPORT_SELECTION_PROMPT.format(
            report_text=report_text,
            candidates=candidates_text,
        )

        try:
            raw = await self._llm.generate(prompt, "")
        except Exception:
            logger.exception("LLM SUT tetkik report selection failed")
            return [
                SUTSuggestion(
                    kodu=c["kodu"],
                    adi=c["adi"],
                    brans=c["brans"],
                    confidence=c["score"],
                    reasoning=f"Vektorel arama: {c['source']}",
                )
                for c in candidates[:10]
            ]

        return self._parse_llm_selection(raw)

    # ------------------------------------------------------------------
    # Step 1: NER extraction
    # ------------------------------------------------------------------

    async def _extract_ner_terms(self, transcript: str) -> list[str]:
        """Extract medical/test terms from transcript using GLiNER NER."""
        terms: list[str] = []

        if self._ner is not None:
            try:
                if not self._ner.is_ready:
                    await self._ner.initialize()
                entities = await self._ner.extract(transcript)
                terms = list({e.text for e in entities})
                logger.info("GLiNER NER found: %s", terms)
            except Exception:
                logger.exception("NER extraction failed, falling back to keyword extraction")

        if not terms:
            terms = self._extract_keywords(transcript)
            logger.info("Keyword fallback extracted: %s", terms)

        return terms

    @staticmethod
    def _extract_keywords(transcript: str) -> list[str]:
        """Extract tetkik/tahlil terms from transcript text."""
        tetkik_keywords = {
            "kan sayımı", "kan sayimi", "hemogram", "kan tahlili",
            "şeker", "seker", "açlık kan şekeri", "hba1c",
            "idrar", "idrar tahlili", "tam idrar",
            "tiroit", "tiroid", "tsh", "t3", "t4",
            "karaciğer", "karaciger", "ast", "alt",
            "böbrek", "bobrek", "kreatinin", "üre",
            "kolesterol", "lipid", "trigliserid",
            "röntgen", "rontgen", "mr", "tomografi", "bt",
            "ultrason", "ekg", "eko", "eforlu",
            "kültür", "kultur", "balgam", "gaita",
            "sedimantasyon", "crp", "demir", "ferritin",
            "d vitamini", "b12", "folik asit",
            "psa", "ca 125", "cea", "afp",
        }

        transcript_lower = transcript.lower()
        found: list[str] = []

        # Direct keyword match
        for keyword in tetkik_keywords:
            if keyword in transcript_lower:
                found.append(keyword)

        # Extract full phrases from doctor lines mentioning tetkik/tahlil
        lines = transcript.split("\n")
        for line in lines:
            lower_line = line.lower()
            if any(speaker in lower_line for speaker in ["doktor:", "doctor:", "dr:"]):
                if any(w in lower_line for w in [
                    "istek", "iste", "isteyel", "istiyorum",
                    "bakal", "bakıl", "bakilal",
                    "tetkik", "tahlil", "test",
                    "çekelim", "cekelim", "çekim", "cekim",
                    "sayım", "sayim",
                ]):
                    # Send the whole doctor line as a search term
                    doctor_text = line.split(":", 1)[-1].strip()
                    if doctor_text:
                        found.append(doctor_text[:120])

        print(f"[SUT-DEBUG] keyword extraction found: {found}", flush=True)
        return found[:15]

    # ------------------------------------------------------------------
    # Step 2: Vector DB search
    # ------------------------------------------------------------------

    async def _find_vector_candidates(
        self, terms: list[str], brans: str | None = None
    ) -> list[dict[str, Any]]:
        """Search vector DB for candidate SUT tetkik codes."""
        print(f"[SUT-DEBUG] _find_vector_candidates: vectors={self._vectors is not None}, ready={self._vectors.is_ready if self._vectors else False}, terms={terms}", flush=True)
        if self._vectors is None or not self._vectors.is_ready:
            print("[SUT-DEBUG] Vector service NOT ready, falling back to text search", flush=True)
            return await self._text_search_fallback(terms, brans=brans)

        results = await self._vectors.search_multiple(
            terms, n_per_term=3, min_score=0.45, brans=brans
        )

        candidates = []
        for r in results[:20]:
            candidates.append({
                "kodu": r.kodu,
                "adi": r.adi,
                "brans": r.brans,
                "score": r.score,
                "source": r.source_term,
            })
        return candidates

    async def _text_search_fallback(
        self, terms: list[str], brans: str | None = None
    ) -> list[dict[str, Any]]:
        """Fallback: text-based SUT search when vector DB is unavailable."""
        candidates = []
        seen: set[str] = set()
        for term in terms[:5]:
            results = await self._sut.search(term, limit=3, brans=brans)
            for r in results:
                if r.kodu not in seen:
                    seen.add(r.kodu)
                    candidates.append({
                        "kodu": r.kodu,
                        "adi": r.adi,
                        "brans": r.brans,
                        "score": 0.5,
                        "source": term,
                    })
        return candidates

    # ------------------------------------------------------------------
    # Step 3: LLM selection
    # ------------------------------------------------------------------

    async def _llm_select(
        self, transcript: str, candidates: list[dict[str, Any]]
    ) -> list[SUTSuggestion]:
        """Ask LLM to select the most relevant tetkik from candidates."""
        candidates_text = "\n".join(
            f"({c['kodu']}) - {c['adi']} [{c['brans']}] [kaynak: \"{c['source']}\", skor: {c['score']:.2f}]"
            for c in candidates
        )

        prompt = SUT_SELECTION_PROMPT.format(
            transcript=transcript,
            candidates=candidates_text,
        )

        try:
            raw = await self._llm.generate(prompt, "")
        except Exception:
            logger.exception("LLM SUT tetkik selection failed")
            return [
                SUTSuggestion(
                    kodu=c["kodu"],
                    adi=c["adi"],
                    brans=c["brans"],
                    confidence=c["score"],
                    reasoning=f"Vektorel arama: {c['source']}",
                )
                for c in candidates[:10]
            ]

        return self._parse_llm_selection(raw)

    @staticmethod
    def _parse_llm_selection(raw: str) -> list[SUTSuggestion]:
        """Parse LLM's JSON selection response."""
        cleaned = raw.strip()
        if "```" in cleaned:
            cleaned = re.sub(r"```(?:json)?\s*", "", cleaned).strip()
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if not match:
            return []
        try:
            parsed = json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse LLM SUT tetkik selection: %s", raw[:200])
            return []

        suggestions: list[SUTSuggestion] = []
        for item in parsed[:10]:
            suggestions.append(
                SUTSuggestion(
                    kodu=item.get("kodu", ""),
                    adi=item.get("adi", ""),
                    brans=item.get("brans", ""),
                    confidence=float(item.get("confidence", 0.5)),
                    reasoning=item.get("reasoning", ""),
                )
            )
        return suggestions
