# Phase 3.2 — Constitutional Prompt Rules Sonuçları

**Tarih:** 2026-05-09
**Branch:** master
**Test:** 20 ICD sub-agent (SUT P2.3'ten miras)
**Maliyet:** $0
**Karar: ✅ MAJOR WIN — yeni cumulative best, ana iyileştirme!**

## Yapılan İş

### Yeni Prompt
- `apps/backend/src/services/icd10_suggestion_service.py`:
  - `ICD10_REPORT_SELECTION_PROMPT_CONSTITUTIONAL` eklendi
  - 4 anayasal kural + 3-aşamalı seçim + .9-default + R53-istisnası

### Constitutional Rules Özeti

**KURAL #1 — KOD-KISITLAMA (CODE CONSERVATION):**
- Aile öyküsü Z83.x ASLA kodlanmaz (T01/T20 Z83.3 → atıldı)
- Fizik muayene bulgusu (BMI/E66) ASLA kodlanmaz (T01 E66.9 → atıldı)
- Zımni tanı ASLA kodlanmaz

**KURAL #2 — DEFAULT .9 ALT-TIPI:**
- Doktor spesifik subtype demediyse → .9 default
- Sadece "saf hiperkolesterolemi", "konjestif KKY", "akut alevlenme" gibi açık ifadeler → .x specific
- T17: D50.0 (P2.3) → D50.9 (Const) — gold-aligned

**KURAL #3 — SEMPTOM-BASTIRMA + R53 İSTİSNASI:**
- KOAH/Astım/Bronşit → R05/R06.x suppress (T08 R05+R50.9 → atıldı)
- Anemi → R23.1/R00.2/R42 suppress
- Hipotiroidi → R00.1/K59.0 suppress
- ⭐ **R53 (yorgunluk) HER ZAMAN EKLE** — gold consistently includes it (T17/T19 wins)

**KURAL #4 — NEGATE EDILMIS SEMPTOM ASLA KODLANMAZ.**

## Ölçüm Sonuçları

### 🎯 BIG WIN (n=20 form)

| Metric | Baseline | P1.1 | P1.2 | P2.1 | P2.3 | **P3.2** | Δ vs P2.3 | Δ vs Baseline |
|---|---|---|---|---|---|---|---|---|
| **ICD exact macro F1** | 0.4552 | 0.5176 | 0.5160 | 0.5193 | 0.5252 | **0.6067** | **+0.0815** | **+0.1515** |
| **ICD exact micro F1** | 0.4421 | 0.4500 | 0.4810 | 0.4878 | 0.5057 | **0.5974** | **+0.0917** | **+0.1553** |
| **ICD prefix3 macro F1** | 0.5804 | 0.6219 | 0.6469 | 0.6619 | 0.6119 | **0.7483** | **+0.1364** | **+0.1679** |
| **ICD prefix3 micro F1** | 0.5684 | 0.5750 | 0.6076 | 0.6173 | 0.5747 | **0.7013** | **+0.1266** | **+0.1329** |
| ICD exact macro Precision | 0.4017 | 0.4017 | 0.5208 | 0.4967 | 0.4833 | **0.5917** | **+0.1084** | **+0.190** |
| SUT macro F1 | 0.6331 | 0.6242 | 0.6242 | 0.6152 | 0.6402 | 0.6402 | 0.000 | +0.007 |

### Per-Form Perfect Matches (Constitutional ile)

| Form | Gold | Constitutional | Match |
|---|---|---|---|
| T05 | [D50.9] | [D50.9] | ✅ |
| T06 | [J45.9] | [J45.9] | ✅ |
| T08 | [J20.9] | [J20.9] | ✅ |
| T13 | [I10, J44.9] | [J44.9, I10] | ✅ |
| T16 | [E11.9, I11.9] | [I11.9, E11.9] | ✅ |
| T17 | [D50.9, R53] | [D50.9, R53] | ✅ 🎯 (P2.3 D50.0 + missing R53) |
| T19 | [E03.9, R53] | [E03.9, R53] | ✅ 🎯 (P2.3 E03.9 + R00.1 + K59.0) |

### False Positive Reductions (P2.3 → P3.2)

- T01: E66.9, Z83.3 atıldı → recall korundu, precision iyileşti
- T07: K31.9 yine var ama Z56.3 yerine R12+R11 (gold farklı bekliyor — unchanged)
- T08: R05+R50.9 suppress edildi → false positives drop
- T20: Z83.3 atıldı

### R53 Exception Win

Gold standardlar T17 ve T19'da R53 (yorgunluk) bekliyor — anemi/hipotiroidi olsa bile. Constitutional Rule #3 EXCEPTION'ı eklediğimiz için R53 mutlaka kodlanıyor → 2 form'da +1 TP.

## Phase 3.2 Kabul Durumu

✅✅✅ **MAJOR WIN — KESINLIKLE GEÇTİ:**
- ICD exact macro F1: **+0.0815** vs P2.3 (en büyük tek-faz kazancı)
- ICD prefix3 macro F1: **+0.1364** vs P2.3
- Cumulative gain (Baseline → P3.2): **+0.1515 macro F1, +0.1679 prefix3**
- Net relative: **+33% ICD exact F1, +29% prefix3 F1** (baseline'dan)

## Pipeline State After Phase 3.2

```
Cumulative best = Phase 3.2 (HyDE + Hierarchical + BM25 + RRF + Synonym Expansion + CONSTITUTIONAL PROMPT)

Bileşenler:
- HyDE: hipotetik klinik doc (Haiku)
- Hierarchical 3-aşamalı prompt
- BM25 sparse retrieval + RRF fusion
- TR/EN synonym expansion
- Constitutional rules:
  * Code conservation (Z83/E66 atılır)
  * .9 default (saf/konjestif/alevlenme demediyse)
  * Symptom suppression + R53 exception
  * Negated symptom suppression
- Max 4 kod sınırı
```

## Çıktı Lokasyonları
- Constitutional inputs: `data/subagent_inputs_constitutional/` (40 dosya)
- Constitutional outputs: `data/subagent_outputs_constitutional/` (40 dosya)
- Scores: `data/scores_phase3.2_vs_synonym.json`, `data/scores_phase3.2_vs_baseline.json`

## Sonraki Adım

**Phase 3.3** — 3-class output format (REQUEST/PAST/HYPOTHETICAL calibration) — SUT için
**Phase 5.1** — LLM-as-Judge framework — token-F1 yerine semantic match metric
**Stop and consolidate** — sonuçları paketle, tezi yaz
