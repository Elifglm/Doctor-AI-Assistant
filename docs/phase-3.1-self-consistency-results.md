# Phase 3.1 — Self-Consistency Decoding Sonuçları (NEGATIVE / REVERTED)

**Tarih:** 2026-05-09
**Branch:** master
**Test:** 80 ek sub-agent (20×2 round; 20×3 = round 1 P2.3'ten geliyor)
**Maliyet:** $0
**Karar: ❌ REGRESSION → Phase 2.3 best kalıyor**

## Yapılan İş

### Yeni Kod
- `apps/backend/src/scripts/aggregate_self_consistency.py`
  - N round çıktıyı majority-vote ile birleştirir
  - threshold parametresi: bir kodun consensus'a girmesi için ≥k round oyu gerekli
  - Her kod için `sc_votes` ve `sc_rounds` metadata ekler

### Procedure
1. Round 1 = Phase 2.3 outputs (`data/subagent_outputs_synonym/`, 40 dosya)
2. Round 2 = 40 yeni ICD sub-agent (`data/subagent_outputs_synonym_r2/`)
3. Round 3 = 40 yeni ICD sub-agent (`data/subagent_outputs_synonym_r3/`)
4. SUT outputs r1'den r2 ve r3'e kopyalandı (SUT bu fazda değişmedi)
5. Aggregate threshold=2 (≥2 of 3) ve threshold=3 (≥3 of 3, strict)

## Ölçüm Sonuçları

### Comparison Table (n=20 form)

| Metric | Baseline | P2.3 (best) | **P3.1 t=2** | **P3.1 t=3** | Δ t=2 vs P2.3 |
|---|---|---|---|---|---|
| ICD exact macro F1 | 0.4552 | **0.5252** | 0.5036 | 0.5019 | **-0.0216** ⚠️ |
| ICD exact micro F1 | 0.4421 | **0.5057** | 0.5000 | 0.5063 | -0.0057 |
| ICD prefix3 macro F1 | 0.5804 | **0.6119** | 0.6069 | 0.5886 | -0.0050 |
| ICD prefix3 micro F1 | 0.5684 | 0.5747 | 0.5747 | **0.5823** | 0.0000 |
| SUT macro F1 | 0.6331 | **0.6402** | 0.6402 | 0.6402 | 0.0000 |

### Precision/Recall Trade-Off

threshold=2 (≥2 of 3):
- ICD exact macro **P=0.446** (vs P2.3 0.483): **-3.7 puan**
- ICD exact macro **R=0.646** (vs P2.3 0.646): **same**

threshold=3 (≥3 of 3, strict):
- ICD exact macro **P=0.492** (vs P2.3 0.483): **+0.9 puan** (slight gain)
- ICD exact macro **R=0.571** (vs P2.3 0.646): **-7.5 puan**

threshold=3 precision'ı iyileştirdi (false positive filtreleme) ama recall'u 7.5 puan düşürdü. Net F1 negatif.

### Round-by-Round Variance Observed

**Yüksek varyans gösteren formlar:**
- T04: r1=[K59.0, R63.5, R53, L65.9], r2=[K59.0, R53, R63.5, L65.9, R68.2], r3=[K59.0, R63.5, R53, L65.9]
  - L65.9, R63.5, R53, K59.0 — 3/3 (consensus)
  - R68.2 — 1/3 (filtered)
- T07: r1=[K31.9, R12, R11, Z72.8], r2=[K31.9, R12, R11], r3=[K29, K29.9, K31.9, R12, R11, Z56.3]
  - R12, R11, K31.9 — 3/3 (consensus)
  - Z72.8/Z56.3 — 1/3 each (filtered)
  - K29, K29.9 — 1/3 each (filtered)
- T16: r1=[I11.9, E11.9], r2=[I11.9, E11.9, I10], r3=[I11.9, E11.9, I10, R60.0]
  - I11.9, E11.9 — 3/3
  - I10 — 2/3 (kept at t=2, filtered at t=3)
  - R60.0 — 1/3

**Düşük varyans (deterministic):**
- T01, T03, T08, T10, T13, T14, T18 — neredeyse identical her round'ta

### Why Self-Consistency Did Not Help

1. **Sub-agent varyansı orta seviyede**: Çoğu form'da agent'lar tutarlı, varyans az. SC'nin sinyal-üretme avantajı sınırlı.
2. **n=20 eval seti küçük**: SC literatürde N=100+ örnekte daha net görülen kazanç.
3. **Hierarchical prompt zaten precision-bias**: Phase 1.2'den beri agent zaten "yanlış prefix yerine SKIP" gibi kuralları uyguluyor. SC'nin filtrelemesi için yer az.
4. **Z83.3, R42, R51 gibi opsiyonel kodlar**: Bazı agentlar seçti, bazıları seçmedi. threshold=2 ile bu kodlardan bazıları gold'da olmasına rağmen filtrelendi.
5. **threshold=3 çok katı**: True positive recall 7.5 puan düştü.

## Phase 3.1 Kabul Durumu

❌ **REDDEDİLDİ** — kabul kriteri "F1 ≥ önceki phase + regresyon yok" sağlanmadı:
- ICD exact macro: -0.0216 (regresyon)
- ICD prefix3 macro: -0.0050
- SUT marjinal değişim yok

## Öğrenilen Dersler

1. **Self-consistency for medical IE**: Literatürde tipik kazanç +1-3 F1 puan, ama bizde negatif. Görev/eval kombinasyonu SC'ye uygun değil.
2. **Threshold tuning**: t=2 → recall tutuyor ama precision düşüyor (?); t=3 → precision tutuyor ama recall çok düşüyor
3. **Cumulative compounding**: Phase 1.x + 2.x retrieval+prompt iyileştirmeleri zaten precision-yüksek çalışıyor. SC için "düzeltilebilecek" çok az hata kaldı.
4. **N=20 too small for SC**: Eval setini büyütmek (N=100+) Phase 5.x'te değerlendirilebilir.

## Karar

**Phase 3.1 reverted.** Kod tabanında kalıyor (`aggregate_self_consistency.py`) ama production pipeline'da kullanılmıyor.

**Cumulative best = Phase 2.3** (synonym expansion).

## Sonraki Adım

**Phase 3.2** — Constitutional prompt rules. T06/T17 specificity overshoot fix etmek için prompt'a daha katı .9-prefer kuralı eklenebilir.

Veya **Phase 3.3** — 3-class output format (REQUEST/PAST/HYPOTHETICAL calibration).

Veya **Phase 5.1** — LLM-as-Judge framework (token-F1 yerine semantic match).

## Çıktı Lokasyonları
- Round 2 outputs: `data/subagent_outputs_synonym_r2/` (40 dosya)
- Round 3 outputs: `data/subagent_outputs_synonym_r3/` (40 dosya)
- Consensus t=2: `data/subagent_outputs_sc_t2/` (40 dosya)
- Consensus t=3: `data/subagent_outputs_sc_t3/` (40 dosya)
- Scores: `data/scores_phase3.1_t2_vs_synonym.json`, `data/scores_phase3.1_t3_vs_synonym.json`, `data/scores_phase3.1_t2_vs_baseline.json`

## Pipeline State After Phase 3.1

```
Cumulative best STILL = Phase 2.3 (HyDE + Hierarchical + BM25 + RRF + Synonym Expansion)
- Phase 3.1 self-consistency: tested, reverted
- Single-round outputs (Phase 2.3) outperform 3-round consensus
```
