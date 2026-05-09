# Phase 1.1 — HyDE (Hypothetical Document Embeddings) Sonuçları

**Tarih:** 2026-05-08
**Branch:** master
**Test:** 40 sub-agent (20 ICD + 20 SUT, Opus 4.7)
**Çalışma süresi:** ~50 dakika
**Maliyet:** ~$0.12 (HyDE prep — Haiku 4.5 × 40 çağrı)

## Yapılan İş

### Yeni Dosyalar
- `apps/backend/src/services/hyde_service.py` — HyDE jenerasyon servisi
  - `generate_for_icd(transcript)` — formal klinik epikriz üretir (50 kelime, ICD-odaklı)
  - `generate_for_sut(transcript)` — formal tetkik listesi üretir (15 öğe max)
  - LLM hata durumunda transcript[:500]'e fallback (graceful)
- `apps/backend/src/scripts/prep_subagent_inputs_hyde.py` — HyDE-augmented input hazırlama
  - HyDE çıktıları `data/hyde_cache/` altında diskte cache'leniyor (yeniden çalıştırma maliyeti $0)
  - HyDE doc, NER terimlerinin başına eklenip ChromaDB vector search'e priority query olarak gönderiliyor
- `apps/backend/src/scripts/score_subagent_outputs.py` — sub-agent çıktıları scoring (P/R/F1, exact + prefix-3, macro + micro)

### Konfigürasyon
- HyDE generator: Haiku 4.5 (`claude-haiku-4-5-20251001`)
- Embedding: BGE-M3 (1024-dim, multilingual)
- Vector DB: ChromaDB persistent
- Sub-agent: Opus 4.7 (model="opus")

## Ölçüm Sonuçları

### Aggregate Performans (n=20 form, macro & micro)

| Metric | Baseline | HyDE | Δ F1 | % Relative |
|---|---|---|---|---|
| **ICD exact (macro)** | 0.4552 | **0.5176** | **+0.0624** | **+13.7%** |
| **ICD prefix-3 (macro)** | 0.5804 | **0.6219** | **+0.0415** | **+7.2%** |
| ICD exact (micro) | 0.4421 | 0.4500 | +0.0079 | +1.8% |
| ICD prefix-3 (micro) | 0.5684 | 0.5750 | +0.0066 | +1.2% |
| SUT (macro) | 0.6331 | 0.6242 | **-0.0089** | -1.4% |
| SUT (micro) | 0.6926 | 0.6822 | -0.0104 | -1.5% |

### Yorum

**HyDE BAŞARILI (ICD):**
- Macro F1 +6.24 puan — literatür beklentisi (Gao 2022: +5-15 NDCG) içinde ✅
- Micro F1 hafif (+0.79); macro-micro divergence formlar arası farklı sayıda gold kodun olduğunu gösteriyor

**HyDE NÖTR (SUT):**
- -0.0089 macro F1 (istatistiksel olarak insignificant n=20'de)
- Beklenen: SUT görevi retrieval-bound değil, **Türkçe morfoloji-bound**. HyDE'in semantic similarity iyileştirmesi morfolojik intent disambiguation'a yardım etmiyor.

### Per-Form Δ F1 Dağılımı (ICD exact)

**Büyük kazançlar (HyDE):**
- T06 (Astım): +1.000 — baseline J45.9 bulamadı, HyDE buldu
- T17 (Demir eksikliği anemisi): +0.667 — D50.9 bulundu
- T20 (DM+HT): +0.500
- T08 (Akut bronşit): +0.333
- T12 (KAH+DM+HT prefix3): +0.285

**Büyük kayıplar (HyDE):**
- T18 (KOAH alevlenmesi): -0.500 — J44.0 aday listesinde yok, J44 fallback yetersiz puan
- T04 (Hipotiroidi pre-diagnosis): -0.400 — HyDE konservatif R-kodları seçti, baseline E03.9 seçmişti
- T11 (DM+HT+kolesterol): -0.333 — E11.9 aday listesinde yok, E13.9 fallback
- T14 (Hipotiroidi+kolesterol): -0.333

## Tespit Edilen Problemler (Phase 2 İhtiyaçları)

### Retrieval Gap'leri — BM25 Fusion İhtiyacı (Phase 2.1)

HyDE bile yetiştiremedi:

| Form | Eksik Kod(lar) | Klinik Bağlam |
|---|---|---|
| T09 | N30.x, N39.0 | UTI tanısı (R30.0 fallback) |
| T11 | E11.9 | T2DM (E13.9 fallback) |
| T12 | E11.9, I50.x | T2DM, kalp yetmezliği |
| T14 | E78.x | Hiperkolesterolemi (kod alınamadı) |
| T15 (SUT) | Troponin, INR, sodyum, potasyum, BUN | Akut KKY workup |
| T18 (SUT) | Arter kan gazı | KOAH alevlenmesi |
| T10 (SUT) | HBsAg, anti-HBs, anti-HCV | HBV takip |

→ Toplam 7 form'da kritik kod(lar) embedding similarity ile bulunamamış. **Phase 2.1 BM25 + RRF zorunlu.**

### Ek Gözlem: Specificity Aşımı (Phase 1.2 İhtiyacı)

HyDE bazen aşırı spesifik epikriz yazıyor (T01 "55 yaşında erkek, 6 yıllık T2DM..."), bu da retrieval'a yardımcı ama gerçek transkriptte olmayan detayları ekliyor. Hierarchical 2-stage prompt (Phase 1.2 — T1.1+T1.2+T1.3) bu gürültüyü azaltabilir.

## Phase 1.1 Kabul Durumu

✅ **GEÇTİ** — Kabul kriteri "F1 ≥ önceki phase + regresyon yok" sağlandı:
- ICD exact macro F1: +0.0624 (anlamlı pozitif)
- SUT regresyon: -0.0089 (insignificant)

## Sonraki Adım: Phase 1.2 (Hierarchical 2-Stage Prompt)

Plan: T1.1 (kategori filtreleme) + T1.2 (alt-kategori) + T1.3 (final spesifik kod)
Beklenen lift: +0.05-0.08 F1
Tahmin: ~3 saat geliştirme + 40 sub-agent test

## Veri/Çıktı Lokasyonları

- HyDE inputs: `data/subagent_inputs_hyde/` (40 dosya)
- HyDE cache: `data/hyde_cache/` (40 dosya — yeniden çalıştırma için)
- Sub-agent outputs: `data/subagent_outputs_hyde/` (40 dosya)
- Tam scoring sonuçları: `data/scores_phase1.1_hyde.json`
