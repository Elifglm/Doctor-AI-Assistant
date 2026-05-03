# Dahiliye Real-Anamnesis RAG — Plan ve Çalışma Kaydı

**Branch:** `feature/dahiliye-real-anamnesis-rag`
**Başlangıç:** 2026-05-03
**Hedef:** 38,222 gerçek dahiliye anamnez raporundan BGE-M3 + multilingual-E5-base ile RAG kurmak; doktor konuşurken (ASR transkript) benzer geçmiş anamnezleri retrieve edip LLM (Claude Haiku 4.5) few-shot örnekleri ile yapılandırılmış rapor üretmek.

> **Not:** Mevcut sentetik RAG (`anamnez_core_scenarios.json` + `generate_variations.py` + `medical_knowledge` collection) dokunulmaz. Sentetik vs gerçek karşılaştırma final raporda yer alacak.

---

## 1. Veri kaynağı

| Kaynak | Konum | Boyut |
|---|---|---|
| `IcAnemnez.xlsx` | `data/Anemnez_tetkik/` | 38,222 satır × 48 kolon |
| `Tetkik.xlsx` | `data/Anemnez_tetkik/` | 51,399 satır × 7 kolon |
| `data/anamnez.db` (SQLite) | Excel'lerden import edildi (`scripts/import_anamnez.py`) | 16 MB, 2 tablo + indeks |
| `ic_anamnez` (HAM) | SQLite tablo | 38,222 satır, dokunulmaz |
| `tetkik` (HAM) | SQLite tablo | 51,399 satır, dokunulmaz |

**Kritik istatistikler:**
- 38,222 raporun yalnızca **10,514**'ünde tetkik var (FORM_ID join). Tetkik var/yok metadata, filtre kriteri **değil**.
- `ÖN TANI` kolonu 1/38,222 dolu → ICD ground truth yok.
- Memory: 500 satır PHI taraması, sıfır hit (TC/telefon/email/isim).
- Top-15 tetkik: HEMOGRAM (7,162), VITAMIN B12 (3,646), TSH (3,592), AKŞ (3,204), FERRITIN (2,655)…

---

## 2. Faz 0 kararları (özet)

1. Sentetik RAG kenarda durur, dokunmuyoruz. ✓
2. Embedding ablation: **BGE-M3 (BAAI/bge-m3) + multilingual-E5-base (intfloat/multilingual-e5-base)**.
3. Ablation stratejisi: **B yolu** — önce E5-base'de filtre ablation (4 config), kazanan filtreyle BGE-M3 + E5-base 2-model karşılaştırması. Toplam **5 embed pass**.
4. Filtreli her veri ayrı SQLite tablosu, ham veri korunur.
5. Filtre **anamnez kalitesine** bakar (yakınma+öykü+muayene); kalan iyi anamnezlerin tetkikleri **opsiyonel metadata**.
6. Ablation kapsamı: **baseline + 3 ablation** (4 config toplam).
7. Eval seti hold-out yaklaşımı: filtreli korpustan **100 random satır** ayır (random_seed=42), embed'e dahil etme. Mini panel: 100 holistic + 20 deep-dive Likert. Sen + LLM-judge (Claude Haiku) + RAGAS otomatik metrikler. Cohen's κ ile uyuşma.
8. Hekim paneli future work; bu sprint'te yok.

---

## 3. Mimari karar (Faz 2)

**Alternatif B — Paralel `AnamnezRAGService`** seçildi.

- Yeni servis sınıfı: `apps/backend/src/services/anamnez_rag_service.py`
- ChromaDB path: `data/anamnez_chroma_<profile>_<filter>/` (her ablation config ayrı dizin)
- `embedding_config.py`'a 2 yeni profil eklenir (`bge-m3`, `e5-base`); mevcut `minilm`/`e5-large` korunur
- `RAGService` ve `medical_knowledge` collection dokunulmaz
- Faz 4'te (Adım 13, opsiyonel) `ReportGenerator._retrieve_rag()` genişletilir

---

## 4. Filtre + ablation tasarımı (revize, veri keşfi sonrası)

**Veri keşfi (2026-05-03):** Hastane öykü alanını telegrafik dolduruyor (median 8ch, sadece "X GÜNDÜR" formatında). Uzunluk eşikleri uygulamak veriyi katlediyor (38K → 1.9K). **Karar: filtre eşiği yok**, alan dolu/boş ayırımı yeter. Boilerplate cascade ciddi (ham 38,222 → exact dedup sonrası 18,270; %51 birebir kopya).

### Tek korpus, dedup'lı:
- `ic_anamnez_filt_v1_minimal` (yakınma boş olmayanlar + exact dedup) → **18,270 satır**
- `ic_anamnez_filt_v1_clean` (v1_minimal + MinHash 0.85) → **14,518 satır** (%20.5 fuzzy dedup)
- `ic_anamnez_eval_holdout` (v1_clean'den random 100, seed=42) → **100 satır**
- `ic_anamnez_filt_v1_corpus` (v1_clean - holdout) → **14,418 satır**

### Ablation eksenleri (3 config, embedding text variation):

| Config | Embedding text format | Test ettiği |
|---|---|---|
| **baseline** | `YAKINMA:\n...\nÖYKÜ:\n...\nMUAYENE:\n...` (3 alan başlıklı) | Referans |
| **no_titles** | `{yakinma} {oyku} {muayene}` (başlıksız konkat) | "Bölüm başlıkları sinyal mi gürültü mü?" |
| **metadata** | baseline + `ÖZ GEÇMİŞ:\n...\nYAŞAM TARZI:\n...\nVİTAL:\n...` | "Kronik hastalık + yaşam tarzı + vital değerler retrieval'a katkı yapıyor mu?" |

Tüm 3 config aynı 14,418 satırı kullanır, sadece embedding text farklı.

### Embed pass planı (B stratejisi):
- 3 config × E5-base = 3 pass
- 1 config × BGE-M3 (kazanan filtre + final model karşılaştırması) = 1 pass
- **Toplam 4 embed pass**, ~2-3 saat 3050 Mobile GPU

---

## 5. Eval set kompozisyonu

| Kaynak | Sayı | Üretim |
|---|---|---|
| Manuel (sen yazarsan) | 30 | `eval_queries_manual.json`, gerçek doktor konuşma tonu |
| Sentetik (Haiku ile) | 50 | `gen_synthetic_queries.py` (~$0.10 API maliyeti) |
| Hold-out leave-one-out | 100 | Filtreli korpustan random_seed=42 |
| **Toplam** | **180** | |

Mini panel:
- **100 holistic** (her query için tek Likert 1-5: "5 sonuç bu hastayı doldurmaya yeter mi?") — sen + LLM-judge
- **20 deep-dive** (her query için 5 retrieve sonucun her biri ayrı Likert + neden notu) — sen + LLM-judge

---

## 6. 13 adımlı yol haritası

| # | Adım | Durum | Çıktı |
|---|---|---|---|
| 1 | Bu plan dokümanı | **devam ediyor** | `DAHILIYE_RAG_PLAN.md` |
| 2 | PHI bulk scan | bekliyor | Eşleşme sayıları, plan.md log |
| 3 | Filtre tabloları (v1, v2, v4) | bekliyor | 3 SQLite tablosu |
| 4 | Dedup pass (v3) | bekliyor | MinHash sonuçları, v3 tablosu |
| 5 | Hold-out seçici | bekliyor | `ic_anamnez_eval_holdout` |
| 6 | Embed text builder | bekliyor | Python helper |
| 7 | Embedding profil ekleme | bekliyor | `embedding_config.py` güncellemesi |
| 8 | Build vector script (5 embed pass) | bekliyor | 5 ChromaDB collection |
| 9 | AnamnezRAGService | bekliyor | Servis sınıfı |
| 10 | Eval set hazırlama | bekliyor | 180 query |
| 11 | Eval pipeline (RAGAS + LLM-judge) | bekliyor | Per-config skor CSV |
| 12 | Ablation analiz + kazanan seçim | bekliyor | Sonuç tablosu, karar |
| 13 | (Opsiyonel) Production entegrasyon | adım 12 sonrası karar | `report_generator.py` patch |

---

## 7. Adım adım çalışma kaydı

> Bu bölüme her adım tamamlandıktan sonra **gerçek sayılar** ve **kararlar** yazılır.

### Adım 1 — Plan dokümanı oluşturma
- **Tarih:** 2026-05-03
- **Çıktı:** Bu dosya (`apps/backend/src/rag/DAHILIYE_RAG_PLAN.md`)
- **Sonuç:** ✓ Faz 0/1/2 kararları + 13 adımlı plan + filtre eksenleri belgelenmiş.
- **Sonraki:** Adım 2 — PHI bulk scan

### Adım 2 — PHI bulk scan
- **Tarih:** 2026-05-03
- **Script:** `apps/backend/src/rag/phi_scan.py` (deid_service regex'lerini reuse eder)
- **Taranan:** 38,222 satır × 17 metin alanı
- **Sonuç:**
  - **TC kimlik:** 0 hit ✓
  - **Telefon:** 0 hit ✓
  - **E-mail:** 0 hit ✓
  - **Pascal-case isim bigram:** 111 hit (61 unique, 38 singleton)
  - Bigram frequency analizi: tamamı **tıbbi terim** (top: "açlık kan" ×12, "antral gastrit" ×6, "endoskopik hiperemik" ×5, "hidroksi vitamin" ×4, "bisoprolol fumarat" ×3). Kişi adı tespit edilmedi.
- **Karar:** Veri PHI temiz, embed'e güvenle gidebiliriz. Defense-in-depth amacıyla yine de Adım 13 (production entegrasyon) öncesi RAG retrieval çıktıları LLM'e gitmeden önce TC/phone/email regex katmanı eklenecek (güvenlik notu, plan §8).
- **Sonuç:** ✓
- **Sonraki:** Adım 3 — Filtre tabloları (v1, v2, v4)

### Adım 3 — Filtre tablosu (minimal)
- **Tarih:** 2026-05-04
- **Script:** `apps/backend/src/rag/filters/01_minimal.sql` + `apply_filters.py`
- **Veri keşfi:** ÖYKÜ medianı 8ch — uzunluk eşiği saçma; eski `01_basic.sql`/`02_lax.sql` `filters/archive/` altına alındı.
- **Yeni filtre:** yakınma boş olmasın + exact dedup (yakinma+öykü+muayene tuple)
- **Sonuç:** 38,222 → 18,270 (%51 birebir kopya elendi)
- **Sonuç:** ✓

### Adım 4 — Dedup pass (MinHash)
- **Tarih:** 2026-05-04
- **Script:** `apps/backend/src/rag/dedup_anamnez.py` (datasketch MinHashLSH)
- **Parametreler:** Jaccard 0.85, num_perm=128, word 5-shingle
- **Sonuç:** 18,270 → 14,518 (%20.5 fuzzy dedup, 1,798 cluster, 41,314 near-dup pair)
- **Süre:** 19 saniye
- **Sonuç:** ✓

### Adım 5 — Hold-out
- **Tarih:** 2026-05-04
- **Script:** `apps/backend/src/rag/eval_holdout_select.py` (random_seed=42)
- **Sonuç:** 14,518 → 100 holdout + 14,418 corpus
- **Sonuç:** ✓

### Adım 6 — Embed text builder
- **Tarih:** 2026-05-04
- **Script:** `apps/backend/src/rag/embed_text_builder.py`
- **3 format:** `baseline`, `no_titles`, `metadata`
- **Smoke test:** 2 random satırda doğrulandı (baseline ~100-160ch, no_titles ~80-130ch, metadata ~200-460ch)
- **Sonuç:** ✓

### Adım 7 — Embedding profil
- **Tarih:** 2026-05-04
- **Değişiklik:** `apps/backend/src/services/embedding_config.py`'a `e5-base` ve `bge-m3` profilleri eklendi. Mevcut `minilm` ve `e5-large` korundu.
- **Sonuç:** ✓

### Adım 8 — Build vector (E5-base × 3 format)
- **Tarih:** 2026-05-04
- **Script:** `apps/backend/src/scripts/build_anamnez_vectors.py`
- **Onceki blokaj:** PyTorch CPU-only kuruluydu; CUDA için `pip install torch==2.8.0+cu126` ile yeniden kuruldu (RTX 3050 Ti, 4.29 GB CUDA aktif)
- **3 pass sonuçları:**
  | Pass | Format | Encode | sps | ChromaDB write | Smoke top-1 dist |
  |---|---|---|---|---|---|
  | 1 | baseline | 62.0s | 232.5 | 9.2s | 0.1224 |
  | 2 | no_titles | 55.0s | 262.1 | 9.3s | 0.1072 |
  | 3 | metadata | 96.0s | 150.2 | 11.0s | 0.1224 |
- **Toplam wall:** ~5 dk
- **Smoke kalitesi:** üç format da "boğaz ağrısı öksürük halsizlik 2 gündür" sorgusunda ÜSYE pattern'lerini doğru getiriyor
- **Çıktılar:** `data/anamnez_chroma_e5-base_baseline/`, `_no_titles/`, `_metadata/` — her biri 14,418 doc, `anamnez_<fmt>` collection
- **Sonuç:** ✓
- **Kalan:** Pass 4 — BGE-M3 × kazanan format, Adım 12 sonrası

### Adım 9 — AnamnezRAGService
- **Tarih:** 2026-05-04
- **Yeni dosya:** `apps/backend/src/services/anamnez_rag_service.py`
- **Tasarım:** Mevcut `RAGService` dokunulmadı; yeni servis profil + format parametresi alır, ChromaDB'yi `data/anamnez_chroma_<profile>_<fmt>/` altından yükler
- **Sonuç:** ✓

### Adım 10 — Eval set hazırlama
- **Tarih:** 2026-05-04
- **Sentetik 50 query (Haiku 4.5):**
  - 50 dahiliye senaryosu × Haiku → ASR-style doktor konuşma transkriptleri
  - Token: in=17,385  out=8,315
  - Maliyet: **$0.059**
  - Çıktı: `apps/backend/src/rag/eval_queries_synthetic.json`
- **Holdout 100 (Adım 5'te tamamlandı):** `ic_anamnez_eval_holdout` tablosu, seed=42
- **Manuel 30 query:** kullanıcı sonra ekleyecek (`eval_queries_manual.json` iskeleti hazır)
- **Toplam eval input (şimdiki):** 150 query (100 holdout + 50 sentetik)
- **Sonuç:** ✓ (manuel sonra eklenir)

### Adım 9 — RAG servis
- **Durum:** bekliyor

### Adım 10 — Eval set
- **Durum:** bekliyor

### Adım 11 — Eval pipeline + 3-config E5-base + BGE-M3 eval
- **Tarih:** 2026-05-04
- **Script:** `apps/backend/src/rag/eval_anamnez.py`
- **Eval input:** 150 query (100 holdout + 50 sentetik)
- **3 E5-base config** ($1.40):
  | Config | Holistic | Deep-dive | Combined | Top1 dist | Diversity |
  |---|---|---|---|---|---|
  | baseline | 3.59 | 3.82 | 3.71 | 0.109 | 0.579 |
  | no_titles | 3.52 | 3.61 | 3.57 | 0.099 | 0.618 |
  | **metadata** | **3.66** | 3.80 | **3.73** | 0.116 | 0.621 |
- **BGE-M3 × metadata** ($0.55):
  | Holistic | Deep-dive | Combined | Top1 dist | Diversity |
  |---|---|---|---|---|
  | **3.92** | **4.51** | **4.22** | 0.270 | 0.600 |
- **Çıktılar:** `apps/backend/src/rag/eval_results/` altında 4 config × 3 dosya (per_query.csv, per_result.csv, summary.json) + all_summaries.json
- **Sonuç:** ✓

### Adım 12 — Ablation analiz + kazanan config
- **Tarih:** 2026-05-04
- **Format kazananı (E5-base sabitlendiğinde):** `metadata` (combined 3.73)
- **Model kazananı (metadata sabitlendiğinde):** `bge-m3` (combined 4.22, **+%13** artış vs E5-base)
- **Final production config:**
  ```
  profile = "bge-m3"
  fmt = "metadata"
  chroma_dir = data/anamnez_chroma_bge-m3_metadata/
  collection = anamnez_metadata
  ```
- **Toplam bütçe:** $2.01 / $2.95 (buffer $0.94 kaldı)
- **Sonuç:** ✓

### Adım 13 — Production entegrasyon
- **Durum:** Kullanıcı kararı bekleniyor — bu sprint'te mi, ayrı sprint mi

---

## 8. Güvenlik notları (bu sprint kapsamı dışı, kayıt için)

Faz 1 güvenlik analisti raporundan, **dahiliye RAG'a doğrudan bloke etmeyen ama production geçişinde kritik** bulgular:

- 🔴 `.env` dosyasında açık API anahtarları (Anthropic + HF). Git history kontrolü + rotate gerekli (ayrı görev).
- 🟡 `routes/transcription.py` WebSocket endpoint'i `kvkk_consent` kontrolsüz (frontend bypass riski).
- 🟡 RAG retrieved metinleri Haiku'ya prompt olarak giderken defense-in-depth TC/telefon regex (Adım 13 zorunlu).
- 🟢 `import_anamnez.py`'de PHI bulk tarama yoktu → Adım 2'de ele alınıyor (defense-in-depth).

Mevcut `deid_service.py` regex'leri (`_RE_TC`, `_RE_PHONE`, `_RE_EMAIL`, isim bigram) Adım 2'de yeniden kullanılır.

---

## 9. Maliyet ve süre tahmini

| Kalem | Tahmin |
|---|---|
| Embedding (BGE-M3 + E5-base, lokal) | $0 |
| Sentetik query üretimi (Haiku) | ~$0.10 |
| LLM-judge eval (4 config × ~120 puanlama × 2 model) | ~$1.50-3 |
| **Toplam API** | **~$2-3 USD** |
| GPU build (5 embed pass, 3050 Mobile) | 30-60 dk wall |
| Manuel Likert (180 query) | 3-4 saat |
| Toplam aktif iş (kod + test) | ~10-12 saat dağıtık |

---

## 10. Kullanılan kütüphane ve modeller

- `BAAI/bge-m3` — BGE-M3 embedding (HuggingFace, açık)
- `intfloat/multilingual-e5-base` — E5-base embedding (HuggingFace, açık; `query: `/`passage: ` prefix zorunlu)
- `chromadb` — vector DB (mevcut)
- `sentence-transformers` — embedding pipeline (mevcut)
- `datasketch` — MinHash + LSH (yeni dependency, requirements.txt güncellenecek)
- `ragas` — RAG değerlendirme (yeni dependency, requirements.txt güncellenecek)
- `rapidfuzz` — fuzzy match (mevcut)
- `pandas`, `openpyxl` — Excel/SQLite IO (mevcut)
- Anthropic Claude Haiku 4.5 — sentetik query üretimi + LLM-judge (mevcut API)
