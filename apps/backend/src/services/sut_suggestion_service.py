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
- SADECE transkriptte doktorun istedigi veya bahsettiği tetkikleri sec.
- Doktor tetkik istemiyorsa bos liste don.
- Doktorun kullandigi halk dilindeki ifadeleri dogru tetkikle esle \
  (ornek: "kan sayimi" = Hemogram, "seker" = Aclik kan sekeri).
- ICD-10 tanilari verilmisse, o taniya uygun tetkikleri oncelikle sec.
- Maksimum 10 tetkik sec.
- Her tetkik icin guven skoru (0.0-1.0) ver.
- Sadece JSON formatinda yanit ver.

TRANSKRIPT:
{transcript}
{icd_context}
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

GOREV: Aday tetkiklerden RAPORDA ACIKCA ISTENEN tetkikleri sec.

KURALLAR (KESIN):
- Rapordaki "konsultasyon_muayene", "tedavi", "oneri" gibi alanlarda \
  doktor hangi tetkikleri PLANLADIYSA SADECE onlari sec.
- Klinik pratikte standart tetkikleri SADECE rapor o yonde isaret \
  ediyorsa ekle (sikayetle uyumlu, doktor tarafindan dolayli istenmis).
- Aday listesinde olup raporda HIC BAHSEDILMEYEN tetkikleri SECME, \
  guven 0.5'in altina dusurmek yerine TAMAMEN ATLA.
- Halk dilindeki ifadeleri TAM kelime bazli degil, SEMANTIK olarak esle:
  * "kan tahlili" / "kan sayimi" / "hemogram" → L107020 (Tam Kan Sayimi)
  * "kan tahlili" *farkli bir test olan* "Gaitada gizli kan aranmasi" \
    DEGILDIR — kan tahlili istenince gaita testi SECILMEZ.
  * "karaciger enzimleri" → ALT (L100300) + AST (L101280)
  * "böbrek fonksiyonu" → kreatinin, BUN, GFR
  * "lipid paneli" → LDL, HDL, total kolestrol, trigliserid
  * "karın USG" / "batın ultrasonu" → 803570 (Tum Batin USG)
  * "EKG" → 530100 (basit EKG). "Holter" / "24 saat EKG" / "ritim holter" \
    SADECE bu ifadeler gectiyse seçilir (700540). Doktor sadece "EKG" \
    dediyse holter SECILMEZ.
  * "tiroid USG" / "boyun USG" / "tiroid ultrason" → 803320 (Boyun USG)
  * "tiroid testleri" / "tiroid paneli" → TSH (L107380) + Serbest T3 \
    (L106760) + Serbest T4 (L106770). Anti-TPO (L107060) ayrica istendiyse \
    eklenir, "tiroid testi" otomatik anti-TPO icermez.
- ICD-10 tanisi varsa o taniyla uyumsuz tetkikleri SECME.
- Maksimum 10 tetkik. Her biri icin guven skoru (0.0-1.0).
- Sadece JSON yaniti ver.

ANAMNEZ RAPORU:
{report_text}

ADAY TETKIKLER:
{candidates}

ORNEKLER:
[OK] "konsultasyon_muayene: kan tahlili, karaciger enzimleri istenmis"
     -> [Hemogram, ALT, AST] (Gaitada gizli kan SECILMEZ — alakasiz)
[OK] "tedavi: tiroid takibi" -> [TSH] (FT3/FT4 doktor istemediyse SECILMEZ)
[OK] "rapor tetkik plani icermiyor" -> [] (bos liste)

Yanit (sadece JSON):
[
  {{"kodu": "L107020", "adi": "Tam Kan Sayimi (Hemogram)", "confidence": 0.95, \
"reasoning": "Konsultasyon muayene alaninda kan tahlili planlanmis"}}
]

Hicbir aday gercekten uygun degilse: []
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
        self, transcript: str, brans: str | None = None,
        icd_context: list[str] | None = None
    ) -> list[SUTSuggestion]:
        """Full pipeline: NER → Vector DB → LLM selection."""
        ner_terms = await self._extract_ner_terms(transcript)
        logger.info("NER extracted %d terms: %s", len(ner_terms), ner_terms[:5])

        # If no tetkik terms found in transcript, don't suggest anything
        # ICD context alone should NOT trigger tetkik suggestions
        if not ner_terms:
            logger.info("No tetkik terms in transcript, skipping SUT suggestions")
            return []

        candidates = await self._find_vector_candidates(ner_terms, brans=brans)
        # Always add text search results for better coverage
        text_candidates = await self._text_search_fallback(ner_terms, brans=brans)
        seen = {c["kodu"] for c in candidates}
        for tc in text_candidates:
            if tc["kodu"] not in seen:
                seen.add(tc["kodu"])
                candidates.append(tc)

        if not candidates:
            logger.warning("No SUT tetkik candidates found")
            return []

        suggestions = await self._llm_select(
            transcript, candidates, icd_context=icd_context
        )
        logger.info("LLM selected %d SUT tetkik", len(suggestions))

        return suggestions

    # Keys whose content is forwarded to the SUT suggestion pipeline. The
    # konsultasyon_* fields commonly hold the explicit test plan (e.g.
    # "kan tahlili, karaciğer enzimleri, karın USG istenmesi planlanmış")
    # so they are critical for retrieval. Includes both dahiliye and
    # ortopedi-specific section keys.
    _RELEVANT_KEYS = {
        # Common
        "hastanin_yakinmasi", "hastanin_oykusu",
        "muayene_bulgulari",
        "oz_gecmisi_soy_gecmisi", "soy_gecmisi",
        "tedavi", "oneri", "uyari",
        "icd10_list", "sut_tetkik_list",
        # Konsultasyon — often the explicit test plan
        "konsultasyon_muayene", "konsultasyon_sonuc", "konsultasyon_oneri",
        # Ortopedi-specific
        "kesin_tani", "on_tani",
        "hastanede_kullanilan_ilaclar", "kullanmakta_oldugu_ilaclar",
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
        """Extract medical/test terms from transcript.

        Combines GLiNER NER with the keyword fallback. NER alone misses
        compact abbreviations (TSH, T3, T4, AST, ALT) and explicit code-list
        sections like "EKG ---- TSH ---- SERBEST T3 ---- SERBEST T4" because
        it tends to merge them into a generic "tiroid testleri" entity.
        Keyword extraction also splits known separators ("----", "+") so each
        test name reaches the vector search individually.
        """
        ner_terms: list[str] = []

        if self._ner is not None:
            try:
                if not self._ner.is_ready:
                    await self._ner.initialize()
                entities = await self._ner.extract(transcript)
                ner_terms = list({e.text for e in entities})
                logger.info("GLiNER NER found: %s", ner_terms)
            except Exception:
                logger.exception("NER extraction failed; relying on keyword fallback only")

        keyword_terms = self._extract_keywords(transcript)
        logger.info("Keyword extraction found: %s", keyword_terms)

        # Merge keeping NER first (richer phrases) then keywords; deduplicate
        # case-insensitively while preserving the original casing/order.
        seen: set[str] = set()
        merged: list[str] = []
        for term in ner_terms + keyword_terms:
            key = term.strip().lower()
            if key and key not in seen:
                seen.add(key)
                merged.append(term.strip())
        return merged

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

        # Anamnez raporu alanlarında doktor tetkik listesini "----" / "+" ile
        # ayırmış olabilir (örn konsultasyon_muayene = "EKG ---- TSH ---- SERBEST T3").
        # Bu açıkça yazılı testleri tek tek aday yapmak için ayrıştır.
        import re as _re
        for fragment in _re.split(r"-{2,}|\+|/{2,}|;|,", transcript):
            token = fragment.strip()
            # Yalnızca tetkik adı gibi görünen kısa parçalar — uzun cümleleri ele.
            if 2 <= len(token) <= 80 and not _re.search(r"[.!?]", token):
                # Sadece bir-iki kelimelik test/kod adı eklensin
                word_count = len(token.split())
                if word_count <= 5:
                    found.append(token)

        print(f"[SUT-DEBUG] keyword extraction found: {found}", flush=True)
        return found[:25]

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
        self, transcript: str, candidates: list[dict[str, Any]],
        icd_context: list[str] | None = None
    ) -> list[SUTSuggestion]:
        """Ask LLM to select the most relevant tetkik from candidates."""
        candidates_text = "\n".join(
            f"({c['kodu']}) - {c['adi']} [kaynak: \"{c['source']}\", skor: {c['score']:.2f}]"
            for c in candidates
        )

        icd_text = ""
        if icd_context:
            icd_text = "\nICD-10 TANILARI (referans):\n" + "\n".join(
                f"- {d}" for d in icd_context
            ) + "\n"

        prompt = SUT_SELECTION_PROMPT.format(
            transcript=transcript,
            candidates=candidates_text,
            icd_context=icd_text,
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
