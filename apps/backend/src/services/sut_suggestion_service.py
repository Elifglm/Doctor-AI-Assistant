"""SUT tetkik suggestion service: NER → Vector DB → LLM selection pipeline."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from apps.backend.src.schemas.sut_tetkik import IntentLabel, SUTSuggestion
from apps.backend.src.services.sut_service import SUTService
from apps.backend.src.services.sut_vector_service import SUTVectorService
from apps.backend.src.services.llm_base import LLMProvider

logger = logging.getLogger(__name__)


def _safe_for_format(text: str) -> str:
    """Escape ``{`` and ``}`` so user-controlled text cannot break str.format().

    Defends against prompt-injection-by-format-string. Doctor-patient
    transcript or report sections are user/ASR-controlled inputs that flow
    into prompt templates via ``str.format()`` — a stray ``{`` would raise
    ``KeyError`` and a crafted ``{key}`` could collide with a placeholder.
    """
    return text.replace("{", "{{").replace("}", "}}")


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

GOREV: ADAY TETKIKLER listesinden RAPORDA ACIKCA ISTENEN tetkikleri sec.

KRITIK KURAL — KOD KAYNAGI:
SADECE asagidaki "ADAY TETKIKLER" listesinde gecen kodlari ve adlari kullan. \
Aday listesinde olmayan bir kodu/adi UYDURMA, ASLA. Bilmediğin kodu yazma.

ZORUNLU SECIM KURALI:
Eger bir tetkik/tahlil adi raporun "konsultasyon_muayene", "tedavi" veya "oneri" \
alanlarinda ACIKCA gecmisse VE aday listesinde semantik karsiligi VARSA → o tetkiki \
MUTLAKA SEC, confidence >= 0.90. ATLAMA, eleme, "yeterli match degil" deme.

SEMANTIK ESLESME (ADAY LISTESI ICINDEN):
- "TAM KAN SAYIMI" / "kan sayimi" / "hemogram" → adaylarda "Tam Kan Sayımı" varsa sec.
- "TROPONIN" → adaylarda "Troponin I" ve/veya "Troponin T" varsa HEPSINI sec.
- "BNP" → adaylarda "B natriüretik peptid" ve/veya "NT-ProBNP" varsa HEPSINI sec.
- "EKOKARDIYOGRAFI" / "EKO" → adaylarda "Ekokardiyografi" varsa sec.
- "EKG" → adaylarda basit "EKG" varsa sec. "Holter" SADECE rapor "holter" \
  derse seçilir, "EKG" denildi diye otomatik holter SECILMEZ.
- "BIYOKIMYA" / "biyokimya paneli" → adaylarda glukoz, ure, kreatinin, ALT, AST, \
  sodyum, potasyum gibi panel komponentleri varsa HEPSINI sec. \
  Yoksa biyokimya icin uydurma, atla.
- "KARACIGER ENZIMLERI" → adaylarda ALT ve AST varsa HEPSINI sec.
- "BOBREK FONKSIYONU" → adaylarda kreatinin, BUN/ure varsa hepsini sec.
- "LIPID PANELI" → adaylarda LDL, HDL, total kolesterol, trigliserid varsa hepsini sec.
- "TIROID TESTLERI" → adaylarda TSH, sT3, sT4 varsa hepsini sec.
- "KARIN USG" → adaylarda Tum Batin USG varsa sec.
- "TIROID USG" / "boyun USG" → adaylarda Boyun USG varsa sec.

NEGATIF KURALLAR (bu sinirlari koru):
- Aday listesinde olup raporda HIC BAHSEDILMEYEN tetkikleri SECME.
- Aday listesinde OLMAYAN bir kod/adi ASLA UYDURMA — kod bilmiyorsan o tetkiki ATLA.
- "kan tahlili" istenince yanlis "Gaitada gizli kan" SECILMEZ.
- "EKG" denilince "Holter" SECILMEZ.
- ICD-10 tanisi verilmisse o taniyla CELISEN tetkikleri SECME.

CIKTI:
- Maksimum 10 tetkik.
- Her tetkik icin confidence (0.0-1.0). Raporda ismen gecen tetkikler >= 0.90.
- SADECE JSON. Markdown fence yok, aciklama yok.

ANAMNEZ RAPORU:
{report_text}

ADAY TETKIKLER:
{candidates}

ORNEKLER:

[ORNEK 1 — coklu tetkik, ADAY LISTESINDE olanlari sec]
konsultasyon_muayene: "TAM KAN SAYIMI ---- TROPONIN ---- BNP ---- EKOKARDIYOGRAFI"
Adaylarda Tam Kan Sayimi, Troponin I, Troponin T, BNP, Ekokardiyografi varsa:
[
  {{"kodu":"<adaydan>","adi":"Tam Kan Sayımı","confidence":0.95,"reasoning":"Raporda 'TAM KAN SAYIMI' ismen gecti, adayda var"}},
  {{"kodu":"<adaydan>","adi":"Troponin I","confidence":0.95,"reasoning":"Raporda 'TROPONIN' ismen gecti"}},
  {{"kodu":"<adaydan>","adi":"Troponin T","confidence":0.92,"reasoning":"Raporda 'TROPONIN' ismen gecti, T varyanti da adayda"}},
  {{"kodu":"<adaydan>","adi":"BNP","confidence":0.95,"reasoning":"Raporda 'BNP' ismen gecti"}},
  {{"kodu":"<adaydan>","adi":"Ekokardiyografi","confidence":0.95,"reasoning":"Raporda 'EKOKARDIYOGRAFI' ismen gecti"}}
]
("<adaydan>" yerine ADAY TETKIKLER listesindeki gerçek kodu yaz.)

[ORNEK 2 — semantic mapping, halk dili]
konsultasyon_muayene: "kan tahlili ve karaciger enzimleri istenmis"
Adaylarda Hemogram, ALT, AST varsa: bu uclunu sec. Gaitada gizli kan ADAYDA OLSA BILE SECILMEZ \
(rapor "gaita" demedi).

[ORNEK 3 — biyokimya panel, ama aday listesi sadece 2 komponenti iceriyor]
konsultasyon_muayene: "BIYOKIMYA istendi"
Adaylar sadece "Glukoz (Serum/Plazma)" ve "Kreatinin (Serum/Plazma)" iceriyor. \
SECIM: bu iki kodu sec. Aday listesinde olmayan ALT/AST/Ure icin SECME, UYDURMA.

[ORNEK 4 — bos rapor]
"rapor tetkik plani icermiyor" → [] (bos liste, asla uydurma)

Yanit (sadece JSON, kod fence yok):
"""


EXPLICIT_TEST_EXTRACTION_PROMPT = """\
Asagidaki tibbi rapor metninde DOKTOR TARAFINDAN ACIKCA ISTENMIS \
tetkik/tahlil/goruntuleme isimlerini cikar. Sadece tetkik adlarini listele, kod yazma.

KURALLAR:
- Sadece raporda ACIKCA gecen tetkik isimlerini listele.
- Tetkik adlarini DOGRU TURKCE karakterleriyle yaz: ı→İ donusumu yapilmissa duzgun \
  Turkce yaziya geri cevir. Ornek: "EKOKARDIYOGRAFI" YANLIS → "EKOKARDİYOGRAFİ" DOGRU. \
  "TIROID USG" YANLIS → "TİROİD USG" DOGRU. \
  "BIYOKIMYA" YANLIS → "BİYOKİMYA" DOGRU.
- Eger panel adi varsa (BIYOKIMYA, LIPID PANELI, KARACIGER ENZIMLERI, BOBREK \
  FONKSIYONU, TIROID TESTLERI), panel adini birak ama ek olarak bilinen alt-testlerini \
  de listeye ekle:
  * BIYOKIMYA → glukoz, üre, kreatinin, sodyum, potasyum, ALT, AST
  * KARACIGER ENZIMLERI → ALT, AST
  * BOBREK FONKSIYONU → kreatinin, üre
  * LIPID PANELI → LDL kolesterol, HDL kolesterol, total kolesterol, trigliserid
  * TIROID TESTLERI → TSH, sT3, sT4
- Hicbir tetkik istenmemisse bos liste don.
- Sadece JSON array, baska aciklama yok.

RAPOR:
{report_text}

Yanit (sadece JSON array):
"""


# ============================================================================
# V2 PROMPT — Per-mention CoT label-then-decide for intent disambiguation.
# Selected via ASR_SUT__INTENT_PROMPT_VERSION env var (default v2).
# Set to "v1" to fall back to SUT_SELECTION_PROMPT (legacy).
# ============================================================================

SUT_SELECTION_PROMPT_V2 = """\
Sen Türkçe tıbbi tetkik/tahlil uzmanısın. Aşağıda doktor-hasta görüşme \
transkripti ve aday SUT tetkik kodları var.

GÖREV: Transkriptteki her tetkik mention'ını analiz et, sadece DOKTORUN \
ŞİMDİ İSTEDİĞİ tetkikleri seç. Geçmiş mention'ları, hasta sorularını, \
hipotetik/reddedilen tetkikleri DAHIL ETME.

ADIM ADIM AKIL YÜRÜTME (her aday için):
1. **kaynak_cumle**: tetkikin geçtiği TAM cümleyi transkriptten kelimesi \
   kelimesine çıkar. Konuşmacı prefix'ini ("Doktor:" / "Hasta:") koru.
2. **konuşmacı**: cümle "Doktor:" ile başlıyorsa DOCTOR, "Hasta:" ile \
   başlıyorsa PATIENT. Belirsizse OTHER.
3. **zaman_kipi**: Türkçe morfoloji ipuçları:
   - PAST_NARRATIVE: -mIştI, -mIş, -dI ekleri ("baktırmıştım", \
     "yaptırdım", "geldi", "bakmıştık")
   - OPTATIVE: -AlIm ("isteyelim", "bakalım"), imperatif ("iste", "bak")
   - FUTURE: -AcAk ("isteyeceğim", "yapacağım", "yazacağım")
   - HYPOTHETICAL: -sA + ana cümle ("şeker yüksekse insülin bakarız")
   - INTERROGATIVE: soru ("- mi?", "- mı?", "lazım mı?")
   - DECLARATIVE: düz haber cümlesi
4. **intent_etiketi** (KARAR):
   - **REQUEST**: konuşmacı=DOCTOR + zaman_kipi (OPTATIVE | FUTURE | \
     imperatif) + olumlu cümle. SADECE bu seçilir.
   - **PAST_DONE**: zaman_kipi=PAST_NARRATIVE (kim söylerse söylesin: \
     doktor "iki yıl önce şeker baktınız" dese de geçmiş!)
   - **PATIENT_QUESTION**: konuşmacı=PATIENT + (INTERROGATIVE veya kendi \
     anlatısı)
   - **RESULT_DISCUSS**: tetkik sonucu konuşuluyor ("CRP 5 gelmiş", \
     "şeker normal"), istek değil
   - **OTHER**: hipotetik, reddedilen ("önerir misiniz? - hayır gerek yok"), \
     diğer
5. **include**: intent_etiketi == REQUEST AND aday listesinde ilgili kod var

NEGATİF ÖRNEKLER (HİÇ DAHIL ETME):
- "Hasta: öz geçmişte hemogram baktırdım" → PATIENT/PAST_NARRATIVE/PAST_DONE → EXCLUDE
- "Doktor: iki yıl önce şeker baktınız" → DOCTOR/PAST_NARRATIVE/PAST_DONE → EXCLUDE \
  (DİKKAT: doktor söylese bile PAST!)
- "Doktor: şekerin yüksekse insülin bakarız" → DOCTOR/HYPOTHETICAL/OTHER → EXCLUDE
- "Hasta: D vitamini bakar mıyız?" → PATIENT/INTERROGATIVE/PATIENT_QUESTION → EXCLUDE
- "Doktor: CRP 12 gelmiş" → DOCTOR/DECLARATIVE/RESULT_DISCUSS → EXCLUDE \
  (sonuç paylaşımı, istek değil)

POZİTİF ÖRNEKLER (SEÇ):
- "Doktor: tam kan isteyelim" → DOCTOR/OPTATIVE/REQUEST → INCLUDE
- "Doktor: troponin ve EKG isteyeceğim" → DOCTOR/FUTURE/REQUEST → INCLUDE \
  (iki ayrı mention)
- "Doktor: bir de B12 bakalım" → DOCTOR/OPTATIVE/REQUEST → INCLUDE

KOD KAYNAĞI KURALI: SADECE aday listesindeki kodları kullan. Aday listesinde \
OLMAYAN bir kodu ASLA UYDURMA. Bilmediğin kodu yazma.

GÜVEN SKORU: kaynak cümle açık ve niyet net ise ≥0.90. Belirsizse 0.60-0.80.

TRANSKRIPT:
{transcript}
{icd_context}
ADAY TETKIKLER:
{candidates}

ÇIKTI (sadece JSON array, markdown fence yok, açıklama yok):
[
  {{
    "kodu": "<adaydan>",
    "adi": "<adaydan>",
    "confidence": 0.95,
    "kaynak_cumle": "<transkriptten tam cümle>",
    "intent_etiketi": "REQUEST",
    "reasoning": "DOCTOR/OPTATIVE — tetkik açıkça istendi"
  }}
]

Hiçbir aday REQUEST değilse: []
"""


# ============================================================================
# V3 PROMPT — V2 + üç bug-fix:
#   1) Liste-mirası: ana fiil FUTURE/OPTATIVE/IMPERATIVE ise virgüllü/iki noktalı
#      liste öğeleri o tense'i miras alır
#   2) Pasif imperative tense (-sIn, -mAlI) ayrı kategori; REQUEST'e dahil
#   3) 1. çoğul "isteyeceğiz/yapacağız/bakacağız" net pozitif örnek
#   4) HYPOTHETICAL ("gerekirse...") güçlendirilmiş negatif örnek
# Selected via ASR_SUT__INTENT_PROMPT_VERSION=v3 (default).
# ============================================================================

SUT_SELECTION_PROMPT_V3 = """\
Sen Türkçe tıbbi tetkik/tahlil uzmanısın. Aşağıda doktor-hasta görüşme \
transkripti ve aday SUT tetkik kodları var.

GÖREV: Transkriptteki her tetkik mention'ını analiz et, sadece DOKTORUN \
ŞİMDİ İSTEDİĞİ tetkikleri seç. Geçmiş mention'ları, hasta sorularını, \
hipotetik/şartlı/reddedilen tetkikleri DAHIL ETME.

ADIM ADIM AKIL YÜRÜTME (her aday için):

1. **kaynak_cumle**: tetkikin geçtiği TAM cümleyi transkriptten kelimesi \
   kelimesine çıkar. Konuşmacı prefix'ini ("Doktor:" / "Hasta:") koru.

2. **konuşmacı**: cümle "Doktor:" ile başlıyorsa DOCTOR, "Hasta:" ile \
   başlıyorsa PATIENT. Belirsizse OTHER.

3. **liste_kontekst** (KRİTİK YENİ KURAL): Cümlede iki nokta (":") veya \
   "şunlar/şunları/aşağıdakileri" gibi liste başlatıcı varsa VE liste içinde \
   virgülle ayrılmış birden fazla tetkik adı varsa → liste başındaki ANA \
   FİİLİ tespit et ve onun tense'ini liste öğelerine MİRAS olarak uygula.
   Örnek:
     "Tahliller isteyeceğiz: TSH, T3, T4, anti-TPO, hemogram"
     → ana fiil: "isteyeceğiz" (FUTURE)
     → liste öğeleri (TSH, T3, T4, anti-TPO, hemogram) HEPSİ FUTURE miras alır
     → her biri için intent: REQUEST
   Liste başında ana fiil yoksa veya tetkik tek başına geçiyorsa, kelime \
   düzeyinde tense kontrolü yap (4. adım).

4. **zaman_kipi**: Türkçe morfoloji ipuçları:
   - PAST_NARRATIVE: -mIştI, -mIş, -dI ekleri ("baktırmıştım", \
     "yaptırdım", "geldi", "bakmıştık")
   - OPTATIVE: -AlIm 1.çoğul ("isteyelim", "bakalım", "yapalım")
   - FUTURE: -AcAk ("isteyeceğim" 1.tekil, "isteyeceğiz" 1.çoğul, \
     "yapacağız", "bakacağız", "yazacağız")
   - **IMPERATIVE_PASSIVE: -sIn 3.tekil pasif emir** ("bakılsın", \
     "yapılsın", "istensin", "ölçülsün") — REQUEST sayılır
   - IMPERATIVE_ACTIVE: 2.tekil/çoğul emir ("iste", "bak", "yap", "isteyin")
   - HYPOTHETICAL: -sA + ana cümle ("şeker yüksekse insülin bakarız", \
     "**gerekirse holter takarız**", "olursa yapacağız")
   - INTERROGATIVE: soru ("- mi?", "- mı?", "lazım mı?", "bakalım mı?")
   - DECLARATIVE: düz haber cümlesi (yalın isim cümlesi, fiil yok ya da \
     -DIr eki ile durum belirten)

5. **intent_etiketi** (KARAR):
   - **REQUEST** ← konuşmacı=DOCTOR + zaman_kipi (FUTURE | OPTATIVE | \
     IMPERATIVE_ACTIVE | IMPERATIVE_PASSIVE) + olumlu cümle
     VEYA liste_kontekst varsa ve ana fiil REQUEST üreten kategoride
   - **PAST_DONE** ← zaman_kipi=PAST_NARRATIVE (kim söylerse söylesin: \
     doktor "iki yıl önce şeker baktınız" dese de geçmiş!)
   - **PATIENT_QUESTION** ← konuşmacı=PATIENT + (INTERROGATIVE veya kendi \
     anlatısı). Veya konuşmacı=DOCTOR + INTERROGATIVE + hastaya yöneltilmiş \
     soru ("Şeker, kolesterol var mı?")
   - **RESULT_DISCUSS** ← tetkik sonucu konuşuluyor ("CRP 5 gelmiş", \
     "ferritin 20", "tiroid normal"), istek değil
   - **OTHER** ← HYPOTHETICAL ("gerekirse"), reddedilen ("önerir misiniz? \
     - hayır gerek yok"), kapanış cümlesi

6. **include**: intent_etiketi == REQUEST AND aday listesinde ilgili kod var

NEGATİF ÖRNEKLER (HİÇ DAHIL ETME):
- "Hasta: öz geçmişte hemogram baktırdım" → PATIENT/PAST_NARRATIVE/PAST_DONE → EXCLUDE
- "Doktor: iki yıl önce şeker baktınız" → DOCTOR/PAST_NARRATIVE/PAST_DONE → EXCLUDE \
  (DİKKAT: doktor söylese bile PAST!)
- "Doktor: şekerin yüksekse insülin bakarız" → DOCTOR/HYPOTHETICAL/OTHER → EXCLUDE
- **"Doktor: gerekirse holter takarız"** → DOCTOR/HYPOTHETICAL/OTHER → EXCLUDE \
  (şartlı ifade — şu an istemiyor)
- **"Doktor: olursa biz tomografi de çekeriz"** → HYPOTHETICAL/OTHER → EXCLUDE
- "Hasta: D vitamini bakar mıyız?" → PATIENT/INTERROGATIVE/PATIENT_QUESTION → EXCLUDE
- "Doktor: Şeker, kolesterol var mı?" → DOCTOR/INTERROGATIVE/PATIENT_QUESTION → \
  EXCLUDE (hastaya yöneltilmiş tarama sorusu)
- "Doktor: CRP 12 gelmiş" → DOCTOR/DECLARATIVE/RESULT_DISCUSS → EXCLUDE \
  (sonuç paylaşımı, istek değil)
- "Doktor: tiroid normal, hemoglobin 12.1, ferritin 20" → 3 mention DECLARATIVE/\
  RESULT_DISCUSS → HEPSİ EXCLUDE

POZİTİF ÖRNEKLER (SEÇ):
- "Doktor: tam kan isteyelim" → DOCTOR/OPTATIVE/REQUEST → INCLUDE
- "Doktor: troponin ve EKG isteyeceğim" → DOCTOR/FUTURE/REQUEST → INCLUDE \
  (iki ayrı mention)
- "Doktor: bir de B12 bakalım" → DOCTOR/OPTATIVE/REQUEST → INCLUDE
- **"Doktor: rutin tahliller isteyeceğiz: kan şekeri, hemogram, TSH, idrar"** \
  → DOCTOR/FUTURE liste-mirası → 4 mention HEPSİ REQUEST → 4'ünü de INCLUDE \
  (kan şekeri, hemogram, TSH, idrar tahlili)
- **"Doktor: Tahliller isteyeceğiz: TSH, T3, T4, anti-TPO, hemogram, açlık \
  kan şekeri, tiroid USG"** → DOCTOR/FUTURE liste-mirası → 7 mention HEPSİ \
  REQUEST → hepsini INCLUDE
- **"Doktor: 8 saat aç kaldıktan sonra açlık kan şekerine bakılsın"** → \
  DOCTOR/IMPERATIVE_PASSIVE/REQUEST → INCLUDE ("bakılsın" pasif emir!)
- **"Doktor: HbA1c ve lipid profili isteyeceğiz"** → DOCTOR/FUTURE 1.çoğul/\
  REQUEST → INCLUDE (1. çoğul "biz" hekim ekibi anlamında ama emir doktorun)
- "Doktor: Açlık kan şekeri, HbA1c ve lipid profili isteyeceğiz. Ön tanı tip 2 \
  diyabet" → 3 mention DOCTOR/FUTURE liste-mirası → REQUEST → INCLUDE

KOD KAYNAĞI KURALI: SADECE aday listesindeki kodları kullan. Aday listesinde \
OLMAYAN bir kodu ASLA UYDURMA. Bilmediğin kodu yazma.

GÜVEN SKORU: kaynak cümle açık ve niyet net ise ≥0.90. Belirsizse 0.60-0.80.

TRANSKRIPT:
{transcript}
{icd_context}
ADAY TETKIKLER:
{candidates}

ÇIKTI (sadece JSON array, markdown fence yok, açıklama yok):
[
  {{
    "kodu": "<adaydan>",
    "adi": "<adaydan>",
    "confidence": 0.95,
    "kaynak_cumle": "<transkriptten tam cümle>",
    "intent_etiketi": "REQUEST",
    "reasoning": "DOCTOR/FUTURE liste-mirası — ana fiil 'isteyeceğiz', tetkik liste öğesi"
  }}
]

Hiçbir aday REQUEST değilse: []
"""


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3.3 — Constitutional V4 SUT prompt
# ─────────────────────────────────────────────────────────────────────────────
# Phase 2.3 SUT eval analizi:
#   - T01/T02: L104520 (Kolesterol Serum) FP — gold farklı varyant istiyor
#   - T17: L102420 (Ferritin Kan) FP — gold L102410 (Ferritin Serum) istiyor
#   - T18: Sodyum/Potasyum Serum/Plazma seçildi, gold Kan varyantı istedi
#   - T06/T08/T15/T18: 801720 (PA tek yön) FP — gold sıklıkla istemiyor
#
# Çözüm: Variant-deduplication kuralları + 3-class discipline + conservative coding

SUT_SELECTION_PROMPT_V4_CONSTITUTIONAL = """\
Sen Türkçe tıbbi tetkik/tahlil uzmanısın. UC ASAMALI hiyerarsik secim yap.

═══════════════════════════════════════════════════════════════════════════
ANAYASAL KURALLAR (her secimde uy):
═══════════════════════════════════════════════════════════════════════════

KURAL #1 — 3-CLASS INTENT DISCIPLINE:
Her tetkik mention'ı için zihinsel olarak SINIFLANDIR:
  ✅ REQUEST: Doktor BUGUN istiyor ("isteyelim/bakalım/yapılsın/çekilsin/isteyeceğim")
  ❌ PAST_DONE: Daha önce yapılmıştı ("baktırmıştım/yapılmıştı/geçen sefer baktık")
  ❌ HYPOTHETICAL: Şartlı ("eğer X yüksekse Y bakarız", "gerekirse")
  ❌ NEGATED: Açıkça reddedilmiş ("istemiyorum/gerek yok/atlayalım")
  ❌ PATIENT_QUESTION: Hasta sorgusu, doktor istemi değil

YALNIZCA REQUEST = REQUEST'ler output'a girer. Şüphe varsa ATLA (tutucu kodla).

KURAL #2 — VARIANT DEDUP (TEK VARYANT):
Bir tetkik için aday listesinde birden çok varyant olabilir. SADECE BİR TANE seç:

  📌 Standart varyant tercihleri:
  - Sodyum/Potasyum/Klorur: "Kan" varyantı ÖNCELİKLİ (kan elektrolit paneli)
    → L106160 Potasyum (Kan), L106920 Sodyum (Kan)
    → L106150/L106910 Serum/Plazma SECME
  - Ferritin: Serum/Plazma varyantı ÖNCELİKLİ
    → L102410 Ferritin (Serum/Plazma) > L102420 Ferritin (Kan)
  - AST/ALT/GGT/ALP/Kreatinin/Üre/Kolesterol: Serum/Plazma standart
    → L101280 AST (Serum/Plazma), L100300 ALT (Serum/Plazma)
    → L102780 GGT (Serum/Plazma), L100710 ALP (Serum/Plazma)
    → L101290/L100310/L102790/L100720 Vücut sıvıları varyantını ASLA seçme
    → "karaciğer enzimi" / "KCFT" / "LFT" denince AST+ALT+GGT+ALP dördü birden istenir
  - CRP: standart (L101850) tek başına
    → L101840 CRP Lateks ve L106680 hsCRP ASLA (sadece doktor adlandırıyorsa)

KURAL #3 — AKCİĞER GRAFİSİ DEFAULT:
  - Doktor "PA akciğer grafisi" derse → 801720 (tek yön)
  - Doktor sadece "akciğer grafisi" derse → 801690 (iki yönlü) DEFAULT
  - Spesifik yön belirtmediyse iki yönlü tercih et

KURAL #4 — KOD-KISITLAMA:
Sadece doktorun NETLİKLE istediği tetkikleri kodla. Şu durumlar HİÇ kodlanmaz:
  ❌ "Falan/filan" geçen genel ifadeler ("tahlil falan istiyorum" tek başına)
  ❌ Hasta sorularına verilen "evet/bakarız" yanıtları (kontekst muğlak)
  ❌ Çıkış sırasında "tahlilleri verin" gibi follow-up komutlar (zaten istenen tetkikler)

KURAL #5 — BRANS FILTRESI:
Tüm seçilen kodlar `brans=dahiliye` veya `her ikisi` olmalı. Diğer branş kodları reddet.

═══════════════════════════════════════════════════════════════════════════
TÜRKÇE MORFOLOJI REHBERI:
═══════════════════════════════════════════════════════════════════════════
- FUTURE (-AcAk): "isteyeceğim/bakacağız" → REQUEST ✅
- OPTATIVE (-AlIm): "isteyelim/bakalım" → REQUEST ✅
- IMPERATIVE_PASSIVE (-sIn): "çekilsin/yapılsın/eklensin" → REQUEST ✅
- PAST_NARRATIVE (-DI/-mIş): "baktım/yapılmıştı" → PAST_DONE ❌
- HYPOTHETICAL (-sA + ana cümle): "yüksekse... bakarız" → HYPOTHETICAL ❌

═══════════════════════════════════════════════════════════════════════════
TRANSCRIPT:
{transcript}

ICD CONTEXT (yardımcı, tani için):
{icd_context}

ADAY SUT KODLARI:
{candidates}

YANIT (sadece JSON array, max 15 kod):
[
  {{
    "kodu": "L107020",
    "adi": "Tam Kan Sayımı (Hemogram)",
    "intent": "REQUEST",
    "confidence": 0.95,
    "trigger_phrase": "<doktorun cümlesi>",
    "reasoning": "DOCTOR/OPTATIVE 'bakalım'; KURAL #2 dedup uygulandı"
  }}
]

Hiçbir aday REQUEST değilse: []
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
        validation_mode: str = "strict",
    ) -> None:
        self._llm = llm
        self._sut = sut_service
        self._vectors = vector_service
        self._ner = ner_service
        # Hallucination guard mode (ablation switch — mirrors ICD pipeline):
        #   "strict"     — drop any LLM-output code not in candidate pool
        #   "db_rescue"  — also accept LLM codes that exist in SUT DB
        # Switched at runtime via ASR_SUT__VALIDATION_MODE env var.
        self._validation_mode = validation_mode if validation_mode in {"strict", "db_rescue"} else "strict"
        logger.info("SUTSuggestionService validation_mode=%s", self._validation_mode)

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

        candidates = await self._inject_panel_aliases(transcript, candidates)

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
        logger.debug(f"[SUT-DEBUG] suggest_from_report called with {len(report_sections)} sections")
        search_parts: list[str] = []
        for key in self._RELEVANT_KEYS:
            val = report_sections.get(key, "").strip()
            logger.debug(f"[SUT-DEBUG]   key={key} val={val[:60]!r} included={bool(val and val not in {'BELIRTILMEDI', 'BELIRTILMEDI.', ''})}")
            if val and val not in {"BELIRTILMEDI", "BELIRTILMEDI.", ""}:
                search_parts.append(val)

        # Fallback: use ALL non-empty report sections
        if not search_parts:
            logger.debug("[SUT-DEBUG]   No relevant keys matched, trying ALL sections...")
            for key, val in report_sections.items():
                val = val.strip()
                if val and val not in {"BELIRTILMEDI", "BELIRTILMEDI.", ""}:
                    search_parts.append(val)
                    logger.debug(f"[SUT-DEBUG]   FALLBACK key={key} val={val[:60]!r}")

        if not search_parts:
            logger.debug("[SUT-DEBUG] NO search_parts found, returning empty")
            return []

        logger.debug(f"[SUT-DEBUG] search_parts count: {len(search_parts)}")

        logger.info("search_parts count: %d", len(search_parts))

        report_text = "\n".join(search_parts)

        ner_terms = await self._extract_ner_terms(report_text)
        logger.info("Report NER extracted %d terms: %s", len(ner_terms), ner_terms[:5])

        vector_candidates = await self._find_vector_candidates(ner_terms, brans=brans)
        text_candidates = await self._text_search_fallback(ner_terms, brans=brans)
        # LLM-explicit extraction skipped under db_rescue mode — DB-rescue at
        # parse time covers the same use case (LLM medical knowledge → DB
        # validation) with one fewer LLM call.
        explicit_candidates: list[dict[str, Any]] = []
        if self._validation_mode == "strict":
            explicit_candidates = await self._llm_extract_and_search(report_text, brans=brans)

        # Merge — RRF if enabled, else naive dedup-concat
        from apps.backend.src.services.rrf_fusion import rrf_fuse, is_rrf_enabled
        if is_rrf_enabled():
            candidates = rrf_fuse(
                [vector_candidates, text_candidates, explicit_candidates],
                id_field="kodu",
                k=60,
            )
            logger.info(
                "RRF fused (SUT): vector=%d + text=%d + explicit=%d → %d unique [mode=%s]",
                len(vector_candidates), len(text_candidates),
                len(explicit_candidates), len(candidates),
                self._validation_mode,
            )
        else:
            candidates = list(vector_candidates)
            seen = {c["kodu"] for c in candidates}
            for src in (text_candidates, explicit_candidates):
                for tc in src:
                    if tc["kodu"] not in seen:
                        seen.add(tc["kodu"])
                        candidates.append(tc)
            logger.info(
                "Report combined %d candidates (vector + text%s) [mode=%s]",
                len(candidates),
                " + llm-explicit" if self._validation_mode == "strict" else "",
                self._validation_mode,
            )
        logger.debug(
            f"[SUT-DEBUG] candidate sources: vector={len(candidates) - len(text_candidates) - len(explicit_candidates)} "
            f"text={len(text_candidates)} llm-explicit={len(explicit_candidates)}",
        )

        candidates = await self._inject_panel_aliases(report_text, candidates)

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
            report_text=_safe_for_format(report_text),
            candidates=_safe_for_format(candidates_text),
        )

        logger.debug(f"[SUT-DEBUG] LLM report-select: {len(candidates)} candidates")

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

        return await self._parse_llm_selection(raw, candidates)

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
            "tiroit", "tiroid", "tsh", "t3", "t4", "anti-tpo", "trab",
            "tsh reseptör antikoru", "tsh reseptor antikoru",
            "karaciğer", "karaciger", "ast", "alt",
            "böbrek", "bobrek", "kreatinin", "üre",
            "kolesterol", "lipid", "trigliserid",
            "röntgen", "rontgen", "mr", "tomografi", "bt",
            "ultrason", "ekg", "eko", "eforlu",
            "akciğer grafisi", "akciger grafisi", "akciğer testi", "akciger testi",
            "tüm batın", "tum batin", "tümbatım", "tum batim",
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
        for fragment in _re.split(r"-{2,}|\+|/{2,}|;|,|\n", transcript):
            token = fragment.strip()
            # Yalnızca tetkik adı gibi görünen kısa parçalar — uzun cümleleri ele.
            if 2 <= len(token) <= 80 and not _re.search(r"[.!?]", token):
                # Sadece bir-iki kelimelik test/kod adı eklensin
                word_count = len(token.split())
                if word_count <= 5:
                    found.append(token)

        # ASR-typo handling: fuzzy match for likely transcription errors
        # ("hemogran" → "hemogram", "tümbatım" → "tüm batın", etc.)
        # Only run on tokens not already captured by exact-match above.
        try:
            from rapidfuzz import fuzz, process
            existing_lower = {f.lower() for f in found}
            tokens = set(_re.findall(r"\b\w{5,}\b", transcript_lower))
            for token in tokens:
                if token in tetkik_keywords or token in existing_lower:
                    continue
                # 85% threshold: catches single-char typos in 5-8 char words
                result = process.extractOne(
                    token, tetkik_keywords, scorer=fuzz.ratio, score_cutoff=85
                )
                if result:
                    canonical_keyword = result[0]
                    if canonical_keyword not in existing_lower:
                        found.append(canonical_keyword)
                        existing_lower.add(canonical_keyword)
                        logger.debug(
                            "[SUT-DEBUG] fuzzy match: %r → %r (score=%d)",
                            token, canonical_keyword, int(result[1]),
                        )
        except ImportError:
            logger.debug("rapidfuzz not available, skipping fuzzy ASR-typo match")

        logger.debug(f"[SUT-DEBUG] keyword extraction found: {found}")
        return found[:25]

    # ------------------------------------------------------------------
    # Step 2: Vector DB search
    # ------------------------------------------------------------------

    async def _find_vector_candidates(
        self, terms: list[str], brans: str | None = None
    ) -> list[dict[str, Any]]:
        """Search vector DB for candidate SUT tetkik codes."""
        # Query expansion: synonyms + per-word significant tokens.
        # Token step (noise-resistance): a phrase like "MENENJİT İHTİMALİ
        # GÖZE ALINIYOR" loses signal in dense embedding because filler
        # words dominate; isolating "menenjit" lets the vector index match.
        from apps.backend.src.services.nlp_normalizer import (
            get_expander, expand_with_tokens,
        )
        expanded = expand_with_tokens(get_expander(), terms)
        if len(expanded) > len(terms):
            logger.debug(
                f"[SUT-DEBUG] expansion (synonyms+tokens): {len(terms)} → {len(expanded)} terms",
            )
        terms = expanded

        logger.debug(f"[SUT-DEBUG] _find_vector_candidates: vectors={self._vectors is not None}, ready={self._vectors.is_ready if self._vectors else False}, terms={terms}")
        if self._vectors is None or not self._vectors.is_ready:
            logger.debug("[SUT-DEBUG] Vector service NOT ready, falling back to text search")
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

    async def _llm_extract_and_search(
        self, report_text: str, brans: str | None = None
    ) -> list[dict[str, Any]]:
        """LLM extracts explicit test names from report, then text-search each.

        Bypasses vector embedding limitations and Turkish-character normalization
        bugs by relying on the LLM to produce proper Turkish forms (e.g.
        "EKOKARDIYOGRAFI" → "EKOKARDİYOGRAFİ") that match the SUT DB exactly.
        """
        prompt = EXPLICIT_TEST_EXTRACTION_PROMPT.format(
            report_text=_safe_for_format(report_text)
        )
        try:
            raw = await self._llm.generate(prompt, "")
        except Exception:
            logger.exception("LLM explicit test extraction failed")
            return []

        cleaned = raw.strip()
        if "```" in cleaned:
            cleaned = re.sub(r"```(?:json)?\s*", "", cleaned).strip()
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if not match:
            return []
        try:
            names = json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            return []
        if not isinstance(names, list):
            return []

        logger.debug(f"[SUT-DEBUG] LLM-extracted explicit test names: {names}")

        # Each LLM-extracted name is synonym-expanded before SUT search.
        # Use substring-aware expand() (not expand_term, which requires exact
        # match) so phrases like "Beyin görüntülemesi (MR/BT)" still surface
        # the dictionary's "beyin görüntülemesi" entry → BT/MR Beyin codes.
        from apps.backend.src.services.nlp_normalizer import get_expander
        expander = get_expander()

        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for name in names[:20]:
            if not isinstance(name, str) or not name.strip():
                continue
            name_clean = name.strip()
            search_terms = {name_clean}
            # Substring-based expansion catches names with extra qualifiers
            search_terms.update(expander.expand(name_clean))
            # Plus exact-key expansion as fallback
            search_terms.update(expander.expand_term(name_clean))
            for term in search_terms:
                results = await self._sut.search(term, limit=3, brans=brans)
                for r in results:
                    if r.kodu not in seen:
                        seen.add(r.kodu)
                        candidates.append({
                            "kodu": r.kodu,
                            "adi": r.adi,
                            "brans": r.brans,
                            "score": 0.95,
                            "source": f"llm_explicit:{name}",
                        })
        return candidates

    async def _inject_panel_aliases(
        self, text: str, candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Force-add SUT codes for panel-alias phrases (KCFT, TİT, ...).

        Vector retrieval can miss panel-level intent (umbrella terms like
        "karaciğer enzimleri"). This guarantees the panel's component
        codes reach the candidate pool with high score before LLM select.
        """
        from apps.backend.src.services.medical_synonyms import find_panel_codes

        panel_codes = find_panel_codes(text)
        if not panel_codes:
            return candidates

        existing = {c["kodu"] for c in candidates}
        added: list[str] = []
        for code in panel_codes:
            if code in existing:
                continue
            row = await self._sut.get_by_code(code)
            if row is None:
                logger.warning("Panel alias maps to unknown SUT code: %s", code)
                continue
            candidates.append({
                "kodu": row.kodu,
                "adi": row.adi,
                "brans": row.brans,
                "score": 1.0,
                "source": "panel_alias",
            })
            added.append(code)
        if added:
            logger.info("Panel alias injected %d SUT codes: %s", len(added), added)
        return candidates

    async def _text_search_fallback(
        self, terms: list[str], brans: str | None = None
    ) -> list[dict[str, Any]]:
        """Fallback: text-based SUT search when vector DB is unavailable."""
        candidates = []
        seen: set[str] = set()
        for term in terms[:25]:
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

        # Intent-disambiguation prompt versioning. v2 = per-mention CoT
        # (default), v1 = legacy single-rule prompt. Switched via
        # ASR_SUT__INTENT_PROMPT_VERSION env var for safe rollback.
        from config.settings import AppSettings
        settings = AppSettings()
        prompt_version = settings.sut.intent_prompt_version
        intent_threshold = settings.sut.intent_min_confidence
        if prompt_version == "v3":
            prompt_template = SUT_SELECTION_PROMPT_V3
        elif prompt_version == "v2":
            prompt_template = SUT_SELECTION_PROMPT_V2
        else:
            prompt_template = SUT_SELECTION_PROMPT
        logger.debug("[SUT-DEBUG] using prompt version=%s", prompt_version)

        prompt = prompt_template.format(
            transcript=_safe_for_format(transcript),
            candidates=_safe_for_format(candidates_text),
            icd_context=_safe_for_format(icd_text),
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

        suggestions = await self._parse_llm_selection(raw, candidates)

        # Confidence gate: dusuk guvenli REQUEST -> NOT_REQUEST. Yanlis
        # pozitif (gereksiz lab istegi → gercek hasta zarari) icin guvenlik.
        # Threshold ASR_SUT__INTENT_MIN_CONFIDENCE env var ile ayarlanir.
        downgraded = 0
        for s in suggestions:
            if s.intent_etiketi == IntentLabel.REQUEST and s.confidence < intent_threshold:
                s.intent_etiketi = IntentLabel.NOT_REQUEST
                tail = f"[confidence<{intent_threshold}, NOT_REQUEST'e indirildi]"
                s.reasoning = f"{s.reasoning} {tail}".strip()
                downgraded += 1
        if downgraded:
            logger.info(
                "Confidence gate: %d REQUEST → NOT_REQUEST (threshold=%.2f)",
                downgraded, intent_threshold,
            )

        return suggestions

    async def _parse_llm_selection(
        self,
        raw: str,
        candidates: list[dict[str, Any]] | None = None,
    ) -> list[SUTSuggestion]:
        """Parse LLM's JSON selection response.

        Hallucination guard depends on ``self._validation_mode`` (set at init,
        switched via ASR_SUT__VALIDATION_MODE env var) — mirrors ICD pipeline
        for thesis ablation:

          - "strict"     drop any code not in candidate pool
          - "db_rescue"  also accept LLM codes that exist in SUT DB
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
            logger.warning("Failed to parse LLM SUT tetkik selection: %s", raw[:200])
            return []

        cand_by_code: dict[str, dict[str, Any]] = {}
        if candidates is not None:
            cand_by_code = {str(c.get("kodu", "")): c for c in candidates}

        suggestions: list[SUTSuggestion] = []
        dropped: list[str] = []
        rescued: list[str] = []
        for item in parsed[:10]:
            kodu = str(item.get("kodu", "")).strip()
            if not kodu:
                continue
            adi = item.get("adi", "")
            brans = item.get("brans", "")

            if kodu in cand_by_code:
                cand = cand_by_code[kodu]
                adi = cand.get("adi", adi)
                brans = cand.get("brans", brans)
            elif self._validation_mode == "db_rescue":
                # Aday listesinde yok — DB'de var mı diye sor
                db_row = await self._sut.get_by_code(kodu)
                if db_row is None:
                    dropped.append(kodu)
                    continue
                adi = db_row.adi or adi
                brans = db_row.brans or brans
                rescued.append(kodu)
            else:  # strict
                dropped.append(kodu)
                continue

            # V2 alanlari: yeni LLM cevabi kaynak_cumle + intent_etiketi
            # iceriyorsa parse et. V1 cevabinda alanlar yok → safe defaults.
            kaynak_cumle = str(item.get("kaynak_cumle", ""))[:200]  # storage hijyeni
            intent_raw = str(item.get("intent_etiketi", "REQUEST")).strip().upper()
            try:
                intent_etiketi = IntentLabel(intent_raw)
            except ValueError:
                logger.warning(
                    "Invalid intent_etiketi=%r from LLM for kodu=%s, defaulting OTHER",
                    intent_raw, kodu,
                )
                intent_etiketi = IntentLabel.OTHER

            suggestions.append(
                SUTSuggestion(
                    kodu=kodu,
                    adi=adi,
                    brans=brans,
                    confidence=float(item.get("confidence", 0.5)),
                    reasoning=item.get("reasoning", ""),
                    kaynak_cumle=kaynak_cumle,
                    intent_etiketi=intent_etiketi,
                )
            )
        if dropped:
            logger.warning(
                "Dropped %d hallucinated SUT code(s) [mode=%s]: %s",
                len(dropped), self._validation_mode, dropped,
            )
        if rescued:
            logger.info(
                "DB-rescued %d SUT code(s) (LLM proposed, DB validated): %s",
                len(rescued), rescued,
            )
        return suggestions
