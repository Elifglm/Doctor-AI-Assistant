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
    get_anamnesis_sections,
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
        sut_suggestion_service: Any | None = None,
    ) -> None:
        self.ner = ner
        self.rag = rag
        self.llm = llm
        self.icd10 = icd10_suggestion_service
        self.sut = sut_suggestion_service

    # ------------------------------------------------------------------
    # Batch prompt helpers
    # ------------------------------------------------------------------

    def _build_batch_prompt(
        self,
        transcript: str,
        entities: list[MedicalEntity],
        grouped: dict[str, list[MedicalEntity]],
        brans: str | None = None,
    ) -> str:
        """Build the user-message prompt for batch anamnesis generation.

        For dahiliye, uses the rich 26-field template with explicit jargon
        rules, format examples and self-check section. For other branches
        (ortopedi for now) falls back to the compact field-list format.
        """
        normalized_brans = (brans or "").strip().lower()
        if normalized_brans == "ortopedi":
            return self._build_compact_prompt(transcript, brans)
        # default: dahiliye (richer template)
        return self._build_dahiliye_prompt(transcript, entities)

    @staticmethod
    def _build_compact_prompt(transcript: str, brans: str | None) -> str:
        """Compact field-list prompt used for branches without a rich template."""
        sections = get_anamnesis_sections(brans)
        fields = ", ".join(
            f'"{k}": "{v["title"]}"' for k, v in sections.items()
        )
        return (
            f"<TRANSKRIPT>\n{transcript}\n</TRANSKRIPT>\n\n"
            f"Yukaridaki transkriptten HBYS anamnez raporu olustur.\n"
            f"SADECE transkriptte gecen bilgileri yaz. Transkriptte olmayan bilgi EKLEME.\n"
            f"BUYUK HARF kullan. Bilgi parcalarini '----' ile ayir.\n"
            f"Bilgi yoksa bos string ver.\n"
            f"Vital degerler (sistolik, diyastolik, nabiz, ates, so2, kilo, boy) icin SADECE sayi yaz.\n"
            f"icd10_list ve sut_tetkik_list alanlari icin bos string ver, bu alanlar ayrica olusturulacak.\n\n"
            f"Alanlar: {{{fields}}}\n\n"
            f"SADECE JSON yanit ver: {{\"alan_key\": \"icerik\", ...}}"
        )

    @staticmethod
    def _build_dahiliye_prompt(
        transcript: str, entities: list[MedicalEntity]
    ) -> str:
        """Rich 26-field anamnez prompt with jargon + format + examples."""
        if entities:
            entity_lines = [
                f"- [{e.label}] {e.text}" for e in entities[:40]
            ]
            entities_str = "\n".join(entity_lines)
        else:
            entities_str = "(NER ciktisi verilmedi)"

        return f"""<transcript>
{transcript}
</transcript>

<entities>
{entities_str}
</entities>

<gorev>
Yukarıdaki dahiliye görüşme transkriptinden 26 alanlı anamnez JSON raporunu \
üret. 26 alanın tamamı çıktıda yer almalı. Aşağıdaki alan tanımlarını, jargon \
dönüşümlerini ve format kurallarını uygula.
</gorev>

<alan_tanimlari>
1.  hastanin_yakinmasi      — Hastanın baş şikayetleri. BÜYÜK HARF. Birden fazla şikayet `+` ile (örn: BAS AGRISI + BAS DONMESI). Yoksa "BELIRTILMEDI".
2.  hastanin_oykusu         — Şikayetin başlangıcı, süresi, lokalizasyon, faktörler. BÜYÜK HARF. Her bilgi `----` ile ayrı (örn: 2 HAFTA ONCE BASLAYAN ---- SOL TARAFLI ---- ZONKLAYICI). Yoksa "BELIRTILMEDI".
3.  oz_gecmisi_soy_gecmisi  — Hastanın kendi kronik hastalıkları/operasyonları. BÜYÜK HARF. Her tanı/operasyon `----`; ilgili ilaç `///` ile (örn: HT (10 YILDIR) /// AMLODIPIN 5 MG 1X1 ---- DM (5 YILDIR) /// METFORMIN 1000 MG 2X1). Yoksa "BELIRTILMEDI".
4.  soy_gecmisi             — Aile hastalık öyküsü. BÜYÜK HARF. Aile bireyi başına `----` (örn: ANNE HT + DM ---- BABA KAH). Yoksa "BELIRTILMEDI".
5.  sigara                  — KULLANIYOR (X PAKET/GUN, Y YILDIR) / KULLANMIYOR / BIRAKMIS (X YIL ONCE). Belirtilmediyse "BELIRTILMEDI".
6.  alkol                   — SOSYAL DUZEYDE / DUZENLI / KULLANMIYOR. Belirtilmediyse "BELIRTILMEDI".
7.  alerji                  — İlaç adı (reaksiyon) / "BILINEN ALERJISI YOK". Belirtilmediyse "".
8.  muayene_bulgulari       — BÜYÜK HARF, virgülle ayrı (örn: GD IYI, KOOPERE, BATIN RAHAT, KVS S1-S2 DOGAL). Yoksa "BELIRTILMEDI".
9.  sistolik                — Sadece sayı (örn: 160). Yoksa "".
10. diyastolik              — Sadece sayı (örn: 90). Yoksa "".
11. so2                     — Sadece sayı (örn: 98). Yoksa "".
12. nabiz                   — Sadece sayı (örn: 78). Yoksa "".
13. ates                    — Sadece sayı, virgüllü olabilir (örn: 36.4). Yoksa "".
14. tedavi                  — Reçete/öneri tedavi. BÜYÜK HARF. Her kalem `----`; ilaç + doz + sıklık (örn: RAMIPRIL 5 MG 1X1 ---- METOPROLOL 50 MG 1X1). Yoksa "BELIRTILMEDI".
15. oneri                   — Yaşam tarzı/diyet önerileri. BÜYÜK HARF. Her öneri `----` (örn: TUZ KISITLAMASI ---- DUZENLI EGZERSIZ). Yoksa "".
16. uyari                   — İlaç etkileşimi/alerji uyarısı. BÜYÜK HARF. Yoksa "".
17. kontrol_zamani          — BÜYÜK HARF (örn: 1 HAFTA SONRA TANSIYON KONTROLU). Yoksa "".
18. agri_skalasi            — Sayı veya "VAS X" (örn: 7 veya VAS 7). Yoksa "".
19. kilo                    — Sadece sayı (kg). Yoksa "".
20. boy                     — Sadece sayı (cm). Yoksa "".
21. sikayet_baslangic_tarihi — BÜYÜK HARF (örn: 2 HAFTA ONCE / 3 GUN ONCE / 1 YILDIR). Yoksa "BELIRTILMEDI".
22. konsultasyon_muayene    — Doktorun istediği muayene/tetkik (örn: KARDIYOLOJI KONSULTASYONU, ABDOMEN USG). KRITIK ALAN — retrieval bunu kullanır. Yoksa "".
23. konsultasyon_sonuc      — Konsültasyon sonucu varsa. Yoksa "".
24. konsultasyon_oneri      — Konsültasyondan gelen öneriler. Yoksa "".
25. icd10_list              — DAİMA "" boş bırak. Ayrı pipeline doldurur.
26. sut_tetkik_list         — DAİMA "" boş bırak. Ayrı pipeline doldurur.
</alan_tanimlari>

<jargon_donusumu>
KONUŞMA DİLİ → ANAMNEZ JARGONU dönüşümü zorunludur. Aşağıdakiler en sık olanlar:

Aile bireyleri (soy_gecmisi):
- "annem/annemde"  → ANNE
- "babam/babamda"  → BABA
- "kardeşim/abim/ablam" → KARDES
- "anneannem"      → ANNE TARAFI BUYUKANNE
- "babaannem"      → BABA TARAFI BUYUKANNE
- "dedem" (taraf belirsizse) → BUYUKBABA  (taraf belliyse "ANNE TARAFI BUYUKBABA" / "BABA TARAFI BUYUKBABA")

Şikayetler (hastanin_yakinmasi):
- "başım ağrıyor"           → BAS AGRISI
- "midem yanıyor"           → EPIGASTRIK YANMA
- "göğsümde sıkışma"        → RETROSTERNAL SIKISMA
- "nefes alamıyorum"        → DISPNE
- "halsizim"                → HALSIZLIK
- "midem bulanıyor"         → BULANTI
- "baş dönmesi"             → VERTIGO
- "bacaklarım şişiyor"      → ALT EKSTREMITE ODEMI
- "kabızım"                 → KONSTIPASYON
- "ishal"                   → DIYARE

Kronik hastalıklar (oz_gecmisi_soy_gecmisi, soy_gecmisi):
- "şeker hastalığı/şekerim" → DM
- "tansiyon/yüksek tansiyon"→ HT
- "kalp hastalığı"          → KAH (sadece doktor onaylarsa)
- "tiroid/guatr"            → TIROID HASTALIGI
- "böbrek yetmezliği"       → KBY
- "felç geçirdim"           → INME OYKUSU
- "astım"/"KOAH"            → ASTIM / KOAH (zaten jargon)

Sayısal ifadeler:
- "tansiyon yüz altmış sekilen yüz" → sistolik=160, diyastolik=100
- "bir paket sigara on yıl"         → KULLANIYOR (1 PAKET/GUN, 10 YILDIR)
- İlaç adı belirtilmemişse: "tansiyon hapı" → ANTIHIPERTANSIF KULLANIYOR (doz uydurma)
</jargon_donusumu>

<format_kurallari>
- Birden fazla şikayet: `+` ile ayır. "VE" YASAK.
  Doğru:   "BAS AGRISI + BAS DONMESI"
  Yanlış:  "BAS AGRISI VE BAS DONMESI"

- Birden fazla bilgi (öykü, tedavi, soy_gecmisi, oneri): `----` (4 tire) ile ayır.
  Doğru:   "2 HAFTA ONCE BASLAYAN ---- SOL TARAFLI"
  Yanlış:  "2 HAFTA ONCE BASLAYAN, SOL TARAFLI"

- Tanı + ilgili ilaç: `///` (3 slash) ile bağla.
  Doğru:   "HT (10 YILDIR) /// AMLODIPIN 5 MG 1X1"

- Sayısal alanlar (sistolik, diyastolik, nabiz, so2, ates, kilo, boy):
  Sadece sayı, BIRIM YOK. Doğru: 165 / Yanlış: "165 mmHg"

- icd10_list ve sut_tetkik_list: HER ZAMAN "" (boş string). Asla doldurma.
</format_kurallari>

<ornekler>
<example index="1" odak="ASR_hatasi_ve_jargon_donusumu">
Mini transcript:
"Hasta: Babamda hipertansiyon vardı, şeker hastalığı da vardı. (ASR çıktısı: 'dedemde' yazıyor olabilir.)
Doktor: Annenizde ne vardı?
Hasta: Annemde tiroid var, ilaç kullanıyor."

Doğru çıktı parçası:
{{
  "soy_gecmisi": "BABA HT + DM ---- ANNE TIROID HASTALIGI"
}}

Yanlış çıktı (kaçınılması gereken):
{{
  "soy_gecmisi": "DEDEMDE HT VARDI, ANNEMDE TIROID VAR"
}}
</example>

<example index="2" odak="bos_alan_ve_format_kuralı">
Mini transcript:
"Doktor: Şikayetiniz nedir?
Hasta: Başım ağrıyor, başım da dönüyor 2 haftadır.
Doktor: Tansiyonunuz 165 ve 100 olarak ölçüldü.
Doktor: Sigara kullanıyor musunuz?
Hasta: Hayır."

Doğru çıktı parçası:
{{
  "hastanin_yakinmasi": "BAS AGRISI + BAS DONMESI",
  "sikayet_baslangic_tarihi": "2 HAFTA ONCE",
  "sistolik": "165",
  "diyastolik": "100",
  "sigara": "KULLANMIYOR",
  "alkol": "BELIRTILMEDI",
  "kilo": "",
  "boy": "",
  "icd10_list": "",
  "sut_tetkik_list": ""
}}
</example>
</ornekler>

<son_kontroller>
JSON'u üretmeden önce kendi çıktını şu kontrollerle doğrula:
1. Çıktıda 26 anahtarın TAMAMI var mı?
2. Her metin alanı format kuralına (BÜYÜK HARF, +, ----, ///) uyuyor mu?
3. Sayısal alanlarda birim/yazı VAR mı? (Olmamalı.)
4. Transkriptte geçmeyen bir bilgi sızdı mı? (Sızmamalı.)
5. icd10_list ve sut_tetkik_list "" mi?
6. Aile/şikayet/kronik hastalık ifadeleri jargon karşılığına çevrildi mi?
</son_kontroller>

Şimdi 26 alanlı JSON çıktısını üret. Sadece JSON yaz, başka bir şey yazma."""

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
        brans: str | None = None,
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
        brans_sections = get_anamnesis_sections(brans)
        section_keys = list(brans_sections.keys())
        sections: list[dict[str, Any]] = []

        await _progress("generating", "Tum alanlar olusturuluyor...", 0.3)

        # Build a single prompt for all sections
        batch_prompt = self._build_batch_prompt(full_text, entities, grouped, brans)
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
            meta = brans_sections[key]
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

        # 4. ICD-10: Report fields → NER → Vector DB → LLM selection
        report_sections = {s["key"]: s["content"] for s in sections}
        icd_suggestions = await self._generate_icd10(sections, report_sections)

        # 4b. SUT Tetkik: transcript + ICD context → Vector DB → LLM selection
        await self._generate_sut_tetkik(sections, report_sections, full_text, icd_suggestions)

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
        self, sections: list[dict[str, Any]], report_sections: dict[str, str]
    ) -> list[str]:
        """Generate ICD-10 suggestions using report fields → Vector DB → LLM pipeline.

        Returns list of ICD-10 diagnosis descriptions for use by SUT pipeline.
        """
        if self.icd10 is None:
            return []

        icd10_section: dict[str, Any] | None = None
        for section in sections:
            if section["key"] == "icd10_list":
                icd10_section = section
                break

        if icd10_section is None:
            return []

        try:
            suggestions = await self.icd10.suggest_from_report(report_sections)
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
                return [s.tani for s in suggestions]
            else:
                logger.info("ICD-10 pipeline returned no suggestions")
                return []
        except Exception:
            logger.exception("ICD-10 pipeline failed")
            return []

    # ------------------------------------------------------------------
    # SUT Tetkik: NER → Vector DB → LLM selection
    # ------------------------------------------------------------------

    async def _generate_sut_tetkik(
        self, sections: list[dict[str, Any]], report_sections: dict[str, str],
        transcript: str = "", icd_diagnoses: list[str] | None = None
    ) -> None:
        """Generate SUT tetkik suggestions using transcript + ICD context → Vector DB → LLM pipeline.

        Only suggests tetkik if the doctor actually requested tests in the conversation.
        ICD diagnoses are used to improve accuracy, not to force suggestions.
        """
        if self.sut is None:
            return

        sut_section: dict[str, Any] | None = None
        for section in sections:
            if section["key"] == "sut_tetkik_list":
                sut_section = section
                break

        if sut_section is None:
            return

        try:
            # Use transcript directly — tetkik names are in conversation, not report fields
            # ICD diagnoses passed as context to improve accuracy (not to force suggestions)
            suggestions = await self.sut.suggest(
                transcript, icd_context=icd_diagnoses
            ) if transcript else []
            if not suggestions:
                suggestions = await self.sut.suggest_from_report(report_sections)
            if suggestions:
                sut_text = "\n".join(
                    f"({s.kodu}) - {s.adi} [%{int(s.confidence * 100)}]"
                    for s in suggestions
                )
                sut_section["content"] = sut_text
                sut_section["confidence"] = (
                    "high" if suggestions[0].confidence >= 0.7 else "medium"
                )
                logger.info(
                    "SUT tetkik pipeline generated %d suggestions", len(suggestions)
                )
            else:
                logger.info("SUT tetkik pipeline returned no suggestions")
        except Exception:
            logger.exception("SUT tetkik pipeline failed")

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
        brans: str | None = None,
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
        brans_sections = get_anamnesis_sections(brans)
        section_keys = list(brans_sections.keys())
        sections: list[dict[str, Any]] = []

        for i, key in enumerate(section_keys):
            meta = brans_sections[key]
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

            # Skip icd10_list and sut_tetkik_list — already validated against DB,
            # formal names won't appear verbatim in the transcript
            if key in ("icd10_list", "sut_tetkik_list"):
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
