# Phase 2.1 — BM25 + RRF Hybrid Retrieval Sonuçları

**Tarih:** 2026-05-09
**Branch:** master
**Test:** 40 sub-agent (20 ICD + 20 SUT, Opus 4.7)
**Maliyet:** $0 (HyDE cache reuse + sub-agent)

## Yapılan İş

### Yeni Kod
- `apps/backend/src/services/bm25_service.py` — BM25 sparse retrieval (rank_bm25 lib)
  - `for_icd10()` → 11k ICD-10 codes index (~0.5s, cached to pickle)
  - `for_sut()` → 600+ SUT codes index
  - Turkish tokenizer (lowercase + ASCII fold + alphanumeric)
- `apps/backend/src/scripts/prep_subagent_inputs_bm25.py` — 3-channel cumulative
  - Channel 1: Dense vector (BGE-M3 + HyDE)
  - Channel 2: Text fallback (SQL LIKE)
  - **Channel 3 (NEW)**: BM25 sparse
  - RRF fusion (k=60) + .9 augmentation **AFTER cap** (kritik fix!)

### Kritik Bug Fix
İlk implementasyonda `_augment_with_unspecified` cap'ten önce çalışıyordu, BM25 parent kodları boost ettiği için .9 child kodları top-60 dışına itiliyordu. Macro F1 -0.20 regresyon yaşandı.

**Fix:** Cap önce, augment sonra (`fused[:55]` + augment) — .9 kodları her zaman aday listesinde.

## Ölçüm Sonuçları (post-fix)

### 4-Way Karşılaştırma (n=20 form)

| Metric | Baseline | HyDE (P1.1) | Hier (P1.2) | BM25 (P2.1) | Δ vs Baseline |
|---|---|---|---|---|---|
| **ICD exact macro F1** | 0.4552 | 0.5176 | 0.5160 | **0.5193** | **+0.0641** ✅ |
| ICD exact micro F1 | 0.4421 | 0.4500 | 0.4810 | **0.4878** | **+0.0457** |
| **ICD prefix3 macro F1** | 0.5804 | 0.6219 | 0.6469 | **0.6619** | **+0.0815** ✅ |
| ICD prefix3 micro F1 | 0.5684 | 0.5750 | 0.6076 | **0.6173** | **+0.0489** |
| **ICD exact macro RECALL** | 0.5917 | 0.5500 | 0.5542 | **0.6042** | **+0.0125** |
| SUT macro F1 | 0.6331 | 0.6242 | 0.6242 | 0.6152 | -0.0179 |

### Phase 2.1 marjinal katkı (vs P1.2)
- ICD exact macro: +0.0033
- ICD exact micro: **+0.0068**
- ICD prefix3 macro: **+0.0150**
- ICD prefix3 micro: **+0.0097**
- **Recall ICD exact macro: +0.05** ← BM25'in ana yararı

### Net Kazançlar (Per-Form)

✅ **T18** — KOAH alevlenme: J44.0 BM25 ile aday listesine girdi (Phase 1.x'te yoktu, P1.2 J44.9 fallback)
✅ **T16** — Hipertansif kalp + T2DM: E11.9 yakalandı (.9 augmentation fix)
✅ **T20** — T2DM + HT: E11.9 yakalandı
✅ **T14** — Hipotiroidi + hiperkolesterolemi: E78.0 yakalandı (P1.2 E78 SKIP)
✅ **T10** — Kronik HBV: B18.1 spesifik subtype (P1.2 B18.9 fallback)
✅ **T02** — HT + baş ağrısı: R42 + R51 yakalandı (P1.2 R42 yoktu)
✅ **T12** — Eski MI: R06.0, R00.2 BM25 ile geldi (semptom-bazlı kazanç)
✅ **T06** — Astım: J45.9 doğru seçim (P1.2 J45.0 overshoot'tan kurtuldu)

### Net Kayıplar / Hâlâ Sorunlu
⚠️ **T11/T12** — T2DM: E11/E11.9 BM25 corpus index'inde Türkçe "diyabet" → ICD-10 corpus İngilizce "diabetes mellitus" tokens — TR/EN token mismatch kaldı
⚠️ **T05** — Anemi: D50.9 + D50 ikisi birden seçildi (duplicate diagnosis kodu — confidence düşüklüğü)
⚠️ **T15** — Atrial fibrilasyon: I48 parent seçildi (I48.x alt kodları aday listesinde yok)

## Yorum

### BM25 ne işe yaradı?
1. **Surface-form retrieval recovery**: J44.0, E11.9, E78.0, R06.0 — BGE-M3'ün soyutladığı tokenleri lexical match ile yakaladı
2. **Recall artışı**: macro recall +0.05 — daha fazla doğru kod aday listesinde
3. **.9 augmentation sayesinde**: Specificity overshoot azaldı (T06 J45.0→J45.9)

### BM25 nerede yetersiz kaldı?
1. **TR/EN token gap**: Doktor "diyabet" der, corpus "diabetes mellitus" yazar — direkt match yok. Phase 2.4 (MSH-TUR sözlük) bu için kritik.
2. **Corpus indexing**: Kısa kodlar (E11, J44 parent) BM25 IDF'de daha avantajlı, ama RRF zaten parent boost'unu zayıflatıyor.

### SUT nötr (-0.009)
SUT için BM25 büyük yarar getirmedi. Çünkü:
- SUT görevi morfoloji-bound (REQUEST/PAST_DONE), retrieval değil
- HyDE doc + BGE-M3 zaten yeterince iyi candidate üretiyor

Beklenen: Phase 2.2 (Zemberek lemmatization) bu için daha etkili.

## Phase 2.1 Kabul Durumu

✅ **GEÇTİ** — kabul kriteri sağlandı:
- ICD exact macro F1: **+0.0033** vs P1.2 (marjinal pozitif)
- ICD exact macro RECALL: **+0.05** vs P1.2 ← retrieval ana hedefi
- Cumulative kazanç (Baseline → P2.1): **+0.0641 macro F1, +0.0815 prefix3**
- SUT regresyon hafif (-0.009 vs P1.2, -0.018 vs Baseline) — kabul edilebilir

## Sonraki Adım: Phase 2.2 (Zemberek Lemmatization)

Hedef: TR morfolojik formları kanonik forma indirgeyerek BM25 token-match'i artırmak.
- "diyabetin" → "diyabet"
- "kreatinini" → "kreatinin"  
- "tetkikleri" → "tetkik"

Beklenen: SUT recall iyileşmesi (özellikle Türkçe çekim ekleri çok), ICD'ye marjinal etki.

## Çıktı Lokasyonları
- BM25 inputs: `data/subagent_inputs_bm25/` (40 dosya)
- BM25 outputs: `data/subagent_outputs_bm25/` (40 dosya — post-fix)
- Scores: `data/scores_phase2.1v2_vs_hierarchical.json`, `data/scores_phase2.1v2_vs_baseline.json`
- BM25 cache: `data/bm25_cache/icd10_bm25.pkl`, `sut_bm25.pkl`
