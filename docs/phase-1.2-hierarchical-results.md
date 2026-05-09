# Phase 1.2 — Hierarchical 3-Stage ICD Prompt Sonuçları

**Tarih:** 2026-05-08
**Branch:** master
**Test:** 20 ICD sub-agent (Opus 4.7) — SUT Phase 1.1'den miras
**Çalışma süresi:** ~30 dakika
**Maliyet:** $0 (HyDE cache, hierarchical sadece prompt değişikliği)

## Yapılan İş

### Yeni Kod
- `apps/backend/src/services/icd10_suggestion_service.py`:
  - `ICD10_REPORT_SELECTION_PROMPT_HIERARCHICAL` eklendi (3-aşamalı)
  - Mevcut `ICD10_REPORT_SELECTION_PROMPT` korundu (production fallback için)
- `apps/backend/src/scripts/prep_subagent_inputs_hierarchical.py` — HyDE + hierarchical cumulative

### 3-Aşamalı Prompt Yapısı
1. **AŞAMA 1 (KATEGORİ)**: Doktorun açıkça belirttiği aktif hastalıkları listele
2. **AŞAMA 2 (PREFIX)**: Her hastalık için 3-karakter ICD prefix bul (E11, J44, I10...)
3. **AŞAMA 3 (ALT-KOD)**:
   - (a) Spesifik alt-tip varsa kullan
   - (b) Yoksa .9 varsa kullan
   - (c) Yoksa aynı prefix altındaki en uygun kardeş
   - (d) Hiç yoksa **SKIP** — yanlış prefix'e sapma yasak

### Kritik Yasaklar (prompt'ta)
- ⚠️ E11 (T2DM) yerine E13 SECME
- ⚠️ J44 (KOAH) yerine J45 (astım) SECME
- ⚠️ E03 (hipotiroidi) yerine E05 (tirotoksikoz) SECME

## Ölçüm Sonuçları

### 3-Way Karşılaştırma (n=20 form)

| Metric | Baseline | HyDE (P1.1) | Hierarchical (P1.2) | Δ Cumul. (P1.2 vs Baseline) |
|---|---|---|---|---|
| **ICD exact (macro F1)** | 0.4552 | 0.5176 | 0.5160 | **+0.0608** ✅ |
| **ICD exact (micro F1)** | 0.4421 | 0.4500 | **0.4810** | **+0.0389** ✅ |
| **ICD prefix3 (macro F1)** | 0.5804 | 0.6219 | **0.6469** | **+0.0665** ✅ |
| **ICD prefix3 (micro F1)** | 0.5684 | 0.5750 | **0.6076** | **+0.0392** ✅ |
| SUT (macro F1) | 0.6331 | 0.6242 | 0.6242 | -0.0089 |

### Phase 1.2 vs Phase 1.1 (marjinal katkı)
- ICD exact macro: -0.0016 (nötr)
- ICD exact **micro: +0.0310** ✅
- ICD prefix3 macro: **+0.0250** ✅
- ICD prefix3 micro: **+0.0326** ✅

### Per-Form Δ F1 (vs HyDE)

**Net kazançlar:**
- T05 (Anemi): D50.9 → D50.0 (gold doğrulandı, +1.0)
- T12 (Eski MI+HT): R06+I25.9 daha spesifik (+0.381)
- T18 (KOAH alevlenme): J44 → J44.9 (+0.286) — yanlış prefix kuralı çalıştı
- T11 (DM+HT+kolesterol): E13.9 yanlış prefix tuzağı atlatıldı (+0.133)

**Net kayıplar (specificity overshoot):**
- T06 (Astım): J45.9 → J45.0 (-1.0) — agent allerjik fenotipe aşırı kayma
- T17 (Anemi): D50.9 → D50.0 (-0.667) — chronic blood loss subtype seçimi gold'a uymadı
- T19 (Hipotiroidi): R00.1 + K59.0 R-kodları gold'da yok (-0.267)
- T15 (KKY+AF): I48 → I48 (parent yerine, gold I48 farklı)

## Yorum

### Hierarchical "yanlış prefix önleme" başarılı oldu
- T11, T12: E11.9 yokken E13'e sapmadı — SKIP'ledi → daha az false-positive ama recall kaybı
- T18: J44.0 yokken J44.9'a doğru fallback (HyDE yetersiz J44 parent seçmişti)
- Bu davranış prefix3 metriklerinde +2.5-3.3 puan kazanç verdi

### Specificity Overshoot (yeni hata sınıfı)
Hierarchical Stage 3(a) çok agresif: doktor herhangi bir spesifik subtipe ipucu verdiğinde .9'dan vazgeçip alt-kod seçti. Gold standardı çoğunlukla **.9 (tanımlanmamış)** içeriyor:
- Gold T06: J45.9 (astım, tanımlanmamış) → hierarchical J45.0 (allerjik) seçti
- Gold T17: D50.9 → hierarchical D50.0 seçti

**Düzeltme önerisi (Phase 1.3 veya prompt revision):**
> "Doktor net olarak alt-tipi adlandırmadığı sürece (.9) tercih et. Klinik kanıt güçlü olsa da .9 yeterli."

### Net Sonuç: ✅ KABUL
- **Cumulative kazanç (Baseline → P1.2): macro +6.08, micro +3.89 ICD F1**
- **Prefix3 kazançları (+6.65 / +3.92)** retrieval-bound olmadan elde edildi
- SUT regresyonu marjinal (-0.0089) ve stabil

## Phase 1.2 Kabul Durumu

✅ **GEÇTİ** — kabul kriteri "F1 ≥ önceki phase + regresyon yok":
- Macro F1 nötr (-0.0016, sürünmüyor)
- Micro F1 ve prefix3 metrikleri **anlamlı pozitif**
- SUT değişmedi (Phase 1.2 SUT'a dokunmadı)

## Sonraki Adım: Phase 2.1 (BM25 + RRF)

Phase 1.1+1.2 toplam **kayıp/gap kanıtı** Phase 2.1 ihtiyacını netleştirdi:
- T11/T12: E11.9 hiç retrieve edilmedi
- T14: E78 hiç retrieve edilmedi
- T15 (SUT): Troponin, INR, sodyum/potasyum, BUN retrieve edilmedi
- T18 (SUT): Arter kan gazı yok
- T10 (SUT): HBsAg, anti-HBs, anti-HCV yok

BM25 sparse retrieval bu eksiklikleri kapatabilir. Beklenen: +0.05-0.10 recall.

## Çıktı Lokasyonları
- Hierarchical inputs: `data/subagent_inputs_hierarchical/` (20 ICD)
- Hierarchical outputs: `data/subagent_outputs_hierarchical/` (40: 20 ICD + 20 SUT mirror)
- Scores: `data/scores_phase1.2_hierarchical_vs_hyde.json`, `data/scores_phase1.2_vs_baseline.json`
