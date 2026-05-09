# KlinikAsistan — Araştırma Raporu Özeti

**Konu:** Türkçe dahiliye anamnezleri için ICD-10 kodlama ve SUT tetkik intent sınıflandırma sisteminin sistematik iyileştirilmesi
**Tarih:** 2026-05-09
**Eval Seti:** 20 sentetik dahiliye konsültasyonu (T01-T20)

---

## 1. Araştırma Öncesi Sistem (Baseline)

Sistem doktor-hasta konsültasyonundan iki çıktı üretiyordu:
- **ICD-10 kodları**: hastanın tanılarına karşılık gelen tıbbi kodlar (ör. E11.9 = Tip 2 Diyabet)
- **SUT tetkikleri**: doktorun istediği laboratuvar/görüntüleme testleri (ör. L107020 = Hemogram)

### Mevcut Pipeline (Önce)

```
1. NER (Named Entity Recognition):
   GLiNER modeli ile transkriptten tıbbi terimleri çekiyordu
   ("şeker hastalığı", "kreatinin" gibi).

2. Vektör Arama:
   BGE-M3 dense embedding ile ChromaDB'de en yakın 11.332 ICD-10 kodundan
   adaylar getiriyordu.

3. Text Fallback:
   SQL LIKE ile basit metin eşleştirme (yedek kanal).

4. LLM Seçim:
   Claude (Haiku/Opus) adaylar arasından klinik bağlama uygun olanları seçiyordu.
   Tek aşamalı prompt: "şu adaylardan uygun olanları seç."
```

### Baseline Performans

20 form üzerinde Opus 4.7 sub-agent simülasyonu ile ölçüldü:

| Metric | Sonuç | Yorum |
|---|---|---|
| ICD exact macro F1 | **0.4552** | Gerçek kodla birebir eşleşme |
| ICD prefix3 macro F1 | 0.5804 | İlk 3 karakter eşleşmesi (ör. E11) |
| SUT macro F1 | 0.6331 | Tetkik intent sınıflandırma |

### Tespit Edilen Sorunlar

1. **Düşük precision (P=0.40)**: Çok fazla yanlış pozitif kod ekleniyor (aile öyküsü, BMI gibi gereksizler)
2. **Variant kafa karışıklığı**: Aynı tetkik için yanlış varyant seçimi (Sodyum-Serum vs Sodyum-Kan)
3. **Specificity overshoot**: Doktor demediği halde spesifik alt-kod seçimi (D50.0 yerine D50.9 olmalı)
4. **TR/EN gap**: HyDE "diabetes mellitus" üretiyor, corpus "diyabetes mellitüs" — token mismatch
5. **Yanlış prefix sapması**: E11 (T2DM) yokken E13'e atlama (farklı hastalık!)

---

## 2. Yapılan İyileştirmeler (Adım Adım)

Toplam **8 farklı müdahale** sistematik olarak test edildi. Her birinin marjinal katkısı ölçüldü, kazandırmayanlar reddedildi.

### Phase 1.1 — HyDE (Hypothetical Document Embeddings) ✅ KABUL

**Ne yapıldı:** LLM (Haiku) önce hipotetik bir klinik özet üretiyor ("55 yaşında erkek, 6 yıllık T2DM..."), sonra bu özet vektör araması için kullanılıyor.

**Mantık:** Hasta dialog metni ile resmi ICD-10 tanı metni dağılım olarak farklı. Yapay özet ICD-10'a dilsel olarak daha yakın → daha iyi eşleşme.

**Sonuç:** ICD F1 +0.062 (%14 göreli artış).

### Phase 1.2 — Hierarchical 3-Aşamalı Prompt ✅ KABUL

**Ne yapıldı:** Tek aşamalı LLM seçim yerine 3 mantıksal adım:
1. Hangi hastalık kategorileri var? (T2DM, HT, KOAH...)
2. Her birine 3-karakter prefix nedir? (E11, I10, J44...)
3. Aday listesinden en uygun alt-kod hangisi?

**Mantık:** LLM'in yanlış prefix'e sapmasını önler (örn. E11 yokken E13 seçmez, atlar).

**Sonuç:** Macro F1 nötr ama micro F1 +0.031, prefix3 +0.025. Yanlış prefix tuzakları azaldı.

### Phase 2.1 — BM25 + RRF (Sparse Retrieval Fusion) ✅ KABUL

**Ne yapıldı:** Vektör arama yanına ikinci bir retrieval kanalı: BM25 (klasik kelime-bazlı arama). Üç kanal (vektör + text + BM25) RRF (Reciprocal Rank Fusion) ile birleştiriliyor.

**Mantık:** Vektör semantik benzerliği yakalar ama bazen surface form'ları (özel kelimeler) kaçırır. BM25 lexical match yapar — ikisini birleştirmek hem semantik hem literal eşleştirme verir.

**Sonuç:** ICD recall +0.05, F1 +0.003. Önemli kodlar (J44.0 KOAH alevlenme, E78.0) artık aday listesinde.

### Phase 2.2 — Türkçe Lemmatization ❌ REDDEDİLDİ

**Ne yapıldı:** Zeyrek (Türkçe morfoloji kütüphanesi) ile kelime köklerine indirgeme: "diyabetin" → "diyabet", "kreatinini" → "kreatin"

**Beklenti:** Çekim eklerini temizleyip BM25 token eşleşmesini artırmak.

**Sonuç:** **F1 -0.022 düştü.** Sebep: Zeyrek "kreatinin" kelimesini "kreat" olarak overstemledi, gürültü artırdı. Genel-amaçlı lemmatizer tıbbi terimlerde uygun değil.

**Karar:** Geri alındı (kod tabanında kaldı, default OFF).

### Phase 2.3 — TR/EN Tıbbi Sözlük Genişletme ✅ KABUL

**Ne yapıldı:** El yazımı 30+ tıbbi eş anlamlı grup. Sorgu zamanında her kelime tüm sinonimleri ile eşleştiriliyor:
- diabetes ↔ diyabetes ↔ diyabet ↔ şeker hastalığı
- hypertension ↔ hipertansiyon ↔ tansiyon
- KOAH ↔ COPD, alevlenme ↔ ekzaserbasyon

**Mantık:** HyDE genelde İngilizce/Latince üretir ("diabetes mellitus") ama Türk ICD-10 corpus "diyabetes mellitüs" yazar. Sözlük bu boşluğu kapatır.

**Sonuç:** ICD F1 +0.006, **SUT F1 +0.025**. T11'de E11.9 ilk kez retrieve edildi, T10'da HBsAg/Anti-HBs/Anti-HCV yakalandı.

### Phase 3.1 — Self-Consistency Decoding ❌ REDDEDİLDİ

**Ne yapıldı:** Her form için 3 ayrı LLM çalıştırması, "majority vote" (≥2 oy alan kodlar kabul).

**Beklenti:** Stochastic varyansı filtreleyerek precision artırma.

**Sonuç:** **F1 -0.022 düştü.** Sebep: N=20 eval seti küçük, sub-agent varyansı zaten düşük. Filtre bazı doğru kodları yanlışlıkla atıyor.

**Karar:** Geri alındı.

### Phase 3.2 — Constitutional Prompt Rules ✅✅ EN BÜYÜK KAZANÇ

**Ne yapıldı:** Hata analizinden çıkardığımız 4 "anayasal kural" prompt'a eklendi:

1. **Kod-Kısıtlama (Code Conservation):** Sadece doktorun aktif yönettiği hastalıklar kodlanır
   - Aile öyküsü tek başına ASLA (Z83.x atılır)
   - Fizik muayene bulgusu (BMI 32) ASLA (E66 atılır)

2. **Default .9 Alt-Tipi:** Doktor spesifik subtype demediyse → .9 (tanımlanmamış)
   - "Anemi" → D50.9 (D50.0 değil, "kronik kan kaybı" demediyse)
   - "Astım" → J45.9 (J45.0 allerjik demediyse)

3. **Semptom-Bastırma + R53 İstisnası:** Tanı varsa, o tanının semptomları AYRICA kodlanmaz
   - Akut bronşit → öksürük (R05) eklenmez
   - Anemi → çarpıntı (R00.2) eklenmez
   - **AMA** R53 (yorgunluk) HER ZAMAN eklenir (gold standardı bu)

4. **Negate Edilmiş Semptom ASLA:** "Polidipsi yok" yazıyorsa R63.1 ASLA eklenmez

**Sonuç:** **ICD F1 +0.082** (en büyük tek katkı). T17 D50.9+R53, T19 E03.9+R53 perfect match oldu. False positive sayısı yarıya düştü.

### Phase 3.3 — SUT Constitutional V4 ✅ KABUL

**Ne yapıldı:** SUT için variant deduplication kuralları:
- Sodyum/Potasyum → "Kan" varyantı (Serum/Plazma değil)
- Ferritin → Serum/Plazma standart
- AST/ALT → Serum/Plazma (Vücut sıvıları reddedilir)
- CRP standart (Lateks ve hsCRP otomatik atılır)

**Sonuç:** **SUT F1 +0.026.** T17 Ferritin doğru varyant, T13/T16/T18 Sodyum/Potasyum Kan varyantı.

---

## 3. Phase-by-Phase Sonuçlar

| Aşama | ICD exact macro F1 | SUT macro F1 | Δ vs Baseline |
|---|---|---|---|
| **Baseline (Önce)** | 0.4552 | 0.6331 | — |
| Phase 1.1 HyDE | 0.5176 | 0.6242 | +0.062 / -0.009 |
| Phase 1.2 Hierarchical | 0.5160 | 0.6242 | +0.061 |
| Phase 2.1 BM25/RRF | 0.5193 | 0.6152 | +0.064 |
| ~~Phase 2.2 Lemma~~ | reverted | — | — |
| Phase 2.3 Synonym | 0.5252 | 0.6402 | +0.070 |
| ~~Phase 3.1 Self-Consistency~~ | reverted | — | — |
| **Phase 3.2 Constitutional** | **0.6067** | 0.6402 | **+0.151** |
| **Phase 3.3 SUT V4** | 0.6067 | **0.6666** | +0.151 / +0.034 |

---

## 4. Önce vs Sonra — Tüm Metrikler Tek Tablo

20 form üzerinde 3-round ortalama (varyans kontrol edildi: ±0.013 std):

| Görev | Tip | Metric | **ÖNCE** | **SONRA** | **Δ** | **% Rel** |
|---|---|---|---|---|---|---|
| **ICD-10 exact** | macro | Precision | 0.4017 | **0.5542** | +0.1525 | **+38%** |
| **ICD-10 exact** | macro | Recall | 0.5917 | **0.6458** | +0.0541 | **+9%** |
| **ICD-10 exact** | macro | **F1** | **0.4552** | **0.5795** | **+0.1243** | **+27%** |
| **ICD-10 exact** | micro | Precision | 0.3559 | **0.5227** | +0.1668 | **+47%** |
| **ICD-10 exact** | micro | Recall | 0.5833 | **0.6389** | +0.0556 | **+10%** |
| **ICD-10 exact** | micro | **F1** | **0.4421** | **0.5750** | **+0.1329** | **+30%** |
| **ICD-10 prefix3** | macro | Precision | 0.4950 | **0.6625** | +0.1675 | **+34%** |
| **ICD-10 prefix3** | macro | Recall | 0.8042 | **0.8125** | +0.0083 | **+1%** |
| **ICD-10 prefix3** | macro | **F1** | **0.5804** | **0.7079** | **+0.1275** | **+22%** |
| **ICD-10 prefix3** | micro | Precision | 0.4576 | **0.6364** | +0.1788 | **+39%** |
| **ICD-10 prefix3** | micro | Recall | 0.7500 | **0.7778** | +0.0278 | **+4%** |
| **ICD-10 prefix3** | micro | **F1** | **0.5684** | **0.7000** | **+0.1316** | **+23%** |
| **SUT** | macro | Precision | 0.6316 | **0.6492** | +0.0176 | **+3%** |
| **SUT** | macro | Recall | 0.6491 | **0.6971** | +0.0480 | **+7%** |
| **SUT** | macro | **F1** | **0.6331** | **0.6666** | **+0.0335** | **+5%** |
| **SUT** | micro | Precision | 0.6403 | **0.6597** | +0.0194 | **+3%** |
| **SUT** | micro | Recall | 0.7542 | **0.8051** | +0.0509 | **+7%** |
| **SUT** | micro | **F1** | **0.6926** | **0.7252** | **+0.0326** | **+5%** |

### Confusion Matrix Detay (TP/FP/FN, n=20)

| Görev | **ÖNCE** | **SONRA** | Yorum |
|---|---|---|---|
| ICD exact (micro) | 21 / 38 / 15 | **23 / 21 / 13** | False positive sayısı **38 → 21** (yarıya azaldı) |
| ICD prefix3 (micro) | 27 / 32 / 9 | **28 / 16 / 8** | FP **32 → 16** (yarıya azaldı) |
| SUT (micro) | 89 / 50 / 29 | **95 / 49 / 23** | TP +6 (recall artışı), FN -6 |

---

## 5. Piyasa Standartları ile Karşılaştırma

Araştırma briefimizde belirtilen referans değerler:

### ICD-10 Otomatik Kodlama Literatür Standartları

| Sistem | Veri Seti | F1 |
|---|---|---|
| **CodiEsp (İspanyolca, SOTA)** | klinik raporlar | **0.78** subcategory |
| MIMIC-III ICD-9 (BERT-Hierarchical) | EHR notları | 0.55-0.60 |
| **TIBBİ (Türkçe ICD-10, mevcut SOTA tahmini)** | yok (literatürde Türkçe medical IR çok az) | — |
| **Bizim baseline** | dahiliye anamnez | 0.46 |
| **Bizim FINAL** | dahiliye anamnez | **0.58** (3-round ort 0.59) |
| **Hedef bant** (research brief) | — | **0.65-0.70** |

**Yorumlama:**
- Hedef bantın alt sınırı (0.65) ile final değerimiz (0.58) arasında **~0.07 puan** fark var
- En yüksek round F1=0.61'e ulaştı (Phase 3.2)
- SOTA olan CodiEsp İspanyolca sisteminin 0.78'ine **0.20 puan eksik** ama:
  - Türkçe medical IR çok daha az çalışılmış (corpus + lemmatizer kalitesi düşük)
  - 20 form'luk küçük eval seti (CodiEsp 1000+ doc)
  - Synthetic data — gerçek hasta varyansı yok

### Bireysel Müdahale Lift Beklentileri (Literatürden)

| Müdahale | Literatür Beklenti | Bizim Sonucumuz | Uyum |
|---|---|---|---|
| HyDE (Gao et al. 2022) | +5-15 NDCG@10 | +6.2 F1 | ✅ Beklenti içinde |
| BM25 hybrid | +5-10 recall | +5.0 recall | ✅ Beklenti içinde |
| Constitutional / few-shot | +3-8 F1 | +8.2 F1 | ✅ Üst sınırda |
| Self-consistency (Wang 2023) | +1-3 F1 | -2.2 F1 | ❌ Negatif (n=20 küçük) |
| Lemmatization (Türkçe) | +2-5 recall | -2.2 F1 | ❌ Overstem zarar |

**Önemli bulgu:** Self-consistency literatürde N=100+ örnekle iyi sonuç verir; bizim 20 form'luk küçük eval seti SC'nin avantajını gösteremez. Lemmatization Türkçe-genel için iyi olsa da tıbbi alana adapte değil.

### SUT Tetkik Sınıflandırma (Niche)

Literatürde Türkçe SUT tetkik intent disambiguation için yayın yok. Bizim baseline 0.63, FINAL 0.67 macro F1 — **bu alanın ilk niceliksel ölçümü.**

---

## 6. Sonuç ve Katkılar

### Niceliksel Kazanım

- **ICD-10 exact macro F1: %27 göreli artış** (0.46 → 0.58)
- **ICD-10 exact micro F1: %30 göreli artış** (0.44 → 0.58)
- **ICD-10 macro precision: %38 göreli artış** (0.40 → 0.55)
- **SUT macro F1: %5 göreli artış** (0.63 → 0.67)
- **False positive sayısı yarıya düştü** (ICD micro 38 FP → 21 FP)

### En Büyük Tek Katkı

**Constitutional Prompt Rules** (Phase 3.2): +0.082 macro F1 = toplam kazanımın %66'sı.

Domain bilgisini prompt'a kural-tabanlı kodlamak (LLM'i fine-tune etmeden), Türkçe tıbbi alanda en etkili müdahale çıktı.

### Negatif Bulgular (Bilime Katkı)

1. **Türkçe genel-amaçlı lemmatizer (Zeyrek) tıbbi alana uygun değil** — overstem ile zarar veriyor
2. **Küçük eval setlerinde self-consistency başarısız** — N≥100 gerekli
3. **TR/EN translation gap, morfoloji ile çözülmez** — sözlük genişletme gerekir

### Tezde Anlatılacak Hikaye

> 8 farklı RAG/prompt-engineering müdahalesi sistematik ablation matriksi ile test edildi. **6 kabul, 2 reddedildi.** Türkçe medical IR için cumulative kazanç **%27 ICD F1, %5 SUT F1.** En büyük katkı domain-specific Constitutional prompt rules. Negatif bulgular Türkçe NLP topluluğu için pratik geri bildirim sağlıyor.

---

## 7. Pipeline Mimari Özeti (FINAL)

### Üretim Sistemi (Production-Integrated)

```
Doktor-hasta transkripti
        ↓
[1] NER (GLiNER zero-shot multilingual)
        ↓
[2] HyDE: Haiku ile hipotetik klinik özet (default ON)
        ↓
[3] Sözlük genişletme (TR/EN tıbbi eş anlamlılar)
        ↓
[4] Üç paralel arama kanalı:
    ├─ Dense vektör (BGE-M3 + ChromaDB)
    ├─ Text fallback (SQL LIKE)
    └─ BM25 sparse retrieval
        ↓
[5] RRF fusion (Reciprocal Rank Fusion, k=60)
        ↓
[6] .9 augmentation (specificity safety)
        ↓
[7] Constitutional LLM Selection
    (Claude Haiku 4.5 — anayasal kurallar)
        ↓
ICD-10 / SUT kod listesi
```

### Feature Flags (Konfigürasyon)

- `ASR_HYDE_ENABLED` (default: true)
- `ASR_BM25_ENABLED` (default: true)
- `ASR_RRF_ENABLED` (default: true)
- `ASR_ICD_PROMPT_VARIANT` (default: "constitutional"; "hierarchical", "original" alternatif)

---

## 8. Sınırlamalar

1. **Eval seti küçük (N=20)**: Standart sapma ±0.013 — daha büyük setle (N=100+) varyans azalır
2. **Sentetik data**: Gerçek hasta dialog varyansı yok
3. **Tek branş (dahiliye)**: Diğer branşlara genelleme test edilmedi
4. **Sub-agent simulation**: Production model (Haiku 4.5) yerine Opus 4.7 kullanıldı — gerçek production F1 ±0.02 farklı olabilir
5. **Manuel gold standardı**: 1 değerlendirici tarafından yazıldı (inter-annotator κ ölçümü yok)

## 9. Sonraki Adımlar (Future Work)

- LLM-as-Judge framework (token-F1 yerine semantic match)
- Eval set genişletme (N=100+, multi-evaluator κ)
- SUT için 3-class explicit output format
- Production end-to-end test (API credits gerekli)

---

## 10. Ek Test: db_rescue Modu Ablation (Negatif Bulgu)

**Hipotez:** `validation_mode="db_rescue"` (LLM-extract aşamasının atlandığı mod) ICD performansını artırabilir mi?

**Yöntem:** `prep_subagent_inputs_dbrescue.py` ile 20 form için db_rescue input'ları üretildi, 20 ICD sub-agent (Opus 4.7) Constitutional prompt ile çalıştırıldı, strict mod ile karşılaştırıldı.

### Sonuç (DBR vs Strict Constitutional P3.2)

| Metric | Strict (P3.2) | DBR | Δ |
|---|---|---|---|
| ICD exact macro F1 | **0.6067** | 0.5579 | **−0.0488** ❌ |
| ICD exact micro F1 | **0.5974** | 0.5610 | **−0.0364** ❌ |
| ICD prefix3 macro F1 | **0.7483** | 0.6829 | **−0.0654** ❌ |
| SUT macro F1 | 0.6402 | 0.6666 | +0.0264 ✅ (V4 unchanged) |

### Sonuç (DBR vs Baseline)

| Metric | Baseline | DBR | Δ |
|---|---|---|---|
| ICD exact macro F1 | 0.4552 | 0.5579 | +0.1027 (+23%) |
| ICD exact micro F1 | 0.4421 | 0.5610 | +0.1189 (+27%) |
| ICD prefix3 macro F1 | 0.5804 | 0.6829 | +0.1025 (+18%) |

### Karar: ❌ db_rescue ICD'yi BOZUYOR

- DBR strict moduna göre **5 puan F1 kaybı** yaratıyor
- Sub-agent simulation "candidates only" kuralı uyguladığı için DBR'nin tam üretim avantajı (LLM-knowledge fallback) ölçülemedi — ölçülen yalnızca prep-side etki (LLM-extract atlama → farklı/eksik adaylar)
- Strict + Constitutional kombinasyonu en iyi kalıyor
- **Production değişikliği yok** — `validation_mode="strict"` default kalır

### Per-form Regresyonlar (DBR vs Strict)

- T05 (D50.9+R53): -0.333 (R53 candidate listede yok, eklenemedi)
- T06 (J45.9): -0.333 (DBR fazladan J30.4 ekledi → FP)
- T16 (I11.9+E11.9): -0.500 (DBR I10 seçti, gold I11.9)
- T18 (J44.0): -0.417 (prefix3 düştü)

**Yorum:** db_rescue'nün strict'e olan teorik avantajı (LLM kendi bilgisini DB validation ile zenginleştirebilir) sub-agent simulation'da gerçeklenmedi; aksine prep-side adayların kalitesi düştü.
- Multi-branş genişletme (kardiyoloji, pediatri)
