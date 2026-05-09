"""HyDE (Hypothetical Document Embeddings) for medical RAG.

Reference: Gao et al. 2022, arXiv:2212.10496
"Precise Zero-Shot Dense Retrieval without Relevance Labels"

Standard RAG embeds the QUERY (transcript snippet, NER terms) and searches.
Problem: query distribution ≠ document distribution. A patient dialogue
is structurally very different from a formal ICD-10 description.

HyDE workaround: ask the LLM to write a HYPOTHETICAL document that would
answer the query, embed THAT, and search. The hypothetical doc shares
distribution characteristics with the real corpus, so cosine similarity
becomes a more reliable retrieval signal.

For our pipeline:
  Input  : doctor-patient transcript (or anamnez fields)
  HyDE   : Haiku 4.5 generates a 2-3 sentence formal clinical summary
  Embed  : BGE-M3 encodes the summary
  Search : ChromaDB vector search over ICD-10 / SUT corpus

Expected gain (literature): +5-15 NDCG@10 in medical IR
(SL-HyDE on CMIRB: 59.38 vs vanilla 56.62)
"""
from __future__ import annotations

import logging
from typing import Any

from apps.backend.src.services.llm_base import LLMProvider

logger = logging.getLogger(__name__)


# Prompt templates — task-specific HyDE per AutoMIR (Zhou & Liu 2024)
# guidance: vague generic prompts cause LLM hallucination; specific
# clinical-summary task is more reliable.

_HYDE_PROMPT_ICD = """\
Aşağıdaki Türkçe doktor-hasta konsültasyon metnini formal bir klinik
epikriz cümlesine dönüştür. Çıktı:
- 2-3 cümle (max 50 kelime)
- Tıbbi terminolojiyi (ICD-10 standartına uygun) kullan
- Hastanın ana tanıları + önemli komorbiditelerini açıkça yaz
- Semptomları SADECE tanı koyulamayanlar için yaz (R-codes)
- Tedavi/tetkik istemini ATLA, sadece tanı odaklı

Örnek girdi: "Hocam ya bende şeker var biliyorsunuz, 8 yıl oldu. Tansiyonum
da yüksek, kontrolde tutmaya çalışıyorum, kolesterolüm de yüksek çıktı son
tahlilde."
Örnek çıktı: "58 yaşında erkek hasta, 8 yıllık tip 2 diabetes mellitus,
esansiyel hipertansiyon ve saf hiperkolesterolemi tanılı. Komplikasyon yok."

KONSÜLTASYON METNİ:
{transcript}

ÇIKTI (sadece klinik epikriz, başka bir şey yazma):
"""

_HYDE_PROMPT_SUT = """\
Aşağıdaki Türkçe doktor-hasta konsültasyon metninden sadece doktorun
İSTEDİĞİ tetkik/tahlilleri formal listeye dönüştür. Çıktı:
- Virgülle ayrılmış formal tetkik adları (max 15)
- SUT standartına uygun isimlendirme ("Tam Kan Sayımı", "HbA1c",
  "Total Kolesterol", "Kreatinin (Serum/Plazma)" gibi)
- Doktor "isteyelim/isteyeceğim/bakalım/çekilsin" dediği tetkikleri yaz
- Hasta sorularını ATLA, geçmişte yapılmış tetkikleri ATLA
- Hipotetik ("eğer X yüksekse Y bakarız") olanları ATLA

Örnek girdi: "Tahliller isteyelim: hemogram, açlık şekeri, HbA1c, kreatinin,
kolesterol paneli yani total kolesterol LDL HDL trigliserid, EKG çekilsin."
Örnek çıktı: "Tam Kan Sayımı (Hemogram), Açlık Kan Şekeri, Hemoglobin A1c,
Kreatinin (Serum/Plazma), Total Kolesterol, LDL Kolesterol, HDL Kolesterol,
Trigliserid, EKG."

KONSÜLTASYON METNİ:
{transcript}

ÇIKTI (sadece tetkik listesi, başka bir şey yazma):
"""


class HyDEService:
    """Generate hypothetical clinical documents for improved RAG retrieval.

    Usage:
        hyde = HyDEService(llm=anthropic_service)
        hypo_doc = await hyde.generate_for_icd(transcript)
        # then: embedding = bge_m3.encode(hypo_doc)
        # then: chroma.search(embedding, ...)
    """

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def generate_for_icd(self, transcript: str) -> str:
        """Generate hypothetical clinical summary for ICD-10 retrieval.

        Returns a formal 2-3 sentence epikriz suitable for embedding and
        searching against the ICD-10 corpus.

        On LLM failure, returns the original transcript truncated to first
        500 chars (graceful fallback — no retrieval gets worse).
        """
        if not transcript or not transcript.strip():
            return ""

        try:
            prompt = _HYDE_PROMPT_ICD.format(transcript=transcript[:3000])
            response = await self._llm.generate(prompt, "")
            cleaned = response.strip().strip('"\'')
            if not cleaned:
                logger.warning("HyDE ICD returned empty, falling back to transcript")
                return transcript[:500]
            logger.info("HyDE ICD generated %d chars from %d-char transcript",
                        len(cleaned), len(transcript))
            return cleaned
        except Exception:
            logger.exception("HyDE ICD generation failed; using fallback")
            return transcript[:500]

    async def generate_for_sut(self, transcript: str) -> str:
        """Generate hypothetical test order list for SUT retrieval."""
        if not transcript or not transcript.strip():
            return ""

        try:
            prompt = _HYDE_PROMPT_SUT.format(transcript=transcript[:3000])
            response = await self._llm.generate(prompt, "")
            cleaned = response.strip().strip('"\'')
            if not cleaned:
                logger.warning("HyDE SUT returned empty, falling back to transcript")
                return transcript[:500]
            logger.info("HyDE SUT generated %d chars from %d-char transcript",
                        len(cleaned), len(transcript))
            return cleaned
        except Exception:
            logger.exception("HyDE SUT generation failed; using fallback")
            return transcript[:500]
