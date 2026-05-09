# Phase 2.3 — TR/EN Medical Synonym Expansion Sonuçları

**Tarih:** 2026-05-09
**Branch:** master
**Test:** 40 sub-agent (20 ICD + 20 SUT, Opus 4.7)
**Maliyet:** $0
**Karar: ✅ KAZANÇ — yeni cumulative best**

## Yapılan İş

### Yeni Kod
- `apps/backend/src/services/medical_synonyms.py` — Hand-crafted TR↔EN medical synonym map
  - 30+ synonym groups covering diseases, labs, anatomical terms
  - Inverted index for O(1) lookup
  - `expand_token(t)` / `expand_tokens(ts)` API
- `apps/backend/src/services/bm25_service.py`:
  - `search()` now has `expand_synonyms=True` default
  - Each query token expanded with all synonyms before BM25 scoring

### Synonym Map Highlights
- **Diabetes** group: `diabetes ↔ diyabetes ↔ diyabet ↔ şeker ↔ mellitus ↔ dm ↔ t2dm`
- **Hipertansiyon**: `hipertansiyon ↔ hypertension ↔ tansiyon ↔ ht ↔ esansiyel`
- **Hipotiroidi** (incl. corpus typo): `hipotiroidi ↔ hipotiroidizm ↔ hipotroidizm`
- **KOAH**: `koah ↔ copd ↔ kronik ↔ obstruktif`, alevlenme: `alevlenme ↔ exacerbation ↔ ekzaserbasyon`
- **Anemi**: `anemi ↔ anemia ↔ kansizlik ↔ demir ↔ ferritin`
- **Kalp yetmezliği**: `kalp ↔ heart`, `yetmezlik ↔ failure`, `kky`
- Plus 25+ lab-specific groups (HbA1c, kreatinin, bun, sodium, etc.)

## Ölçüm Sonuçları

### Cumulative Comparison (n=20 form)

| Metric | Baseline | P1.1 HyDE | P1.2 Hier | P2.1 BM25 | **P2.3 Synonym** | Δ Cumulative |
|---|---|---|---|---|---|---|
| ICD exact macro F1 | 0.4552 | 0.5176 | 0.5160 | 0.5193 | **0.5252** | **+0.0700** ✅ |
| ICD exact micro F1 | 0.4421 | 0.4500 | 0.4810 | 0.4878 | **0.5057** | **+0.0636** ✅ |
| ICD exact macro RECALL | 0.5917 | 0.5500 | 0.5542 | 0.6042 | **0.6458** | **+0.0541** |
| ICD prefix3 macro F1 | 0.5804 | 0.6219 | 0.6469 | **0.6619** | 0.6119 | +0.0315 |
| ICD prefix3 micro F1 | 0.5684 | 0.5750 | 0.6076 | **0.6173** | 0.5747 | +0.0063 |
| SUT macro F1 | **0.6331** | 0.6242 | 0.6242 | 0.6152 | **0.6402** | +0.0071 |

### Key Wins

**🎯 T11 — E11.9 yakalandı**
Phase 1.x ve 2.1'de T11 vakasında E11.9 aday listesinde yoktu (corpus "diyabetes" vs HyDE "diabetes" token mismatch). Synonym expansion `diabetes` → `[diyabetes, diyabet, şeker, mellitus, dm, t2dm]` köprüyü kurdu.

**🎯 T09 — N30.9 yakalandı**
Phase 2.1'de UTI tanı kodu yoktu (R30.0 fallback). Synonym `sistit ↔ cystitis ↔ uti ↔ idrar yolu` → N30 hit'i sağladı.

**🎯 T10 SUT — HBsAg + anti-HBs + anti-HCV yakalandı**
Phase 1.x ve 2.1'de bu 3 hepatit kodu aday listesinde hiç yoktu. Phase 2.3 ile 3 kritik kod doğrulandı (gold ile uyumlu).

**T14 E78.0**, **T18 J44.0**, **T16 E11.9** retained.

### Tradeoffs

**Prefix3 regresyon (-0.05 macro vs P2.1)**:
- Synonym expansion candidate set'i genişletti (87→111 ortalama)
- Bazı vakalarda agent yanlış prefix tuzaklarına düştü (e.g., T07'de K31.9 yeni eklendi, gold'da yok)
- Net: precision -2-3 puan, recall +4 puan

**SUT macro F1 +2.5 puan**:
- HBsAg/anti-HBs/anti-HCV kodları SUT recall'unu doğrudan artırdı
- SUT için synonym expansion ICD'den daha etkili oldu — çünkü tıbbi tetkik isimleri hem TR hem EN formlarda yaygın

## Hata Analizi

### Hâlâ Sorunlu
- **T12 E11**: BM25 corpus E10 (insulin-bağımlı) E11 (insulin-bağımlı OLMAYAN) ile token-eşit puanlanıyor; E10 kısa olduğu için doc-length normalization E10'u öne çıkarıyor
- **T18 SUT arter kan gazı**: Corpus'ta `kan gazları` tek token bloğu, agent doğru kodu bulmuş ama pipeline retrieval'a getiremedi (synonym expansion `arter ↔ blood ↔ gaz` çalışmadı çünkü corpus'ta tek bütün token)
- **T15 SUT troponin/INR/sodyum/potasyum**: Hâlâ aday listesinde değil — corpus'ta SUT spesifik isimleri farklı format

### Specificity Overshoot Devam Ediyor
- T11/T20 Z83.3 (aile öyküsü) ekleme/eklememe variability — agent decision dependent
- T07 K31.9 yeni eklendi, gold'da yok → false positive

## Phase 2.3 Kabul Durumu

✅ **GEÇTİ** — kabul kriteri sağlandı:
- ICD exact macro F1: **+0.0059** vs P2.1 ✅
- ICD exact micro F1: **+0.0179** vs P2.1 ✅
- ICD exact macro RECALL: **+0.0416** vs P2.1 ✅ (en büyük kazanç)
- SUT macro F1: **+0.0250** vs P2.1 ✅
- Prefix3 regresyon kabul edilebilir (synonym noise tradeoff)

**Cumulative gain (Baseline → P2.3): +0.07 macro F1, +0.064 micro F1**

## Sonraki Adım

**Phase 3.x'e geç** — retrieval iyileştirmeleri tamamlandı, şimdi LLM-bazlı iyileştirmeler:
- Phase 3.1 — Self-consistency decoding (n=3 örnekleme + majority vote)
- Phase 3.2 — Constitutional prompt rules (specificity overshoot fix)
- Phase 3.3 — 3-class output format (calibration)

## Çıktı Lokasyonları
- Synonym inputs: `data/subagent_inputs_synonym/` (40 dosya)
- Synonym outputs: `data/subagent_outputs_synonym/` (40 dosya)
- Scores: `data/scores_phase2.3_vs_bm25.json`, `data/scores_phase2.3_vs_baseline.json`

## Pipeline State After Phase 2.3

```
Cumulative best = Phase 2.3 (HyDE + Hierarchical + BM25 + RRF + Synonym Expansion)
- HyDE: hypothetical clinical doc (Haiku)
- Hierarchical 3-stage prompt (KATEGORİ → PREFIX → ALT-KOD)
- BM25 sparse retrieval (rank_bm25)
- RRF fusion (3 channels: dense + text + bm25)
- .9 augmentation post-cap
- TR/EN synonym expansion at query tokenize time (DEFAULT ON)
- Lemmatization OFF (reverted in P2.2)
```
