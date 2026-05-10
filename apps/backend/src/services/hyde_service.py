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

import hashlib
import logging
import os
from pathlib import Path
from typing import Any

from apps.backend.src.services.llm_base import LLMProvider

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_CACHE_DIR = _PROJECT_ROOT / "data" / "hyde_cache"


def _cache_enabled() -> bool:
    """Disk-cache is on by default; turn off with ASR_HYDE_CACHE_ENABLED=false."""
    val = os.environ.get("ASR_HYDE_CACHE_ENABLED", "true").strip().lower()
    return val not in ("false", "0", "no", "off")


def _cache_key(layer: str, transcript: str) -> str:
    """Stable cache key: layer + first 16 hex of sha256 of normalized text."""
    norm = " ".join(transcript.split())[:3000]
    digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
    return f"{layer}_{digest}"


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

    def __init__(self, llm: LLMProvider, cache_dir: Path | None = None) -> None:
        self._llm = llm
        self._cache_dir = cache_dir or _DEFAULT_CACHE_DIR

    def _read_cache(self, layer: str, transcript: str) -> str | None:
        if not _cache_enabled():
            return None
        path = self._cache_dir / f"{_cache_key(layer, transcript)}.txt"
        if path.exists():
            try:
                cached = path.read_text(encoding="utf-8")
                logger.info("HyDE %s cache HIT (%s, %d chars)", layer, path.name, len(cached))
                return cached
            except Exception:
                logger.warning("HyDE cache read failed for %s", path)
        return None

    def _write_cache(self, layer: str, transcript: str, doc: str) -> None:
        if not _cache_enabled():
            return
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            path = self._cache_dir / f"{_cache_key(layer, transcript)}.txt"
            path.write_text(doc, encoding="utf-8")
        except Exception:
            logger.warning("HyDE cache write failed", exc_info=True)

    async def _generate(self, layer: str, prompt_template: str, transcript: str) -> str:
        if not transcript or not transcript.strip():
            return ""
        cached = self._read_cache(layer, transcript)
        if cached is not None:
            return cached
        try:
            prompt = prompt_template.format(transcript=transcript[:3000])
            response = await self._llm.generate(prompt, "")
            cleaned = response.strip().strip('"\'')
            if not cleaned:
                logger.warning("HyDE %s returned empty, falling back to transcript", layer)
                return transcript[:500]
            logger.info("HyDE %s generated %d chars from %d-char transcript",
                        layer, len(cleaned), len(transcript))
            self._write_cache(layer, transcript, cleaned)
            return cleaned
        except Exception:
            logger.exception("HyDE %s generation failed; using fallback", layer)
            return transcript[:500]

    async def generate_for_icd(self, transcript: str) -> str:
        """Generate hypothetical clinical summary for ICD-10 retrieval.

        Cached on disk (sha256 of normalized transcript). Disable cache with
        ASR_HYDE_CACHE_ENABLED=false.
        """
        return await self._generate("icd", _HYDE_PROMPT_ICD, transcript)

    async def generate_for_sut(self, transcript: str) -> str:
        """Generate hypothetical test order list for SUT retrieval."""
        return await self._generate("sut", _HYDE_PROMPT_SUT, transcript)
