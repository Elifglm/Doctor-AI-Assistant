"""ICD-10 suggestion service: NER → Vector DB → LLM selection pipeline.

Production pipeline (post Phase 3.2):
  1. NER extracts medical terms from report
  2. HyDE generates hypothetical clinical doc (if enabled)        [Phase 1.1]
  3. BM25 sparse + dense vector + text fallback channels          [Phase 2.1]
  4. RRF fusion of channels                                       [Phase 2.1]
  5. Synonym expansion at retrieval time (default ON)             [Phase 2.3]
  6. .9 augmentation post-cap (specificity safety)                [Phase 1.2]
  7. Constitutional prompt drives LLM selection                   [Phase 3.2]

Feature flags (env-controlled):
  ASR_HYDE_ENABLED         — default true; disables Haiku HyDE call if off
  ASR_BM25_ENABLED         — default true; disables BM25 channel if off
  ASR_RRF_ENABLED          — default true; disables RRF fusion (naive merge fallback)
  ASR_ICD_PROMPT_VARIANT   — "constitutional" (default) | "hierarchical" | "original"
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from apps.backend.src.schemas.icd10 import ICD10Suggestion
from apps.backend.src.services.icd10_service import ICD10Service
from apps.backend.src.services.icd10_vector_service import ICD10VectorService
from apps.backend.src.services.llm_base import LLMProvider

logger = logging.getLogger(__name__)


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name, "true" if default else "false").lower()
    return raw in ("true", "1", "yes", "on")

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

ICD10_EXPLICIT_EXTRACTION_PROMPT = """\
Asagidaki tibbi rapor metninde HASTALIK TANISI ve SEMPTOM isimlerini cikar.

KURALLAR:
- "TANI" listesi: kesin_tani, on_tani, oz_gecmisi'nde GECEN hastalik adlari + \
  konsultasyon_sonucundan ANLASILAN tanilari yaz (KAH, DM, HT, KOAH, KBY, anemi, \
  hiperkolesterolemi, kalp yetmezligi vb.).
- "SEMPTOM" listesi: yakinma/oykü/muayene'de GECEN semptom adlari (dispne, \
  nefes darligi, carpinti, halsizlik, bas agrisi, gogus agrisi, karin agrisi, \
  ates, bayilma, kilo kaybi vb.).
- Tetkik adi (BNP, ekokardiyografi vb.) ile karistirma — sadece tani ve semptom.
- Adlari DOGRU TURKCE karakterleriyle yaz (DİSPNE / EKOKARDİYOGRAFİ degil, \
  Türkçe karakter kullan: ı→İ, s→Ş, g→Ğ, vb.).
- Hicbiri yoksa bos liste don.

CIKTI FORMATI (sadece JSON, baska aciklama yok):
{{"tani":["HT","DM"],"semptom":["dispne","carpinti"]}}

RAPOR:
{report_text}

Yanit (sadece JSON):
"""


ICD10_REPORT_SELECTION_PROMPT = """\
Sen bir deneyimli tibbi kodlama uzmanisin. Asagida bir anamnez raporunun ilgili \
alanlari ve ICD-10 aday kodlari verilmistir.

GOREV: Aday kodlardan rapora KLINIK OLARAK uygun olanlari sec. Uc kategoriye gore \
kodla:

IKI ASAMA — KAYNAK ETIKETLE ("source" alanina yaz):

[ASAMA A — "tani"] ACIK TANI KODLARI (confidence 0.85-0.95):
- Doktorun "kesin_tani", "on_tani" veya "oz_gecmisi_soy_gecmisi" alanlarinda \
  ACIKCA yazdigi hastalik kodlari (KAH, DM, HT, KOAH, KBY...).
- "konsultasyon_sonuc" alanindaki tani da bu kategoride.

[ASAMA B — "semptom"] SEMPTOM KODLARI (confidence 0.65-0.80):
- Doktor net tani koymamis ama RAPORDA SEMPTOM ACIKCA GECIYORSA, \
  ICD-10'un R-bolumunden semptom kodunu sec.
- Ornek mapping:
  * dispne / nefes darligi → R06.0
  * carpinti → R00.2
  * halsizlik / yorgunluk → R53
  * bas donmesi → R42
  * bas agrisi → R51
  * gogus agrisi → R07.4
  * karin agrisi → R10
  * ates (38+) → R50.9
  * bayilma / senkop → R55
  * kilo kaybi → R63.4

CIKARIM YAPMA — DOKTOR DEMEDIYSE TAHMIN ETME:
- Tedaviye/konsultasyon istemine bakarak hastaliga atlama (ornek: "ramipril" \
  varsa I10 EKLEME — bu tahmin olur).
- Doktor sadece tetkik istedi, tani koymadiysa, sadece SEMPTOM kodlarini sec.
- Doktor hicbir tani veya semptom yazmadiysa BOS LISTE don.

KRITIK KURALLAR:
1. SADECE asagidaki ADAY ICD-10 KODLARI listesindeki kodlari kullan. Kod uydurma.
2. Bir semptom baska bir hastaligin sonucu olabiliyorsa, hastalik kodunu (Asama A) \
   semptom kodu (Asama B) yerine tercih et.
   - Ornek: "Bas donmesi + anemi bulgulari" → D50 (anemi) sec, R42 (vertigo) ATLA.
3. SPESIFIKLIK — alt-tip secimi:
   - Yetersiz kanit varsa "tanimlanmamis" alt kodu (.9 ile biten) tercih et.
   - KOAH var ama akut enfeksiyon yok → J44.9 sec, J44.0 SECME.
   - Diyabet var ama tip/komplikasyon belirsiz → E11.9 sec.
   - Hipertansiyon var ama kalp tutulumu yok → I10 sec, I11 SECME.
4. Birden fazla hastalik/semptom varsa hepsini listele.
5. Maksimum 6 kod (3 tani + 3 semptom).
6. Sadece JSON formatinda yanit ver.

ANAMNEZ RAPORU:
{report_text}

ADAY ICD-10 KODLARI:
{candidates}

Yanit (sadece JSON, baska bir sey yazma):
[
  {{"icd_kodu":"E11.9","tani":"Tip 2 DM","confidence":0.92,"source":"tani","reasoning":"oz_gecmisi'nde DM yazili"}},
  {{"icd_kodu":"R06.0","tani":"Dispne","confidence":0.78,"source":"semptom","reasoning":"Yakinmada nefes darligi, doktor net tani koymamis"}}
]

Hicbir aday uygun degilse bos liste don: []
"""


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1.2 — Hierarchical 3-stage ICD prompt (T1.1 + T1.2 + T1.3 paketi)
# ─────────────────────────────────────────────────────────────────────────────
# Phase 1.1 (HyDE) hata analizi: agent sıklıkla YANLIŞ PREFIX'e sapıyor:
#   - T11/T12: E11.9 aday yok → E13.9 (yanlış DM tipi) seçildi
#   - T18: J44.0 aday yok → J44 parent seçildi (skoru düşük)
#
# Çözüm: 3-aşamalı reasoning template ile prefix-stability sağla.

ICD10_REPORT_SELECTION_PROMPT_HIERARCHICAL = """\
Sen deneyimli bir tibbi kodlama uzmanisin. Asagida bir anamnez raporu ve \
ICD-10 aday kodlari verilmistir. UC ASAMALI hiyerarsik secim yap:

═══════════════════════════════════════════════════════════════════════════
ASAMA 1 — HASTALIK KATEGORI TESPITI (icini ses cikarmadan dusun, yazma):
═══════════════════════════════════════════════════════════════════════════
Raporda doktor tarafindan ACIKCA belirtilen aktif hastaliklari mental olarak \
listele. Ornek: "T2DM | esansiyel HT | hiperkolesterolemi"

Sadece doktor tarafindan dile getirilen taniler. Tedavi/aile oykusunden cikarim YAPMA.

═══════════════════════════════════════════════════════════════════════════
ASAMA 2 — ICD-10 3-KARAKTER PREFIX ESLESMESI:
═══════════════════════════════════════════════════════════════════════════
Her hastalik icin ICD-10 standart prefix'ini bul:
- T2DM → E11
- T1DM → E10
- KOAH → J44
- Astim → J45
- Esansiyel HT → I10 (komplikasyonsuz) veya I11 (kalp tutulumu)
- Hiperkolesterolemi → E78
- Hipotiroidi → E03
- Demir eksikligi anemisi → D50
- KKY → I50
- KAH → I25

═══════════════════════════════════════════════════════════════════════════
ASAMA 3 — ALT-KOD SECIMI (en kritik adim):
═══════════════════════════════════════════════════════════════════════════
Aday listesinde ARANIS SIRASI:

(a) ONCE — Doktorun belirttigi SPESIFIK alt-tipi ara:
    - "KOAH akut alevlenmesi" → J44.0
    - "Tip 2 DM nefropati" → E11.2
    - "Akut MI" → I21.x

(b) BULAMAZSAN — Ayni prefix'in .9 (tanimlanmamis) alt-tipini sec:
    - E11.9, J44.9, I50.9, E03.9 vb.

(c) ONA DA YOKSA — Ayni prefix altindaki EN UYGUN alt-tipi sec
    (ornek: J44.0 ve J44.9 yoksa J44.1 olabilir)

(d) PREFIX HIC YOKSA — O hastaligi ATLA. ASLA yanlis prefix'e sapma:
    ⚠️ E11 (T2DM) yerine E13 (diger DM) SECME — bunlar FARKLI hastaliklar
    ⚠️ J44 (KOAH) yerine J45 (astim) SECME
    ⚠️ E03 (hipotiroidi) yerine E05 (tirotoksikoz) SECME
    Yanlis prefix secmek HATALI KODLAMA, eksik kalmak DOGRU davranis.

═══════════════════════════════════════════════════════════════════════════
SEMPTOM KODLARI (R-bolumu):
═══════════════════════════════════════════════════════════════════════════
Doktor net tani koymadiginda:
- dispne → R06.0 / nefes darligi → R06.0
- carpinti → R00.2 / halsizlik → R53 / bas donmesi → R42
- bas agrisi → R51 / gogus agrisi → R07.4 / karin agrisi → R10
- ates 38+ → R50.9 / senkop → R55 / kilo kaybi → R63.4

ANEMI KURALI: Anemi tanisi varsa, anemi tarafindan aciklanan semptomlari \
EKLEME (R42 vertigo, R53 yorgunluk, R23.1 solukluk anemiyle aciklanir).

═══════════════════════════════════════════════════════════════════════════
GENEL KURALLAR:
═══════════════════════════════════════════════════════════════════════════
1. SADECE asagidaki ADAY ICD-10 KODLARI listesinden sec. Kod uydurma.
2. Tedavi/konsultasyondan tani cikarimi YAPMA.
3. Maksimum 6 kod (3 tani + 3 semptom).
4. Sadece JSON formatinda yanit ver, baska aciklama yazma.

═══════════════════════════════════════════════════════════════════════════
ANAMNEZ RAPORU:
{report_text}

ADAY ICD-10 KODLARI:
{candidates}

YANIT (sadece JSON array, baska bir sey yazma):
[
  {{"icd_kodu":"E11.9","tani":"Tip 2 DM","confidence":0.92,"source":"tani","reasoning":"Asama1: T2DM tanili. Asama2: E11 prefix. Asama3: spesifik komplikasyon yok, .9 alt-tipi"}},
  {{"icd_kodu":"R06.0","tani":"Dispne","confidence":0.78,"source":"semptom","reasoning":"Net tani yok, semptom kodu"}}
]

Hicbir aday uygun degilse bos liste don: []
"""


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3.2 — Constitutional ICD prompt (anayasal kurallar)
# ─────────────────────────────────────────────────────────────────────────────
# Phase 2.3 hata analizi:
#   - T01, T20: Z83.3 (aile öyküsü) FP — agent ekliyor, gold istemiyor
#   - T01: E66.9 (obezite, BMI 32) FP — gold istemiyor
#   - T08: R05+R50.9 FP — akut bronşit (J20.9) bunları açıklıyor
#   - T17: D50.0 seçildi, gold D50.9 — overshoot
#   - T17/T19: R53 (yorgunluk) eksik — gold istiyor (anemi/hipotiroidi olsa da)
#
# Hipotez: "Code-conservation" + "default .9" + "explicit yorgunluk" kuralları
# false positive'leri azaltacak ve recall'u korurken precision artacak.

ICD10_REPORT_SELECTION_PROMPT_CONSTITUTIONAL = """\
Sen deneyimli bir tibbi kodlama uzmanisin. UC ASAMALI hiyerarsik secim yap.

═══════════════════════════════════════════════════════════════════════════
ANAYASAL KURALLAR (her secimde uy):
═══════════════════════════════════════════════════════════════════════════

KURAL #1 — KOD-KISITLAMA (CODE CONSERVATION):
Sadece doktorun TEDAVI ETMEYE KARAR VERDIGI veya AKTIF YONETIMINI YAPTIGI
hastaliklari kodla. Su 3 durum HIC kodlanmaz:

  ❌ AILE OYKUSU TEK BASINA (Z83.x): Babasinda DM varsa Z83.3 ASLA EKLEME.
     Sadece doktorun tedavisini etkileyen klinik onemde ise eklenir.
  ❌ FIZIK MUAYENE BULGUSU (E66 obezite vs.): BMI 32 not edildi diye
     E66.9 ASLA EKLEME. Doktor obezite icin tedavi/onerme yaptiysa olur.
  ❌ ZIMNI TANI: Doktor "olabilir, dusunulebilir, soz konusu" derse o kod
     ASLA eklenmez. Sadece "tani konuldu / tedavi baslandi" netse kodla.

KURAL #2 — DEFAULT .9 ALT-TIPI (UNSPECIFIED PREFERENCE):
Doktor alt-tipi ACIKCA SOYLEMEDIGI surece, .9 (tanimlanmamis) tercih et.

  ✅ "Anemim var" → D50.9 (D50.0 ASLA, "kronik kan kaybi" demediyse)
  ✅ "Astim var" → J45.9 (J45.0 allerjik ASLA, doktor "allerjik astim" demediyse)
  ✅ "KOAH var" → J44.9 (J44.0 ASLA, doktor "alevlenme" demediyse)
  ✅ "Hipotiroidim" → E03.9 (E03.0/E03.1 konjenital ASLA yetiskinde)

  Spesifik subtype SADECE doktor o spesifik kelimeleri kullandiginda:
  - "Saf hiperkolesterolemi" → E78.0 ✓ ("hiperkolesterolemi" tek basina yetmez)
  - "Akut KOAH alevlenmesi" → J44.0 ✓
  - "Konjestif kalp yetmezligi" → I50.0 ✓ ("kalp yetmezligi" tek basina I50.9)

KURAL #3 — SEMPTOM-BASTIRMA (DIAGNOSIS-COVERS-SYMPTOMS):
Bir hastalik tanisi koyulduysa, o hastaligin TIPIK semptomlarini AYRICA
KODLAMA — gereksiz tekrar yaratir.

  KOAH/Astim/Bronsit (J44/J45/J20) → R05 oksuruk EKLEME, R06.x dispne EKLEME
  Akut Bronsit (J20.x) → R50.9 ates EKLEME (subfebril dahil)
  Anemi (D50.x) → R23.1 solukluk, R00.2 carpinti, R42 vertigo EKLEME
  Hipotiroidi (E03.x) → R00.1 bradikardi, K59.0 kabizlik EKLEME (E03 acikliyor)
  Hepatit (B18.x) → R10/R11/R17 EKLEME (asemptomatik tasiyici sik)

  ⚠️ ISTISNA — R53 (yorgunluk/halsizlik): Doktor "halsizlik/yorgunluk"
     diye sikayet kayitladiysa, R53 HER ZAMAN EKLE — anemi veya hipotiroidi
     gibi acikliyici tanisi olsa bile. (R53 her durumda kayda deger.)

KURAL #4 — NEGATE EDILMIS SEMPTOM HIC KODLANMAZ:
Rapor "...yok / tariflemiyor / negatif" diyorsa o semptom kodu KESINLIKLE
EKLENMEZ. "Polidipsi yok" → R63.1 KOY MA. "Carpinti yok" → R00.2 KOY MA.

═══════════════════════════════════════════════════════════════════════════
UC ASAMALI SECIM:
═══════════════════════════════════════════════════════════════════════════

ASAMA 1 — HASTALIK TESPITI (mental):
Doktorun TEDAVI YONETTIGI veya KESIN TANI KOYDUGU hastaliklari listele.
Aile oykusu/BMI/zimni tani EKLEMA.

ASAMA 2 — ICD-10 PREFIX:
T2DM→E11, T1DM→E10, KOAH→J44, Astim→J45, Esansiyel HT→I10 (komplikasyonsuz)
veya I11 (kalp tutulumu), Hiperkolesterolemi→E78, Hipotiroidi→E03,
Demir eksikligi anemisi→D50, KKY→I50, KAH→I25, Atrial Fib→I48

ASAMA 3 — ALT-KOD (KURAL #2 dikkat):
(a) Doktor SPESIFIK subtype kelimesini kullandiysa → o subtype
(b) Yoksa → .9 (tanimlanmamis) — DEFAULT
(c) .9 yoksa → ayni prefix altinda en yakin
(d) Hic yoksa → ATLA (yanlis prefix'e sapma)

═══════════════════════════════════════════════════════════════════════════
GENEL KURALLAR:
═══════════════════════════════════════════════════════════════════════════
1. SADECE asagidaki ADAY ICD-10 KODLARI listesinden sec. Kod uydurma.
2. Tedavi/aile oykusunden tani cikarimi YAPMA.
3. Maksimum 4 kod (KOD-KISITLAMA kurali geregi az kod ye)
4. Sadece JSON formatinda yanit ver, baska aciklama yazma.

═══════════════════════════════════════════════════════════════════════════
ANAMNEZ RAPORU:
{report_text}

ADAY ICD-10 KODLARI:
{candidates}

YANIT (sadece JSON array, anayasal kurallari uygula):
[
  {{"icd_kodu":"E11.9","tani":"Tip 2 DM","confidence":0.92,"source":"tani","reasoning":"Asama1: T2DM tanili. Asama2: E11. Asama3(b): komplikasyon yok, .9 default"}},
  {{"icd_kodu":"R53","tani":"Halsizlik","confidence":0.78,"source":"semptom","reasoning":"R53 ozel kuralla EKLENDI (E03 olsa da)"}}
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
        validation_mode: str = "strict",
        hyde_service: Any | None = None,
        bm25_service: Any | None = None,
    ) -> None:
        self._llm = llm
        self._icd10 = icd10_service
        self._vectors = vector_service
        self._ner = ner_service
        # Phase 1.1 / 2.1 cumulative — optional retrieval-augmentation services.
        # If not injected the pipeline silently falls back to vector + text only.
        self._hyde = hyde_service
        self._bm25 = bm25_service
        # Hallucination guard mode (ablation switch for thesis):
        #   "strict"     — drop any LLM-output code not in candidate pool
        #   "db_rescue"  — also accept LLM codes that exist in ICD-10 DB
        #                  (lets LLM medical knowledge rescue vector recall misses
        #                   like "diyabet" → E11.9, while still rejecting invented
        #                   codes via DB existence check).
        # Switched at runtime via ASR_ICD__VALIDATION_MODE env var.
        self._validation_mode = validation_mode if validation_mode in {"strict", "db_rescue"} else "strict"
        # Phase 3.2 — prompt variant (constitutional default, accepted phase)
        self._prompt_variant = os.getenv("ASR_ICD_PROMPT_VARIANT", "constitutional").lower()
        if self._prompt_variant not in {"constitutional", "hierarchical", "original"}:
            self._prompt_variant = "constitutional"
        logger.info(
            "ICD10SuggestionService validation_mode=%s prompt_variant=%s "
            "hyde=%s bm25=%s",
            self._validation_mode, self._prompt_variant,
            self._hyde is not None and _env_flag("ASR_HYDE_ENABLED"),
            self._bm25 is not None and _env_flag("ASR_BM25_ENABLED"),
        )

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

        # Step 2 (initial): Find candidate ICD-10 codes via vector DB + text
        # search using NER terms only. Used both as final result when retrieval
        # is already strong, and as input to the conditional HyDE skip below.
        vector_candidates = await self._find_vector_candidates(ner_terms)
        text_candidates = await self._text_search_fallback(ner_terms)

        # Phase 1.1 + Cost optimization: HyDE — generate hypothetical clinical
        # doc only when initial retrieval is weak. If top-1 vector score >=
        # ASR_HYDE_SKIP_THRESHOLD (default 0.85), HyDE is skipped (saves 1 LLM
        # call without hurting metrics — strong retrieval doesn't need rescue).
        hyde_doc: str | None = None
        skip_threshold = float(os.environ.get("ASR_HYDE_SKIP_THRESHOLD", "0.85"))
        top_score = max((c.get("score", 0.0) for c in vector_candidates), default=0.0)
        if (
            self._hyde is not None
            and _env_flag("ASR_HYDE_ENABLED")
            and top_score < skip_threshold
        ):
            try:
                hyde_doc = await self._hyde.generate_for_icd(report_text)
                if hyde_doc and len(hyde_doc) > 20:
                    ner_terms.insert(0, hyde_doc)
                    logger.info(
                        "HyDE prepended (%d chars, top_score=%.3f < %.2f)",
                        len(hyde_doc), top_score, skip_threshold,
                    )
                    # Re-run vector + text search WITH hyde doc prepended
                    vector_candidates = await self._find_vector_candidates(ner_terms)
                    text_candidates = await self._text_search_fallback(ner_terms)
            except Exception:
                logger.exception("HyDE generation failed; continuing without")
        elif self._hyde is not None and _env_flag("ASR_HYDE_ENABLED"):
            logger.info(
                "HyDE skipped (top_score=%.3f >= %.2f, retrieval already strong)",
                top_score, skip_threshold,
            )

        # Phase 2.1: BM25 sparse retrieval channel (lexical match for surface
        # forms BGE-M3 abstracts away — e.g. specific ICD codes, medical labels).
        bm25_candidates: list[dict[str, Any]] = []
        if self._bm25 is not None and _env_flag("ASR_BM25_ENABLED"):
            bm25_queries = [hyde_doc] if hyde_doc else []
            bm25_queries += ner_terms[:8] if not hyde_doc else ner_terms[1:8]
            seen_ids: set[str] = set()
            for q in bm25_queries:
                if not q or not q.strip():
                    continue
                try:
                    results = self._bm25.search(q, top_k=15)
                except Exception:
                    logger.exception("BM25 search failed for query")
                    continue
                for r in results:
                    rid = r.get("icd_kodu")
                    if rid and rid not in seen_ids:
                        seen_ids.add(rid)
                        bm25_candidates.append({**r, "source": "bm25"})
            logger.info("BM25 channel returned %d unique candidates", len(bm25_candidates))

        # Step 2a-bis: LLM-extracted explicit diagnoses + symptoms (proper Turkish form).
        # Bypasses keyword/embedding limitations for terms doctor explicitly named.
        # Skipped under db_rescue mode — DB-rescue at parse time covers the same
        # use case (LLM medical knowledge → DB validation) with one fewer LLM call.
        explicit_candidates: list[dict[str, Any]] = []
        if self._validation_mode == "strict":
            explicit_candidates = await self._llm_extract_diagnoses_and_symptoms(report_text)

        # Merge channels — RRF fusion (default ON post Phase 2.1) else naive dedup
        from apps.backend.src.services.rrf_fusion import rrf_fuse
        rrf_enabled = _env_flag("ASR_RRF_ENABLED", default=True)
        if rrf_enabled:
            channels = [vector_candidates, text_candidates, bm25_candidates, explicit_candidates]
            candidates = rrf_fuse(channels, id_field="icd_kodu", k=60)
            seen = {c["icd_kodu"] for c in candidates}
            logger.info(
                "RRF fused: vector=%d + text=%d + bm25=%d + explicit=%d → %d unique",
                len(vector_candidates), len(text_candidates),
                len(bm25_candidates), len(explicit_candidates), len(candidates),
            )
        else:
            candidates = list(vector_candidates)
            seen = {c["icd_kodu"] for c in candidates}
            for extra in (text_candidates, bm25_candidates, explicit_candidates):
                for r in extra:
                    if r.get("icd_kodu") and r["icd_kodu"] not in seen:
                        seen.add(r["icd_kodu"])
                        candidates.append(r)

        # Step 2b: Hierarchical fallback — for every candidate that's a
        # specific subcode (e.g. J44.0), make sure the "unspecified" sibling
        # (J44.9) and the bare parent (J44) are also offered to the LLM.
        # Without this the LLM is forced to pick a specific subtype even when
        # the report lacks evidence to distinguish among them, leading to
        # over-coding (e.g. J44.0 chosen when only J44.9 is supported).
        await self._augment_with_unspecified(candidates, seen)

        logger.info(
            "Report combined %d candidates (vector + text + llm-explicit + unspec)",
            len(candidates),
        )

        if not candidates:
            return []

        # Step 3: LLM selects from candidates using report context
        suggestions = await self._llm_select_from_report(report_text, candidates)
        logger.info("Report LLM selected %d ICD-10 codes", len(suggestions))

        return suggestions

    async def _llm_select_from_report(
        self, report_text: str, candidates: list[dict[str, Any]]
    ) -> list[ICD10Suggestion]:
        """Ask LLM to select ICD-10 codes based on structured report.

        Phase 3.2: Constitutional prompt is the default. Variant selectable
        via ASR_ICD_PROMPT_VARIANT env (constitutional|hierarchical|original).
        """
        # Use rrf_score if present (RRF-fused), else fall back to score
        candidates_text = "\n".join(
            f"({c['icd_kodu']}) - {c['tani']} [skor: {c.get('rrf_score', c.get('score', 0)):.4f}]"
            for c in candidates
        )

        if self._prompt_variant == "constitutional":
            template = ICD10_REPORT_SELECTION_PROMPT_CONSTITUTIONAL
        elif self._prompt_variant == "hierarchical":
            template = ICD10_REPORT_SELECTION_PROMPT_HIERARCHICAL
        else:
            template = ICD10_REPORT_SELECTION_PROMPT
        prompt = template.format(
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

        return await self._parse_llm_selection(raw, candidates)

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
        # Query expansion: synonyms (halk_dili → tıbbi terim) AND
        # per-word significant token isolation. The token step is a
        # noise-resistance fix — long phrases like "MENENJİT İHTİMALİ GÖZE
        # ALINIYOR" lose semantic signal in dense embedding because filler
        # words dominate; isolating "menenjit" lets the vector index
        # surface the actual ICD code.
        from apps.backend.src.services.nlp_normalizer import (
            get_expander, expand_with_tokens,
        )
        expanded = expand_with_tokens(get_expander(), terms)
        if len(expanded) > len(terms):
            logger.info("ICD expansion (synonyms+tokens): %d → %d terms",
                        len(terms), len(expanded))
        terms = expanded

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

    async def _llm_extract_diagnoses_and_symptoms(
        self, report_text: str
    ) -> list[dict[str, Any]]:
        """LLM extracts explicit diagnoses + symptoms, then ICD-search each.

        Bypasses vector embedding limitations and Turkish-character normalization
        bugs by relying on the LLM to produce proper Turkish forms.
        """
        prompt = ICD10_EXPLICIT_EXTRACTION_PROMPT.format(report_text=report_text)
        try:
            raw = await self._llm.generate(prompt, "")
        except Exception:
            logger.exception("LLM ICD10 extraction failed")
            return []

        cleaned = raw.strip()
        if "```" in cleaned:
            cleaned = re.sub(r"```(?:json)?\s*", "", cleaned).strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return []
        try:
            parsed = json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            return []

        tani_names = parsed.get("tani", []) if isinstance(parsed, dict) else []
        semptom_names = parsed.get("semptom", []) if isinstance(parsed, dict) else []
        logger.debug(
            "LLM-extracted ICD candidates: tani=%s semptom=%s",
            tani_names, semptom_names,
        )

        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for name in (tani_names + semptom_names)[:20]:
            if not isinstance(name, str) or not name.strip():
                continue
            results = await self._icd10.search(name.strip(), limit=3)
            for r in results:
                if r.icd_kodu not in seen:
                    seen.add(r.icd_kodu)
                    candidates.append({
                        "icd_kodu": r.icd_kodu,
                        "tani": r.tani,
                        "score": 0.95,
                        "source": f"llm_explicit:{name}",
                    })
        return candidates

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

        return await self._parse_llm_selection(raw, candidates)

    async def _parse_llm_selection(
        self,
        raw: str,
        candidates: list[dict[str, Any]] | None = None,
    ) -> list[ICD10Suggestion]:
        """Parse LLM's JSON selection response.

        Hallucination guard depends on ``self._validation_mode`` (set at init,
        switched via ASR_ICD__VALIDATION_MODE env var) — for thesis ablation:

          - "strict"     drop any code not in candidate pool (high precision,
                         lower recall: vector DB misses are unrecoverable)
          - "db_rescue"  also accept LLM codes that exist in ICD-10 DB
                         (LLM medical knowledge rescues vector recall failures
                         like "diyabet" → E11.9; invented codes still rejected
                         by DB existence check)
        """
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

        cand_by_code: dict[str, dict[str, Any]] = {}
        if candidates is not None:
            cand_by_code = {str(c.get("icd_kodu", "")): c for c in candidates}

        suggestions: list[ICD10Suggestion] = []
        dropped: list[str] = []
        rescued: list[str] = []
        for item in parsed[:8]:
            kodu = str(item.get("icd_kodu", "")).strip()
            if not kodu:
                continue
            tani = item.get("tani", "")

            if kodu in cand_by_code:
                tani = cand_by_code[kodu].get("tani", tani)
            elif self._validation_mode == "db_rescue":
                # Aday listesinde yok — DB'de var mı diye sor
                db_row = await self._icd10.get_by_code(kodu)
                if db_row is None:
                    dropped.append(kodu)
                    continue
                tani = db_row.tani or tani
                rescued.append(kodu)
            else:  # strict
                dropped.append(kodu)
                continue

            source = item.get("source", "tani")
            if source not in {"tani", "semptom"}:
                source = "tani"
            suggestions.append(
                ICD10Suggestion(
                    icd_kodu=kodu,
                    tani=tani,
                    confidence=float(item.get("confidence", 0.5)),
                    reasoning=item.get("reasoning", ""),
                    source=source,
                )
            )
        if dropped:
            logger.warning(
                "Dropped %d hallucinated ICD code(s) [mode=%s]: %s",
                len(dropped), self._validation_mode, dropped,
            )
        if rescued:
            logger.info(
                "DB-rescued %d ICD code(s) (LLM proposed, DB validated): %s",
                len(rescued), rescued,
            )
        return suggestions
