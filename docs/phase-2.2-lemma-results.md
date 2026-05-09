# Phase 2.2 — Turkish Lemmatization Sonuçları (NEGATIVE / REVERTED)

**Tarih:** 2026-05-09
**Branch:** master
**Test:** 40 sub-agent (20 ICD + 20 SUT, Opus 4.7)
**Maliyet:** $0
**Karar: ❌ FAIL → Phase 2.2 revert, Phase 2.1 baseline'a dön**

## Yapılan İş

### Yeni Kod
- `apps/backend/src/services/bm25_service.py`:
  - `_lemmatize_token()` — zeyrek MorphAnalyzer wrapper
  - `_tokenize()` — lemmatize-then-fold order (Türkçe karakterler önce, fold sonra)
  - In-memory token cache + skip rules (medical codes preserved)
- `apps/backend/src/scripts/prep_subagent_inputs_bm25.py` — same script, output to `subagent_inputs_lemma/`

### Lemmatization Strategy
Pipeline order:
1. lowercase (TR chars preserved)
2. tokenize alphanumeric
3. lemmatize via zeyrek (returns canonical form)
4. ASCII-fold (TR → EN char map)

## Ölçüm Sonuçları

### 4-Way Karşılaştırma (n=20 form)

| Metric | Baseline | P1.2 Hier | P2.1 BM25 | **P2.2 Lemma** | Δ vs P2.1 |
|---|---|---|---|---|---|
| ICD exact macro F1 | 0.4552 | 0.5160 | **0.5193** | 0.4967 | **-0.0226** ⚠️ |
| ICD exact micro F1 | 0.4421 | 0.4810 | **0.4878** | 0.4706 | -0.0172 |
| ICD prefix3 macro F1 | 0.5804 | 0.6469 | **0.6619** | 0.6167 | **-0.0452** ⚠️ |
| ICD prefix3 micro F1 | 0.5684 | 0.6076 | **0.6173** | 0.5647 | **-0.0526** ⚠️ |
| SUT macro F1 | 0.6331 | 0.6242 | 0.6152 | 0.6157 | +0.0005 |

**Phase 2.2 vs P2.1: Net regresyon her ICD metriğinde.**

## Hata Analizi

### Neden Lemmatization Zarar Verdi?

1. **Zeyrek overstem (kreatinin → kreat)**
   - "kreatinin" tokeni "kreat" stem'ine indirgeniyor
   - "kreat" gürültü tokenleri ile (creatinine analogs, creatine kinase) çakışıyor
   - BM25 IDF zayıflıyor, false positive oranı artıyor

2. **Corpus indexing aday sıralamasını bozdu**
   - T01: Z83.3 (DM aile öyküsü) aday listesinde olduğu halde agent skipledi (lemmatized form mismatch?)
   - T11/T15: Sodyum/Potasyum P2.1'de vardı, P2.2'de yok
   - T15: Kreatinin gold'da var, agent skipledi (overstem effect)

3. **TR/EN translation gap kapanmadı**
   - "diabetes" (HyDE) ↔ "diyabetes" (corpus): zeyrek bu farkı kapatmıyor
   - T11/T12'de E11 hâlâ retrieve edilmiyor

### Marjinal Kazanç (T16)
- T16 Üre (L107420) yakalandı (P2.1'de yoktu)
- Lemmatization "üre", "üresinde" gibi formları normalize etti
- Tek kazanç bu, geri kalanı zarar

## Karar ve Geri Dönüş

```python
# apps/backend/src/services/bm25_service.py
def _tokenize(text: str, lemmatize: bool = False) -> list[str]:  # Default OFF
```

`_tokenize()` default'u `lemmatize=False` yapıldı — lemmatization codebase'de kalıyor (opsiyonel) ama kullanılmıyor.

## Phase 2.2 Kabul Durumu

❌ **REDDEDİLDİ** — kabul kriteri "F1 ≥ önceki phase + regresyon yok" sağlanmadı:
- ICD exact macro: -0.0226 (regresyon)
- ICD prefix3 macro: -0.0452 (büyük regresyon)
- SUT macro: marjinal değişim (+0.0005, anlamsız)

## Öğrenilen Dersler

1. **Genel-amaçlı lemmatizer ≠ medical lemmatizer**: Zeyrek/Zemberek tıbbi terimleri yanlış stem'liyor (kreatinin/kreatine ayrımı yok)
2. **Token rare-form preservation > stemming**: "diyabet" tokenı corpus'ta zaten "diyabetes" formuyla bulunduğunda BM25 alternatif token-eşleşme bekliyor
3. **TR/EN translation problemi morfoloji ile çözülmez**: Phase 2.3 (MSH-TUR sözlük) gerekli

## Sonraki Adım

**Phase 2.2'yi atla, Phase 2.3'e geç:** MSH-TUR Türkçe medical sözlük kullanarak query/corpus expansion ile TR/EN gap kapatılır.

Alternatif: Prompt-bazlı iyileştirmeler (Phase 3.1 self-consistency) — retrieval bottleneck'i değil LLM kararlarını hedef alıyor.

## Çıktı Lokasyonları
- Lemma inputs: `data/subagent_inputs_lemma/` (40 dosya)
- Lemma outputs: `data/subagent_outputs_lemma/` (40 dosya)
- Scores: `data/scores_phase2.2_vs_bm25.json`, `data/scores_phase2.2_vs_baseline.json`
- BM25 lemma cache: `data/bm25_cache/icd10_bm25_lemma.pkl`, `sut_bm25_lemma.pkl`

## Pipeline State After Phase 2.2

```
Cumulative best = Phase 2.1 (BM25 + RRF + .9 augmentation)
- HyDE retained
- Hierarchical 3-stage prompt retained
- BM25 hybrid retrieval retained
- Lemmatization DEFAULT OFF (code preserved as opt-in)
```
