"""ICD-10 suggestion service: NER → Vector DB → LLM selection pipeline."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from apps.backend.src.schemas.icd10 import ICD10Suggestion
from apps.backend.src.services.icd10_service import ICD10Service
from apps.backend.src.services.icd10_vector_service import ICD10VectorService
from apps.backend.src.services.llm_base import LLMProvider

logger = logging.getLogger(__name__)

# LLM prompt for selecting from candidates
ICD10_SELECTION_PROMPT = """\
Sen bir deneyimli tibbi kodlama uzmanisin. Asagida bir doktor-hasta gorusme \
transkripti ve ICD-10 aday kodlari verilmistir.

GOREV: Aday kodlardan transkripte KLINIK OLARAK en uygun olanlari sec.

KRITIK KURALLAR:
1. SADECE kelime eslesmesine bakma, KLINIK BAGLAMI degerlendir.
   - Ornek: Hasta "basim donuyor" diyorsa ve anemi bulgulari varsa (halsizlik, solukluk,
     dusuk hemoglobin), R42 (Vertigo) SECME — bu semptom aneminin sonucu.
   - Semptom kodlari (R grubu) yerine ALTTA YATAN HASTALIK kodlarini tercih et.
2. AYIRICI TANI mantigi kullan:
   - Bir semptom baska bir hastaligin sonucu olabilir mi? Eger evetse semptom kodunu SECME.
   - Ornek: Bas donmesi + halsizlik + solukluk = Anemi (D50), Vertigo (R42) degil.
   - Ornek: Karin agrisi + ishal + ates = Gastroenterit (A09), karin agrisi (R10) degil.
3. Eger doktor acik bir tani soyluyorsa (ornek: "akut gastrit"), o taniyi yuksek guvenle sec.
4. Maksimum 5 kod sec. Semptom kodlari ancak altta yatan hastalik bulunamazsa secilmeli.
5. Her kod icin guven skoru (0.0-1.0) ve NEDEN sectigini acikla.
6. Sadece JSON formatinda yanit ver.

TRANSKRIPT:
{transcript}

ADAY ICD-10 KODLARI:
{candidates}

Yanit (sadece JSON, baska bir sey yazma):
[
  {{"icd_kodu": "D50", "tani": "Demir eksikligi anemisi", "confidence": 0.90, "reasoning": "Hasta halsizlik, solukluk ve bas donmesi tarif ediyor - anemi bulgulari"}}
]

Hicbir aday uygun degilse bos liste don: []
"""

ICD10_REPORT_SELECTION_PROMPT = """\
Sen bir deneyimli tibbi kodlama uzmanisin. Asagida bir anamnez raporunun ilgili \
alanlari ve ICD-10 aday kodlari verilmistir.

GOREV: Aday kodlardan rapora KLINIK OLARAK en uygun olanlari sec.

KRITIK KURALLAR:
1. SADECE kelime eslesmesine bakma, KLINIK BAGLAMI degerlendir.
   - Semptom kodlari (R grubu) yerine ALTTA YATAN HASTALIK kodlarini tercih et.
   - Bir semptom baska bir hastaligin sonucu olabiliyorsa, semptom kodunu SECME.
   - Ornek: "Bas donmesi" + anemi bulgulari varsa → D50 (Anemi) sec, R42 (Vertigo) SECME.
   - Ornek: "Karin agrisi" + gastrit bulgulari varsa → K29 (Gastrit) sec, R10 (Karin agrisi) SECME.
2. AYIRICI TANI mantigi:
   - Raporun tum alanlarini bir arada degerlendir (sikayet + oykü + muayene + konsultasyon sonucu).
   - Doktorun konsultasyon sonucunda yazdigi taniyi EN YUKSEK guvenle sec.
   - Birden fazla hastalik varsa hepsini listele (ornek: anemi + gastrit ayni anda olabilir).
3. SPESIFIKLIK KURALI — alt-tip secimi:
   - ICD-10 hiyerarsiktir (ornek: J44 → J44.0, J44.1, J44.8, J44.9).
   - Spesifik alt-tip kodu (J44.0 "akut enfeksiyonlu", J44.1 "akut alevlenmeli") \
     SADECE raporda o alt-tipin AYIRICI klinik bulgulari acikca varsa SECILEBILIR.
   - Yetersiz kanit varsa "tanimlanmamis" alt kodu (.9 ile biten) tercih et.
   - Ornekler:
     * KOAH ana tani var, ama akut enfeksiyon (ates, purulan balgam) yok → \
       J44.9 (KOAH NOS) sec, J44.0 SECME.
     * "Akut alevlenme" ifadesi rapora yazilmamissa → J44.1 SECME, J44.9 sec.
     * Diyabet var ama tip belirsiz → E11.9 (Tip 2 NOS) sec, E11.0 (komali) \
       sadece koma dökümante edilmisse SECILIR.
     * Hipertansiyon var ama komplikasyon yok → I10 (essansiyel HT) sec, \
       I11 (HT + kalp tutulumu) SADECE LVH/kalp yetmezligi varsa SECILIR.
   - Kural ozeti: "SUPHE durumunda DAHA AZ spesifik kod sec."
4. Maksimum 5 kod sec.
5. Her kod icin guven skoru (0.0-1.0) ve NEDEN sectigini acikla.
6. Sadece JSON formatinda yanit ver.

ANAMNEZ RAPORU:
{report_text}

ADAY ICD-10 KODLARI:
{candidates}

Yanit (sadece JSON, baska bir sey yazma):
[
  {{"icd_kodu": "D50", "tani": "Demir eksikligi anemisi", "confidence": 0.90, "reasoning": "Raporda halsizlik, solukluk ve bas donmesi — anemi bulgulari"}}
]

Hicbir aday uygun degilse bos liste don: []
"""


class ICD10SuggestionService:
    """NER → Vector DB search → LLM selection pipeline for ICD-10 coding.

    Pipeline:
    1. NER extracts medical terms from transcript
    2. Vector DB finds candidate ICD-10 codes for each term
    3. LLM selects the most appropriate codes from candidates
    """

    def __init__(
        self,
        llm: LLMProvider,
        icd10_service: ICD10Service,
        vector_service: ICD10VectorService | None = None,
        ner_service: Any | None = None,
    ) -> None:
        self._llm = llm
        self._icd10 = icd10_service
        self._vectors = vector_service
        self._ner = ner_service

    async def suggest(self, transcript: str) -> list[ICD10Suggestion]:
        """Full pipeline: NER → Vector DB → LLM selection."""

        # Step 1: Extract medical terms via NER
        ner_terms = await self._extract_ner_terms(transcript)
        logger.info("NER extracted %d terms: %s", len(ner_terms), ner_terms[:5])

        # Step 2: Find candidate ICD-10 codes via vector DB
        candidates = await self._find_vector_candidates(ner_terms)
        logger.info("Vector DB found %d candidate codes", len(candidates))

        if not candidates:
            logger.warning("No ICD-10 candidates found from vector search")
            return []

        # Step 3: LLM selects from candidates
        suggestions = await self._llm_select(transcript, candidates)
        logger.info("LLM selected %d ICD-10 codes", len(suggestions))

        return suggestions

    # ------------------------------------------------------------------
    # Report-based suggestion (structured data → better ICD-10)
    # ------------------------------------------------------------------

    # Anahtar bölümler — LLM'e aktarılan rapor alanları. ICD-10 için tanı
    # bilgisi ağırlıklı olduğundan kesin/ön tanı, klinik öykü ve muayene
    # bulguları öncelikli; konsültasyon görüşleri tanıyı netleştirir.
    _RELEVANT_KEYS = {
        # Tanı / klinik durum
        "hastanin_yakinmasi", "hastanin_oykusu", "muayene_bulgulari",
        "on_tani", "kesin_tani",
        # Geçmiş
        "oz_gecmisi_soy_gecmisi", "soy_gecmisi",
        # Konsültasyon — uzman görüşü tanıyı sağlamlaştırır
        "konsultasyon_muayene", "konsultasyon_sonuc", "konsultasyon_oneri",
        # Plan
        "tedavi",
    }

    async def suggest_from_report(
        self, report_sections: dict[str, str]
    ) -> list[ICD10Suggestion]:
        """Generate ICD-10 suggestions from structured report fields.

        Uses report fields (complaint, history, findings) instead of raw
        transcript for more accurate ICD-10 matching.
        """
        # Build search text from relevant report fields
        search_parts: list[str] = []
        for key in self._RELEVANT_KEYS:
            val = report_sections.get(key, "").strip()
            if val and val not in {"BELIRTILMEDI", "BELIRTILMEDI.", ""}:
                search_parts.append(val)

        if not search_parts:
            logger.warning("No relevant report fields for ICD-10 suggestion")
            return []

        report_text = "\n".join(search_parts)

        # Step 1: Extract medical terms from report text
        ner_terms = await self._extract_ner_terms(report_text)
        logger.info("Report NER extracted %d terms: %s", len(ner_terms), ner_terms[:5])

        # Also extract terms directly from report fields (split by ----)
        for part_text in search_parts:
            for fragment in part_text.split("----"):
                fragment = fragment.strip()
                if fragment and len(fragment) > 2 and fragment not in {"BELIRTILMEDI", "BELIRTILMEDI."}:
                    if fragment not in ner_terms:
                        ner_terms.append(fragment)

        # Step 2: Find candidate ICD-10 codes via vector DB + text search
        candidates = await self._find_vector_candidates(ner_terms)
        # Also add text search results for better coverage
        text_candidates = await self._text_search_fallback(ner_terms)
        seen = {c["icd_kodu"] for c in candidates}
        for tc in text_candidates:
            if tc["icd_kodu"] not in seen:
                seen.add(tc["icd_kodu"])
                candidates.append(tc)

        # Step 2b: Hierarchical fallback — for every candidate that's a
        # specific subcode (e.g. J44.0), make sure the "unspecified" sibling
        # (J44.9) and the bare parent (J44) are also offered to the LLM.
        # Without this the LLM is forced to pick a specific subtype even when
        # the report lacks evidence to distinguish among them, leading to
        # over-coding (e.g. J44.0 chosen when only J44.9 is supported).
        await self._augment_with_unspecified(candidates, seen)

        logger.info("Report combined %d candidates (vector + text + unspec)", len(candidates))

        if not candidates:
            return []

        # Step 3: LLM selects from candidates using report context
        suggestions = await self._llm_select_from_report(report_text, candidates)
        logger.info("Report LLM selected %d ICD-10 codes", len(suggestions))

        return suggestions

    async def _llm_select_from_report(
        self, report_text: str, candidates: list[dict[str, Any]]
    ) -> list[ICD10Suggestion]:
        """Ask LLM to select ICD-10 codes based on structured report."""
        candidates_text = "\n".join(
            f"({c['icd_kodu']}) - {c['tani']} [skor: {c['score']:.2f}]"
            for c in candidates
        )

        prompt = ICD10_REPORT_SELECTION_PROMPT.format(
            report_text=report_text,
            candidates=candidates_text,
        )

        try:
            raw = await self._llm.generate(prompt, "")
        except Exception:
            logger.exception("LLM ICD-10 report selection failed")
            return [
                ICD10Suggestion(
                    icd_kodu=c["icd_kodu"],
                    tani=c["tani"],
                    confidence=c["score"],
                    reasoning=f"Vektörel arama: {c['source']}",
                )
                for c in candidates[:5]
            ]

        return self._parse_llm_selection(raw)

    # ------------------------------------------------------------------
    # Step 1: NER extraction
    # ------------------------------------------------------------------

    async def _extract_ner_terms(self, transcript: str) -> list[str]:
        """Extract medical terms from transcript using GLiNER NER."""
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

        # Fallback: simple keyword extraction from transcript
        if not terms:
            terms = self._extract_keywords(transcript)
            logger.info("Keyword fallback extracted: %s", terms)

        return terms

    @staticmethod
    def _extract_keywords(transcript: str) -> list[str]:
        """Simple keyword extraction as NER fallback."""
        # Common medical keywords in Turkish
        medical_keywords = {
            "ağrı", "agri", "ağrısı", "agrisi", "şeker", "seker",
            "tansiyon", "ateş", "ates", "öksürük", "oksuruk",
            "bulantı", "bulanti", "kusma", "baş dönmesi", "bas donmesi",
            "nefes darlığı", "nefes darligi", "halsizlik", "yorgunluk",
            "kilo kaybı", "kilo kaybi", "kilo alma", "çarpıntı", "carpinti",
            "ishal", "kabızlık", "kabizlik", "kanama", "şişlik", "sislik",
            "idrara çıkma", "idrara cikma", "su içme", "su icme",
            "bulanık görme", "bulanik gorme", "uyuyamama",
            "diyabet", "hipertansiyon", "astım", "koah",
        }

        transcript_lower = transcript.lower()
        found: list[str] = []

        for keyword in medical_keywords:
            if keyword in transcript_lower:
                found.append(keyword)

        # Also extract phrases after "şikayeti", "ağrısı", etc.
        # Extract speaker lines for context
        lines = transcript.split("\n")
        for line in lines:
            if "hasta:" in line.lower():
                found.append(line.split(":", 1)[-1].strip()[:100])

        return found[:10]

    # ------------------------------------------------------------------
    # Step 2: Vector DB search
    # ------------------------------------------------------------------

    async def _find_vector_candidates(
        self, terms: list[str]
    ) -> list[dict[str, Any]]:
        """Search vector DB for candidate ICD-10 codes."""
        if self._vectors is None or not self._vectors.is_ready:
            logger.warning("ICD10VectorService not available, using text search fallback")
            return await self._text_search_fallback(terms)

        results = await self._vectors.search_multiple(
            terms, n_per_term=3, min_score=0.45
        )

        candidates = []
        for r in results[:20]:
            candidates.append({
                "icd_kodu": r.icd_kodu,
                "tani": r.tani,
                "score": r.score,
                "source": r.source_term,
            })
        return candidates

    async def _augment_with_unspecified(
        self,
        candidates: list[dict[str, Any]],
        seen: set[str],
    ) -> None:
        """Mutate ``candidates`` to also include parent + ".9" siblings.

        For each candidate code (e.g. ``J44.0``), look up the "unspecified"
        sibling (``J44.9``) and the bare parent (``J44``) and append them to
        the candidate pool if missing. This gives the LLM the option to
        downshift to a less-specific code when the report lacks evidence for
        the specific subtype.
        """
        # Collect parent prefixes that need unspecified siblings.
        wanted: set[str] = set()
        for c in list(candidates):
            kodu = (c.get("icd_kodu") or "").strip()
            if not kodu:
                continue
            # Already an unspecified or bare parent — nothing to add.
            if "." not in kodu:
                wanted.add(f"{kodu}.9")
                continue
            parent = kodu.split(".", 1)[0]
            wanted.add(parent)
            wanted.add(f"{parent}.9")

        # Remove anything we already have.
        wanted -= seen
        if not wanted:
            return

        # SQL fetch — single query for all wanted codes.
        try:
            rows = await self._icd10.get_by_codes(list(wanted))
        except AttributeError:
            # Fallback if the service doesn't expose a batch lookup yet.
            rows = []
            for code in wanted:
                row = await self._icd10.get_by_code(code)
                if row:
                    rows.append(row)
        for row in rows:
            kodu = row.get("icd_kodu") if isinstance(row, dict) else getattr(row, "icd_kodu", None)
            tani = row.get("tani") if isinstance(row, dict) else getattr(row, "tani", None)
            if not kodu or kodu in seen:
                continue
            seen.add(kodu)
            candidates.append({
                "icd_kodu": kodu,
                "tani": tani or "",
                "score": 0.50,  # marked as fallback / hierarchical filler
                "source": "unspecified-fallback",
            })

    async def _text_search_fallback(
        self, terms: list[str]
    ) -> list[dict[str, Any]]:
        """Fallback: text-based ICD-10 search when vector DB is unavailable.

        Also splits compound terms (e.g. 'MIDE BULANTIASI') into individual
        words and searches each word separately for better coverage.
        """
        candidates = []
        seen: set[str] = set()

        # Build expanded search terms: original + individual words
        expanded: list[str] = []
        for term in terms[:10]:
            expanded.append(term)
            # Split compound terms and ---- separated parts
            for part in term.replace("----", " ").split():
                part = part.strip()
                if len(part) > 3 and part not in expanded:
                    expanded.append(part)

        for term in expanded[:15]:
            results = await self._icd10.search(term, limit=3)
            for r in results:
                if r.icd_kodu not in seen:
                    seen.add(r.icd_kodu)
                    candidates.append({
                        "icd_kodu": r.icd_kodu,
                        "tani": r.tani,
                        "score": 0.5,
                        "source": term,
                    })
        return candidates

    # ------------------------------------------------------------------
    # Step 3: LLM selection
    # ------------------------------------------------------------------

    async def _llm_select(
        self, transcript: str, candidates: list[dict[str, Any]]
    ) -> list[ICD10Suggestion]:
        """Ask LLM to select the most relevant codes from candidates."""
        candidates_text = "\n".join(
            f"({c['icd_kodu']}) - {c['tani']} [kaynak: \"{c['source']}\", skor: {c['score']:.2f}]"
            for c in candidates
        )

        prompt = ICD10_SELECTION_PROMPT.format(
            transcript=transcript,
            candidates=candidates_text,
        )

        try:
            raw = await self._llm.generate(prompt, "")
        except Exception:
            logger.exception("LLM ICD-10 selection failed")
            # Return top candidates without LLM filtering
            return [
                ICD10Suggestion(
                    icd_kodu=c["icd_kodu"],
                    tani=c["tani"],
                    confidence=c["score"],
                    reasoning=f"Vektörel arama: {c['source']}",
                )
                for c in candidates[:5]
            ]

        return self._parse_llm_selection(raw)

    @staticmethod
    def _parse_llm_selection(raw: str) -> list[ICD10Suggestion]:
        """Parse LLM's JSON selection response."""
        # Strip markdown code blocks (```json ... ```)
        cleaned = raw.strip()
        if "```" in cleaned:
            cleaned = re.sub(r"```(?:json)?\s*", "", cleaned).strip()
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if not match:
            return []
        try:
            parsed = json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse LLM ICD-10 selection: %s", raw[:200])
            return []

        suggestions: list[ICD10Suggestion] = []
        for item in parsed[:5]:
            suggestions.append(
                ICD10Suggestion(
                    icd_kodu=item.get("icd_kodu", ""),
                    tani=item.get("tani", ""),
                    confidence=float(item.get("confidence", 0.5)),
                    reasoning=item.get("reasoning", ""),
                )
            )
        return suggestions
