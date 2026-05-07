# Tetkik Intent Sprint — Resume Document

**Branch:** `feature/sut-intent-disambiguation`
**Tarih:** 2026-05-05
**Faz framework:** `C:\Users\Furkan\Desktop\agent-teams-pipeline.md`
**Memory pointer:** `~/.claude/.../memory/project_tetkik_intent_sprint.md`

---

## Bugünün durumu (kapanış)

| Faz | Durum |
|---|---|
| Faz 0 — anlama + onay | ✅ tamam (kullanici 6 soruya cevap verdi, scope kilit) |
| Faz 1 — 4 paralel agent | ✅ tamam (kok neden / arastirici / impact / guvenlik) |
| Faz 2 — sentez + alternatifler | ✅ tamam (Alternatif A onerildi, B yedek) |
| Faz 3 — implementasyon plani | ✅ tamam (8 adim, A) |
| Faz 4 Step 0 — guvenlik prereq | ✅ tamam (commit `c2c8af2`) |
| Faz 4 Step 1 — schema (IntentLabel + opsiyonel alanlar) | ✅ tamam (`ef50682`) |
| Faz 4 Step 2 — V2 prompt (per-mention CoT) | ✅ tamam (`adc828a`) |
| Faz 4 Step 3 — parser V2 alanlari | ✅ tamam (`f71f7b7`) |
| Faz 4 Step 4 — confidence gate | ✅ tamam (`24e51b7`) |
| Faz 4 **Step 5a — gold standard taslaklari** | ✅ tamam (`183995e`) |
| Faz 4 **Step 5b — kullanici review** | ⏳ **YARIN** (user + arkadaslar + doktor) |
| Faz 4 Step 6 — baseline + iter | ⏳ user review sonrasi (~$0.30 API) |
| Faz 4 Step 7 — sprint raporu | ⏳ Step 6 sonrasi |

---

## Yarin senin yapacaklarin (Step 5b)

### 1. Kontrollu transkriptlerin REVIEW formlarini ac

```
data/eval_intent/REVIEW_105.md
data/eval_intent/REVIEW_106.md
data/eval_intent/REVIEW_108.md
data/eval_intent/REVIEW_109.md
data/eval_intent/REVIEW_110.md
data/eval_intent/REVIEW_111.md
```

Toplam 33 mention 6 transkript boyunca. Her .md dosyasi:
- Talimat bolumu (REQUEST / PAST_DONE / PATIENT_QUESTION / RESULT_DISCUSS / OTHER)
- Mention 1/N, 2/N, ... seklinde sirali

### 2. Arkadaslarin + doktor ile birlikte her mention icin

- Onerilen Intent dogru mu? (Yanlissa duzeltme)
- Tetkik adi dogru mu? (Yakalanan canonical isim dogru mu)

### 3. Eksikler kontrolu (FALSE NEGATIVE tarayisi)

`extract_gold_intent.py` script'i sadece `data/medical_synonyms.json` ve
`Tetkik.xlsx` 231 ADI'da olan tetkikleri yakalar (toplam 464 surface form).
Transkriptte gecen ama liste disinda kalan tetkikler kacirilabilir.

Lutfen her transkripti hizli bir kez gozden gecirip "asagidaki listede olmayan
ek tetkik mention varsa" ekleyin (.md dosyasinin sonuna manuel ekleme).

Ornek FORM 108-111 hicbirinde REQUEST etiketi yok — bu dogru mu? Yoksa
heuristic kacirdi mi?

### 4. Geri donus formati (sana esnek)

Iki secenek:
- **(a)** REVIEW_*.md dosyalarinda checkbox'lari doldur, "FALSE → DOGRUSU: X"
  satirlarini yazip bana goster
- **(b)** Sozlu olarak "FORM 105 mention 4 yanlis, gercek PAST_DONE" diye
  anlatip bana liste halinde verin. Daha hizli.

### 5. Bekleme alani

Bu adimda ben hicbir sey yapmiyorum — taslaklar hazir, review sende.

---

## Ben yarin nasil devam ederim (Step 5b → Step 7)

### Resume komutlari

```bash
git checkout feature/sut-intent-disambiguation
git log --oneline ^master                    # 6 commit gor
cat apps/backend/src/rag/SPRINT_INTENT_2026-05-05_RESUME.md  # bu dosya
```

### Yapilacaklar

1. **Step 5b (~10 dk):** kullanicinin duzeltmelerini al, gold_*_DRAFT.json'lari
   guncelle → gold_*_FINAL.json olustur
2. **Step 6 (~30 dk + ~$0.30 API):**
   - `apps/backend/src/scripts/eval_sut_intent.py` (yeni) yaz: gold karsilastirmali
     metric runner (9 metrik)
   - 6 transkripte `suggest()` calistir, ciktilari gold ile karsilastir
   - Hata kategorileri analiz et
   - Gerekirse 2-3 prompt iterasyonu
3. **Step 7 (~10 dk):** sprint raporu, memory update, A yeterli mi karari

---

## Kod degisikliklerinin ozeti (commit-by-commit)

### `c2c8af2` Step 0 — Guvenlik prereq
- `print("[SUT-DEBUG] ...")` cagrilarini `logger.debug(...)`'a cevirdi (13 adet)
  → stdout'a PHI sizdiran loglari kaldirdi
- `_safe_for_format()` helper: doktor sozune `{`/`}` injection guard
- `config/settings.py:SUTSettings`: `intent_prompt_version` ve
  `intent_min_confidence` config alanlari
- `.env.example`: `ASR_SUT__INTENT_PROMPT_VERSION=v2`,
  `ASR_SUT__INTENT_MIN_CONFIDENCE=0.70`
- `/api/v1/sut-tetkik/suggest` endpoint'ine audit log (KVKK Madde 12; metadata-only,
  raw transkript log'lanmaz)

### `ef50682` Step 1 — Schema
- `apps/backend/src/schemas/sut_tetkik.py`: `IntentLabel` enum (REQUEST,
  PAST_DONE, PATIENT_QUESTION, RESULT_DISCUSS, OTHER, NOT_REQUEST)
- `SUTSuggestion.kaynak_cumle: str = ""` ve `intent_etiketi: IntentLabel = REQUEST`
  (her ikisi de opsiyonel default → geriye uyumlu)
- `apps/frontend/src/renderer/src/types/sut_tetkik.ts`: TypeScript ayna
  (opsiyonel `kaynak_cumle?`, `intent_etiketi?`)
- `shared/api-spec.json`: ATLANDI — SUT endpoint'leri zaten yokmus orada
  (geriye donuk gap, memory'e ileri gorev)

### `adc828a` Step 2 — V2 prompt
- `SUT_SELECTION_PROMPT_V2` constant (3053 char)
- Per-mention CoT: kaynak_cumle + konusmaci + zaman_kipi + intent
- Turkce morfoloji ipuclari: -mIstI/-mIs/-dI (PAST), -AlIm/-AcAk (REQUEST),
  -sA (HYPOTHETICAL)
- 5 negatif + 3 pozitif paired ornek
- `_llm_select` version-aware: env var `ASR_SUT__INTENT_PROMPT_VERSION`
- v1 (legacy) tam fallback olarak korundu — config-only rollback

### `f71f7b7` Step 3 — Parser
- LLM ciktisindan `kaynak_cumle` (200 char limit) + `intent_etiketi` parse et
- Enum validation: gecersiz deger → `IntentLabel.OTHER`
- V1 (eski) cevabi gelirse alanlar default (`kaynak_cumle=""`, intent=REQUEST)
- 5/5 smoke test yesil

### `24e51b7` Step 4 — Confidence gate
- `_llm_select` post-process: `intent=REQUEST` + `confidence < threshold` →
  `NOT_REQUEST` (gerekce reasoning'e eklenir)
- Threshold env var `ASR_SUT__INTENT_MIN_CONFIDENCE` (default 0.70)
- Logic test: 5/5 case yesil

### `183995e` Step 5a — Gold standard taslaklari
- `apps/backend/src/scripts/extract_gold_intent.py` (yeni)
- 6 .docx transkriptini python-docx ile oku
- 464 surface form lexicon (231 ADI + medical_synonyms.json'dan)
- Heuristic intent oneri (speaker + tense regex)
- Iki cikti per transkript:
  - `data/eval_intent/gold_<form>_DRAFT.json` (eval input)
  - `data/eval_intent/REVIEW_<form>.md` (insan review)
- 33 mention, 6 REQUEST draft

---

## Test durumu

Bugun yapilan smoke testler:
- ✅ Settings yukleme: `AppSettings().sut.intent_prompt_version == 'v2'`
- ✅ Schema: legacy ctor + new fields + invalid enum reddi (3 test)
- ✅ V2 prompt interpolation + injection guard
- ✅ Parser: V1 fallback / V2 valid / invalid intent / truncation /
  hallucination drop (5 test)
- ✅ Confidence gate: 5 case (high/low/threshold/non-REQUEST/OTHER)
- ✅ Tum dosyalar `py_compile` clean
- ✅ Mevcut test suite'i etkileniyor mu yarin Step 6'da kontrol edecegiz

---

## Acik durum / dikkat noktalari

1. **Step 5a heuristic noisy:** ornek FORM 105 mention 4'te kolesterol
   "isteyeceğim" cumlesinde gecti ama gercekte ayni cumlenin "iki yıl önce
   bakmışsınız" kismi → PAST_DONE. Tense detection cumle bazinda calisti,
   noun-level kontekst yakalamiyor. User review duzeltecek.

2. **FORM 108-110'da 0 REQUEST draft:** ya gercekten doktor istek soylememis
   (ki muhtemel — yari kontrollu kayit), ya heuristic kacirmis. User
   transkripti hizli okuyup dogrulayacak.

3. **api-spec.json:** SUT endpoint'leri yok (preexisting gap). Bu sprint
   scope'unda dokumantasyon yapilmadi. Memory: `project_api_spec_gap.md`.

4. **Vector DB / kanonik kod eslesmesi:** Bu sprint'te atlandi. Smoke testte
   MiniLM Turkce medikal jargonu zayif gorundu (B12 → BT Skapula vs).
   Sonraki sprint icin: `project_vector_db_future.md` (BGE-M3'e gec, Tetkik.xlsx
   eksik tetkikleri sut_tetkik.db'ye ekle).

5. **Bütce:** bugun Faz 4 Step 0-5a icin 0 API harcandi. Step 6 icin ~$0.30
   tahmin. Mevcut ~$0.51 ile rahat.

---

## Memory dosyalari (bu sprint icin)

- `project_tetkik_intent_sprint.md` — sprint durum + metrikler + 8 adim
- `project_vector_db_future.md` — vector DB ileri gorev
- `project_api_spec_gap.md` — api-spec eksigi ileri gorev
- `feedback_intent_vs_prediction.md` — prev mistake (yanlis goreve eval kostum)
- `feedback_api_budget.md` — API butce kisidi
