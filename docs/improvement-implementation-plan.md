# İyileştirme Uygulama Planı — ICD-10 ve SUT Pipeline

> **Kaynak:** Arkadaşımızın akademik araştırma raporu (`docs/icd-sut-pipeline-research-brief.md` → araştırmacı analizi)
> **Hedef:** ICD F1 0.442 → 0.65-0.70 bandı (CodiEsp subcategory SOTA 0.78'e yakın)
> **Strateji:** Cumulative iyileştirme + her phase'de sub-agent test ile A/B karşılaştırma

## Phase Yapısı

| Phase | Müdahale | Dependencies | Effort | Beklenen Lift |
|---|---|---|---|---|
| 1.1 | T2.1 HyDE | - | 2h | +0.06-0.12 F1 |
| 1.2 | T1.1+T1.2+T1.3 Hierarchical paket | 1.1 | 3h | +0.05-0.08 F1 |
| 2.1 | T2.2 BM25 + RRF | 1.x | 3h | +0.05-0.10 recall |
| 2.2 | T7.4 Zemberek lemmatize | 2.1 | 3h | +0.04-0.07 NER F1 |
| 2.3 | T2.4 MSH-TUR sözlük | bağımsız | 1h | +0.02-0.04 |
| 3.1 | T6.2 Self-consistency | 2.x | 2h+1h test | +0.03-0.06 F1 |
| 3.2 | T6.5 Constitutional prompt | 3.1 | 30dk | marjinal |
| 3.3 | 3-sınıflı çıktı | 3.x | 1h | calibration |
| 4.1 | T7.1 LLM-NER (opsiyonel A/B) | 3.x | 3h | +0.04-0.07 NER F1 |
| 5.1 | T4.1+T4.2 LLM-as-Judge | tüm phase'ler | 4h+2h | metrik kalitesi |
| 5.2 | Inter-annotator κ | external | dış | task floor |

## Test Methodology
- Her phase sonrası 40 sub-agent (20 ICD + 20 SUT, Opus 4.7)
- Output dizinleri: `data/subagent_outputs_<phase>/`
- Baseline: `data/subagent_outputs_baseline_v1/` (n=20, Opus 4.7)
- Cumulative ablation tablosu: her müdahalenin marjinal katkısı

## Kabul Kriterleri (Genel)
- **Phase başarılı sayılır:** F1 ≥ önceki phase + regresyon yok
- **Phase fail ise:** rollback, alternatif yaklaşım, veya skip

## Maliyetler
- Sub-agent testler: $0 (Claude Max kotası)
- HyDE API call'ları (Phase 1.1): ~$0.12/run × 5 phase = ~$0.60
- LLM-as-Judge (Phase 5.1): ~$5-10
- **TOPLAM: ~$10-15** (3 hafta için)
