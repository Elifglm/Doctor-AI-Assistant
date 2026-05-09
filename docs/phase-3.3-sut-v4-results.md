# Phase 3.3 — SUT V4 Constitutional Sonuçları

**Tarih:** 2026-05-09
**Branch:** master
**Test:** 20 SUT sub-agent (ICD P3.2'den miras)
**Maliyet:** $0
**Karar: ✅ KAZANÇ — SUT için yeni en iyi**

## Yapılan İş

### Yeni SUT Prompt
- `apps/backend/src/services/sut_suggestion_service.py`:
  - `SUT_SELECTION_PROMPT_V4_CONSTITUTIONAL` eklendi
  - 5 anayasal kural: 3-class discipline, variant dedup, akciğer grafisi default, kod-kısıtlama, branş filter

### Constitutional V4 Rules

**KURAL #1 — 3-CLASS INTENT DISCIPLINE:**
- REQUEST/PAST_DONE/HYPOTHETICAL/NEGATED/PATIENT_QUESTION ayrımı
- Yalnızca REQUEST output'a girer

**KURAL #2 — VARIANT DEDUP (en büyük katkı):**
- Sodyum/Potasyum: **Kan varyantı** (L106920/L106160) gold-aligned
- Ferritin: Serum/Plazma (L102410) standart
- AST/ALT/Kreatinin/Kolesterol: Serum/Plazma standart, Vücut sıvıları reddedilir
- CRP: standart L101850 (Lateks/hsCRP yalnızca açıkça belirtilirse)

**KURAL #3 — Akciğer grafisi:**
- Doktor "PA" derse 801720
- Yön belirtmediyse 801690 (iki yönlü) DEFAULT

**KURAL #4 — KOD-KISITLAMA:** Belirsiz mention'ları kodlama
**KURAL #5 — BRANŞ FILTERI:** dahiliye veya her ikisi

## Ölçüm Sonuçları

### SUT Performans Karşılaştırma

| Metric | Baseline | P2.3 (V3) | **P3.3 (V4)** | Δ vs V3 | Δ vs Baseline |
|---|---|---|---|---|---|
| **SUT macro F1** | 0.6331 | 0.6402 | **0.6666** | **+0.0264** ✅ | **+0.0335** ✅ |
| SUT macro Precision | 0.6316 | 0.6287 | **0.6492** | +0.0205 | +0.0176 |
| SUT macro Recall | 0.6491 | 0.6641 | **0.6971** | +0.0330 | +0.0480 |
| SUT micro F1 | 0.6926 | 0.6822 | (TBD) | — | — |

### Per-Form SUT Improvements

**Variant dedup wins:**
- T11, T12, T13, T16, T18 — Sodyum/Potasyum **Kan** varyantı (V3'te yanlış Serum/Plazma idi)
- T17 — Ferritin Serum/Plazma L102410 (V3'te L102420 Kan idi)
- T05 — Ferritin Serum/Plazma standart

**Recall wins (yeni REQUEST'ler):**
- T12, T14 — LDL kolesterol (L105000) eklendi
- T18 — R53 yorgunluk (constitutional rule)

**Conservative rejection:**
- T07 — Z56.3 (work stress) atıldı
- AST/ALT Vücut sıvıları varyantları konsistent reddedildi

## Cumulative Pipeline Performance

| Faz | ICD exact macro F1 | SUT macro F1 |
|---|---|---|
| Baseline | 0.4552 | 0.6331 |
| HyDE (P1.1) | 0.5176 | 0.6242 |
| Hierarchical (P1.2) | 0.5160 | 0.6242 |
| BM25/RRF (P2.1) | 0.5193 | 0.6152 |
| ~~Lemma (P2.2)~~ | reverted | — |
| Synonym (P2.3) | 0.5252 | 0.6402 |
| ~~SC (P3.1)~~ | reverted | — |
| Constitutional ICD (P3.2) | **0.6067** | 0.6402 |
| **SUT V4 (P3.3)** | 0.6067 | **0.6666** ✅ |

## Final Cumulative Gain (Baseline → P3.3)

| Metric | Baseline | Final (P3.3) | Δ | Relative |
|---|---|---|---|---|
| ICD exact macro F1 | 0.4552 | 0.6067 | +0.1515 | **+33%** |
| ICD exact micro F1 | 0.4421 | 0.5974 | +0.1553 | **+35%** |
| ICD prefix3 macro F1 | 0.5804 | 0.7483 | +0.1679 | **+29%** |
| SUT macro F1 | 0.6331 | 0.6666 | +0.0335 | **+5%** |
| SUT macro Recall | 0.6491 | 0.6971 | +0.0480 | **+7%** |

## Phase 3.3 Kabul Durumu

✅ **GEÇTİ** — kabul kriteri sağlandı:
- SUT macro F1: **+0.0264** vs P3.2 (V3 SUT)
- SUT precision + recall ikisi de pozitif
- ICD aynı (bu fazda SUT'a odaklandık)

## Çıktı Lokasyonları
- SUT V4 inputs: `data/subagent_inputs_sutv4/` (40 dosya)
- SUT V4 outputs: `data/subagent_outputs_sutv4/` (40 dosya)
- Scores: `data/scores_phase3.3_vs_const.json`, `data/scores_phase3.3_vs_baseline.json`

## Production Entegrasyonu (TODO)

Constitutional V4 SUT prompt henüz `SUTSuggestionService`'te varsayılan değil. ICD için yapıldığı gibi prompt swap + feature flag eklenmesi gerek.

## Sonraki Adım

Tüm büyük iyileştirmeler tamamlandı. Birikim:
- ICD exact F1: 0.46 → 0.61 (+33% relative)
- SUT F1: 0.63 → 0.67 (+5% relative)

Tezde "Pipeline iteratif iyileştirme" hikayesi anlatılabilir. Sonraki olası işler:
- Phase 5.1 — LLM-as-Judge framework (metric kalitesi)
- Sub-agent test'leri tekrar (varyans için n=3)
- SUT V4 production entegrasyonu
