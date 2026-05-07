# Sprint Özeti — Dahiliye Anamnez RAG Production Entegrasyonu

**Tarih aralığı:** 2026-05-03 → 2026-05-04
**Branch:** `feature/dahiliye-real-anamnesis-rag` → master'a merge edildi
**Master commit:** `d0f4e8e` → `33463c9` (43 dosya, +4322 satır)
**Toplam aktif iş:** ~12-15 saat dağıtık
**Toplam API maliyeti:** ~$2.01 (Anthropic Haiku — sentetik query üretimi + LLM-judge eval)

---

## 1. Sprint hedefi

Mevcut sentetik RAG (LLM-üretimli `medical_knowledge` collection, MiniLM) yerine **38,222 gerçek hastane dahiliye anamnezi** üzerine kurulu yeni bir RAG sistemini production'a almak. Doktor ASR transkripti → benzer geçmiş anamnezler retrieve → LLM (Claude Haiku 4.5) few-shot ile yapılandırılmış rapor üretimi.

---

## 2. Süreç (agent-teams-pipeline disiplini)

Pipeline 5 fazda tekrarlandı (önce build/ablation, sonra production entegrasyon):

- **Faz 0** — Anlama & Onay (kararlar paketi)
- **Faz 1** — Paralel Araştırma (4 takım üyesi: Tasarım Analisti, Web Research, Impact Analisti, Güvenlik Analisti)
- **Faz 2** — Sentez & Çözüm Önerisi (alternatifler + öneri)
- **Faz 3** — İmplementasyon Planı (sıralı adımlar + bağımlılıklar)
- **Faz 4** — Uygulama & Doğrulama (her adım sonu impact + onay)

---

## 3. Veri pipeline'ı

| Aşama | Çıktı | Sayı |
|---|---|---|
| Ham Excel | `data/Anemnez_tetkik/IcAnemnez.xlsx` | 38,222 |
| SQLite import | `data/anamnez.db / ic_anamnez` | 38,222 |
| PHI bulk scan | TC/Phone/Email | **0 hit** (Pascal-case bigram 111 hepsi tıbbi terim) |
| Minimal filtre + exact dedup | `ic_anamnez_filt_v1_minimal` | 18,270 (%51 kopya elendi) |
| MinHash 0.85 fuzzy dedup | `ic_anamnez_filt_v1_clean` | 14,518 (%20.5 fuzzy elendi) |
| Hold-out (random_seed=42) | `ic_anamnez_eval_holdout` | 100 |
| Embed corpus | `ic_anamnez_filt_v1_corpus` | 14,418 |

**Önemli veri keşfi:** Bu hastanenin pratiği "öykü" alanını telegrafik doldurma (median 8ch, sadece "X GÜNDÜR"). Faz 0'daki "uzunluk eşiği" filtre kararı veriye uymadığı için revize edildi → minimal filtre (yakınma boş olmasın yeter).

---

## 4. Ablation sonuçları (LLM-judge Likert 1-5, 150 query × 4 config)

| Config | Holistic | Deep-dive | **Combined** | Top-1 dist | Diversity |
|---|---|---|---|---|---|
| E5-base × no_titles | 3.52 | 3.61 | 3.57 | 0.099 | 0.62 |
| E5-base × baseline (başlıklı) | 3.59 | 3.82 | 3.71 | 0.109 | 0.58 |
| E5-base × metadata (+vital+yaşam) | 3.66 | 3.80 | 3.73 | 0.116 | 0.62 |
| **🏆 BGE-M3 × metadata** | **3.92** | **4.51** | **4.22** | 0.270 | 0.60 |

**Kazanan: BGE-M3 × metadata** — combined Likert 4.22/5 (E5-base'den +%13). Deep-dive'da en güçlü sıçrama (3.80 → 4.51, +%19).

---

## 5. Production entegrasyon

### Mimari
- Yeni servis: `AnamnezRAGService` (paralel — mevcut `RAGService` dokunulmadı)
- ChromaDB: `data/anamnez_chroma_bge-m3_metadata/` (gitignored)
- Mevcut sentetik RAG **kapatıldı** ama dosyalar kalıcı (env flag `ASR_RAG__USE_SYNTHETIC=true` ile geri açılabilir; default false)

### Akış
```
Frontend POST /api/v1/reports {top_k}
  ↓
ReportGenerator.generate_report (BATCH)
  ↓
_retrieve_anamnez_rag → AnamnezRAGService.query_similar_cases (top-5)
  ↓
_format_anamnez_examples → <examples> XML bloğu
  ↓
batch_prompt = examples_block + _build_batch_prompt()
  ↓
LLM (Haiku) → 26 section JSON
  ↓
ICD + SUT pipeline
```

### Streaming flow da aynı RAG'i kullanıyor (global query, 1 kez başta — per-section overhead yok).

### Güvenlik / KVKK katmanları
- **PHI mask 2 katman** (defense-in-depth):
  1. Build-time: `build_anamnez_vectors.py` embed öncesi `mask_phi()` (0 hit, beklenen)
  2. Query-time: `AnamnezRAGService.query_similar_cases` çıkışında idempotent mask
- Maskleme tipleri: `[MASKED_TC]` (Luhn checksum geçen 11-haneliler), `[MASKED_PHONE]`, `[MASKED_EMAIL]`
- WebSocket KVKK consent guard: `routes/transcription.py` satır 134 — frontend bypass kapatıldı

### Frontend
- Settings page `top_k` slider 3-10 (default 5), `localStorage('anamnez_top_k')`
- ReportReviewPage AI mutation body'ye `top_k` ekleniyor

### Startup
- **Hard-fail** with actionable error: ChromaDB klasörü yoksa backend açılmaz, log mesajı tam komut verir
- Warmup: 2 dummy `encode("warmup")` ile CUDA cliff bypass

---

## 6. Yapılan dosya değişiklikleri (43 dosya, +4322 satır)

### Yeni servis & yardımcılar
- `apps/backend/src/services/anamnez_rag_service.py`
- `apps/backend/src/rag/phi_guard.py` (regex + Luhn)
- `apps/backend/src/rag/embed_text_builder.py`

### Veri pipeline scriptleri
- `apps/backend/src/scripts/import_anamnez.py` (Excel → SQLite)
- `apps/backend/src/scripts/build_anamnez_vectors.py` (PHI mask + BGE-M3/E5 embed)
- `apps/backend/src/rag/apply_filters.py` + `filters/01_minimal.sql` + `filters/archive/`
- `apps/backend/src/rag/dedup_anamnez.py` (datasketch MinHash 0.85)
- `apps/backend/src/rag/eval_holdout_select.py`
- `apps/backend/src/rag/phi_scan.py`

### Eval pipeline
- `apps/backend/src/rag/gen_synthetic_queries.py` (50 senaryo × Haiku, $0.06)
- `apps/backend/src/rag/eval_anamnez.py` (RAGAS-style + LLM-judge)
- `apps/backend/src/rag/eval_results/*.csv|*.json` (4 config × 3 dosya + all_summaries)
- `apps/backend/src/rag/eval_queries_synthetic.json`, `eval_queries_manual.json`
- `apps/backend/src/rag/test_rag_live.py` (canlı doğrulama smoke)

### Production entegrasyon
- `apps/backend/src/main.py` (lifespan)
- `apps/backend/src/services/report_generator.py` (constructor + 2 RAG metodu + batch + streaming)
- `apps/backend/src/services/embedding_config.py` (bge-m3 + e5-base profilleri)
- `apps/backend/src/routes/reports.py` (top_k geçişi)
- `apps/backend/src/routes/transcription.py` (KVKK guard)
- `apps/backend/src/schemas/report.py` (`top_k` Pydantic Field)
- `config/settings.py` (RAGSettings extend)

### Frontend
- `apps/frontend/src/renderer/src/pages/SettingsPage.tsx` (top_k slider + localStorage)
- `apps/frontend/src/renderer/src/pages/ReportReviewPage.tsx` (top_k POST body)
- `apps/frontend/src/renderer/src/i18n/translations.ts` (TR/EN labels)

### Docs
- `apps/backend/src/rag/DAHILIYE_RAG_PLAN.md` (canlı çalışma kaydı, 13 adım)
- `apps/backend/src/rag/SESSION_SUMMARY_2026-05-04.md` (bu dosya)

### Yeni dependency
- `datasketch>=1.6.0` (MinHash LSH)

---

## 7. Live doğrulama

### ÜSYE sorgu testi (`test_rag_live.py`)
- Query: "32 yaşında erkek, 3 gündür boğaz ağrısı, halsizlik, ateş, burun akıntısı, farenks hiperemik..."
- Top-5 hepsi farenjit pattern'i, distance 0.27-0.28 (sıkı kümelenme)
- ✅ Semantic match mükemmel

### Kapsamlı dahiliye vakası (DM + HT kontrol, 26 alan)
- Transkript: 58 yaşında kadın, halsizlik + ayaklarda uyuşma + ağız kuruluğu + polidipsi, DM + HT öyküsü, vital'lar + öneri + tetkik
- Sonuç: 24/26 alan dolu, vital'lar `high` confidence
- **Stilistik proof RAG çalıştığının kanıtı:**
  - `HALSIZLIK + AYAKLARDA UYUŞMA + AYAKLARDA YANMA + AĞIZ KURULUĞU + POLİDİPSİ` (`+` ayraç korpustan)
  - `ANNE DM ---- BABA HT` (`----` separator korpustan)
  - `DM /// METFORMİN 1000 MG 2X1` (`///` separator)
  - `aşırı su tüketimi` → **POLİDİPSİ** (tıbbi jargon dönüşümü, RAG/synonym)
  - BÜYÜK HARF + telegrafik yapı (korpus tarzı)

---

## 8. Hatırlatmalar / Sprint dışı işler

### 🔴 CRITICAL
- **`.env` API key rotate**: Anthropic + HF token `.env` dosyasında açık. Git history kontrolü + key rotation yapılmalı (kullanıcı "şimdilik boşver" dedi — ileride mutlaka).

### 🟡 MEDIUM (sprint dışı, ayrı görevler)
- **ICD-10 halüsinasyon filtresi bug**: `icd10_suggestion_service.py` "Dropped 4 hallucinated ICD code(s): ['E11.9', 'I10', ...]" yapıyor — öz geçmişten gelen gerçek tanıları (E11/I10) yanlış eliyor. Filter mantığı revize edilmeli.
- **TEDAVI vs ISTENEN_TETKIK ayrımı**: LLM prompt'unda net değil, tetkikler bazen TEDAVI alanına geçiyor. `system_prompt.py` prompt güncellemesi gerekiyor.
- **ASR/pyannote model cache**: Test laptop'ta HF download sorunu — modelleri pre-cache veya offline mode default. `HF_HUB_OFFLINE=1` ile çözülebiliyor ama production'da otomatik olmalı.
- **OpenEMR oauth_clients**: Dump'ta tablo boş — manual OAuth client kayıt gerekiyor (XAMPP MySQL + admin panel).

### 🟢 LOW (gelecek iyileştirmeler)
- Hekim paneli (3-5 dahiliye uzmanı × 100 query Likert) — şu an tek-rater + LLM-judge ile sınırlı
- E5-base baseline ablation'ında BGE-M3 ile 4'lü full ablation (şu an B stratejisi: filtre kazananı + 2 model)
- Cosine threshold fallback (Almanac pattern: top-1 dist eşik altıysa few-shot bos)
- Manuel 30 query (kullanıcı tarafı) eval setini zenginleştirme
- Frontend Settings page'e backend env var sync (şu an localStorage'a yazıyor)
- `rag_used:bool` audit log alanı (KVKK iz)

### ⚙️ Hard-fail davranış uyarısı
**`AnamnezRAGService` startup'ta `data/anamnez_chroma_bge-m3_metadata/` yoksa backend açılmaz.** Yeni geliştirici/ortam kuruyorsa README'ye eklenmeli:
```bash
python -m apps.backend.src.scripts.import_anamnez   # Excel → SQLite
python -m apps.backend.src.scripts.build_anamnez_vectors --profile bge-m3 --format metadata
```

---

## 9. Mezuniyet projesi raporu için anahtar bulgular

1. **Real-data RAG vs sentetik RAG karşılaştırma:** Mevcut sentetik RAG production akışında **hiç çağrılmamış** olduğu keşfedildi (batch flow'da `_retrieve_rag` yoktu). Yani gerçek-data RAG **mevcut RAG'i değiştirdi değil, ilk kez RAG'i aktif etti**.
2. **Embedding model karşılaştırması (Türkçe klinik):** BGE-M3 vs E5-base ablation, Türkçe klinik metin için **literatürde yayınlanmış benchmark yok** — bu sprint orijinal katkı.
3. **Filtre/format ablation kararları:** Hastane veri yapısı (öykü median 8ch) literatür beklentilerine uymuyordu, filtre eşikleri **veriye göre revize edildi**.
4. **Production-ready 4.22/5 Likert** — mezuniyet demosu için sağlam temel.
5. **Defense-in-depth PHI**: 2 katmanlı maskleme + WebSocket KVKK guard — KVKK Madde 12 uyumlu.
