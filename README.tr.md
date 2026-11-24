# Doctor AI Assistant (KlinikAsistan)

[English](README.md) · **Türkçe**

Türkçe polikliniklerde yapay zekâ destekli tıbbi dokümantasyon için geliştirilmiş
masaüstü uygulaması. Doktor–hasta görüşmesini sesli olarak kaydeder, konuşmayı
metne çevirir, konuşmacıları ayırır ve büyük dil modeli (LLM) ile yapılandırılmış
**anamnez**, **ICD-10 tanı kodu** ve **SUT tetkik** önerileri üretir. Sonuçlar
OpenEMR (HBYS) sistemine aktarılabilir.

> Bu bir bitirme/araştırma projesidir (Kadir Has Üniversitesi, Bilgisayar
> Mühendisliği). Gerçek hasta verisiyle klinik kullanım öncesi KVKK ve ilgili
> mevzuat uyumu ayrıca değerlendirilmelidir.

> **Veri hakkında:** Geliştirmede kullanılan kimliksizleştirilmiş hastane
> raporları, bunlardan üretilen anamnez veritabanı/ChromaDB indeksleri ve
> değerlendirme çıktıları KVKK gereği bu depoda **yer almaz**. Kod, kendi
> verinizle indeksleri yeniden üretecek scriptleri içerir; veri olmadan
> uygulama anamnez RAG'i kapalı olarak çalışır.

## Ekran görüntüleri

> Görüntülerdeki hasta/doktor bilgileri demo amaçlı kurgusaldır.

**Rapor inceleme:** konuşmacılara ayrılmış transkript (solda), LLM'in ürettiği
25 alanlı anamnez taslağı (sağda), doktor onayı ve HBYS'ye gönderim.

![Rapor inceleme ekranı](docs/images/ui-report-review.png)

| ICD-10 tanı önerileri | SUT tetkik önerileri |
|---|---|
| ![ICD-10 önerileri](docs/images/ui-icd10-suggestions.png) | ![SUT önerileri](docs/images/ui-sut-suggestions.png) |

| Pipeline | KVKK: 4 katmanlı kimliksizleştirme |
|---|---|
| ![Pipeline](docs/images/pipeline.png) | ![De-identification](docs/images/deidentification.png) |

<details>
<summary>Üretilen anamnez raporu (PDF çıktısı)</summary>

![Anamnez raporu](docs/images/generated-anamnesis-report.png)
</details>

## Sonuçlar

20 sentetik dahiliye konsültasyonu üzerinde uçtan uca değerlendirme
(ICD-10 exact F1 ortalama **0.635**, SUT tetkik F1 ortalama **0.667**) ve
dahiliye-filtreli ICD-10 vektör veritabanının Recall@k kazancı:

<p>
  <img src="docs/images/graph_per_form_f1.png" alt="Form bazında ICD-10 ve SUT F1" width="100%">
</p>
<p>
  <img src="docs/images/graph_recall_at_k.png" alt="ICD-10 Recall@k karşılaştırması" width="70%">
</p>

Ablation çalışmasında her adımın ICD-10 macro F1'e katkısı (baseline 0.455 → 0.665):

![Ablation](docs/images/ablation-icd10-f1.png)

Ayrıntılı ablation raporları: `docs/` dizini.

---

## İçindekiler

- [Özellikler](#özellikler)
- [Mimari](#mimari)
- [Teknoloji Yığını](#teknoloji-yığını)
- [Önkoşullar](#önkoşullar)
- [Kurulum](#kurulum)
  - [1. Depoyu klonla](#1-depoyu-klonla)
  - [2. Backend kurulumu](#2-backend-kurulumu)
  - [3. Ortam değişkenleri](#3-ortam-değişkenleri-env)
  - [4. Veritabanı hazırlığı](#4-veritabanı-hazırlığı)
  - [5. Frontend kurulumu](#5-frontend-kurulumu)
- [Çalıştırma](#çalıştırma)
- [Docker ile çalıştırma](#docker-ile-çalıştırma)
- [Hasta verisini içe aktarma](#hasta-verisini-içe-aktarma-paylaşılan-veritabanı-dumpı)
- [OpenEMR (HBYS) entegrasyonu](#openemr-hbys-entegrasyonu)
- [Testler](#testler)
- [Proje yapısı](#proje-yapısı)
- [Dokümantasyon](#dokümantasyon)

---

## Özellikler

- **ASR (Konuşma → Metin):** `faster-whisper` tabanlı toplu (batch) transkripsiyon,
  `pyannote.audio` ile konuşmacı ayrımı (diarization), `DeepFilterNet` ile gürültü
  bastırma.
- **LLM Anamnez Üretimi:** Tek bir LLM çağrısında 25 alanlı yapılandırılmış anamnez
  (JSON) üretimi. Varsayılan model **Anthropic Claude Haiku 4.5**.
- **RAG (Retrieval-Augmented Generation):** BGE-M3 embedding + ChromaDB üzerinden,
  kimliksizleştirilmiş gerçek hastane raporlarından bağlam getirme.
- **ICD-10 Tanı Kodu Eşleştirme:** NER (varlık çıkarımı) → vektör tabanlı anlamsal
  arama → LLM ile kod seçimi. 11.332 Türkçe ICD-10 kodu.
- **SUT Tetkik Önerisi:** Konuşmadan tetkik isteklerini niyet (intent) analiziyle
  ayıklama.
- **OpenEMR (HBYS) Entegrasyonu:** OAuth2 REST API ve doğrudan MariaDB sorguları
  ile hasta/rapor alışverişi.
- **PDF Rapor:** `reportlab` ile rapor çıktısı.
- **Masaüstü Arayüz:** Electron + React tabanlı, tamamı Türkçe arayüz.

---

## Mimari

```
┌─────────────────────────┐         ┌──────────────────────────────┐
│   Frontend (Electron)   │         │      Backend (FastAPI)        │
│  React 19 + TypeScript  │◀───────▶│      Python 3.11              │
│                         │  WS /   │                               │
│  - Ses kaydı            │  SSE /  │  - ASR pipeline               │
│  - Görüşme ekranı       │  REST   │  - LLM servisleri             │
│  - Rapor inceleme       │         │  - RAG / ICD-10 / SUT         │
└─────────────────────────┘         │  - OpenEMR entegrasyonu       │
                                    └───────────────┬───────────────┘
                                                    │
                            ┌───────────────────────┼───────────────────┐
                            ▼                       ▼                   ▼
                     SQLite / MariaDB         ChromaDB (vektör)     OpenEMR (HBYS)
                     (oturum, kullanıcı,      (anamnez RAG,         OAuth2 + MariaDB
                      rapor, ICD-10)           ICD-10 arama)
```

- **İletişim:** WebSocket (ses/transkripsiyon), SSE (LLM streaming), REST (CRUD)
- **API sözleşmesi:** `shared/api-spec.json` — her iki katman için tek doğru kaynak
- **Operasyonel veritabanı:** Varsayılan SQLite (`data/asr.db`); ekip paylaşımı için
  MariaDB'ye geçilebilir.

---

## Teknoloji Yığını

### Backend — Python 3.11

| Alan | Bağımlılıklar |
|------|---------------|
| Web çatısı | `fastapi`, `uvicorn[standard]`, `sse-starlette` |
| ASR | `faster-whisper`, `pyannote.audio`, `deepfilternet`, `ffmpeg` |
| NLP / ML | `torch`, `torchaudio`, `transformers`, `sentence-transformers`, `gliner`, `onnxruntime` |
| Vektör veritabanı | `chromadb` |
| LLM sağlayıcıları | `anthropic` (Claude), `google-genai` (Gemini), Groq, Cerebras, OpenRouter, Moonshot, Ollama (yerel) |
| Veritabanı | `sqlalchemy` 2.x, `aiosqlite`, `asyncmy`, `aiomysql`, `pymysql` |
| Kimlik doğrulama | `python-jose[cryptography]`, `bcrypt` |
| Arama / metin | `rapidfuzz`, `rank-bm25`, `datasketch` |
| Yardımcı | `pydantic` 2.x, `pydantic-settings`, `python-dotenv`, `httpx`, `reportlab`, `numpy<2.0`, `rich` |

> **Not:** PyTorch, GPU/CPU varyantına göre ayrı kurulur. Detay aşağıda.

### Frontend — Node.js / Electron

| Alan | Bağımlılıklar |
|------|---------------|
| Çatı | `electron` 39, `react` 19, `react-dom` 19, `typescript` 5.9 |
| Derleme | `electron-vite` 5, `vite` 7, `electron-builder` 26 |
| UI / stil | `tailwindcss` 4, `lucide-react`, `clsx`, `tailwind-merge` |
| Durum yönetimi | `zustand`, `@tanstack/react-query` |
| Yönlendirme | `react-router-dom` 7 |

---

## Önkoşullar

Projeyi indiren kişinin makinesinde bulunması gerekenler:

| Araç | Sürüm | Not |
|------|-------|-----|
| **Python** | 3.11 | `conda`/`venv` önerilir |
| **Node.js** | 20+ (LTS) | Frontend için |
| **FFmpeg** | güncel | ASR için zorunlu — sistem PATH'inde olmalı |
| **Git** | — | |
| **Docker** | (opsiyonel) | MariaDB + OpenEMR stack'i için |
| **GPU (CUDA)** | (opsiyonel) | ASR'yi hızlandırır; yoksa CPU ile çalışır |

Ayrıca gerekli **API anahtarları**:
- **Anthropic API anahtarı** — varsayılan LLM (Claude Haiku 4.5) için
- **Hugging Face token (`HF_TOKEN`)** — `pyannote` diarization modelleri için

---

## Kurulum

### 1. Depoyu klonla

```bash
git clone https://github.com/Elifglm/Doctor-AI-Assistant.git
cd Doctor-AI-Assistant
```

### 2. Backend kurulumu

**Conda ile (önerilir):**

```bash
conda env create -f environment.yml
conda activate asr
```

**veya venv + pip ile:**

```bash
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 1) Önce PyTorch'u doğru varyantla kur:
pip install torch torchaudio       # CPU
# GPU için: https://pytorch.org/get-started/locally/ adresindeki CUDA komutu

# 2) Sonra geri kalan bağımlılıklar:
pip install -r requirements-docker-base.txt
pip install -r apps/backend/requirements.txt
```

> **Neden PyTorch önce?** `whisperx`/`pyannote`/`transformers` aksi halde PyPI'den
> varsayılan CUDA'lı `torch` çeker. Önce kurulursa pip onu yeterli görür.

### 3. Ortam değişkenleri (`.env`)

```bash
cp .env.example .env
```

`.env` içinde doldurulması gerekenler:

```ini
# LLM — varsayılan sağlayıcı Anthropic
ASR_LLM__MODE=anthropic
ASR_LLM__ANTHROPIC_API_KEY=<anthropic-api-anahtarınız>

# ASR — pyannote diarization modelleri için
HF_TOKEN=<hugging-face-token>

# Veritabanı — boş bırakılırsa SQLite (data/asr.db) kullanılır.
# MariaDB için (ekip paylaşımı):
# DATABASE_URL=mysql+asyncmy://klinik:klinik@127.0.0.1:3307/klinikasistan
```

### 4. Veritabanı hazırlığı

Anamnez RAG verisi (gerçek hasta raporları) bu depoda yoktur. Veri olmadan
çalıştırmak için `.env` içinde `ANAMNEZ_RAG_ENABLED=false` ayarlayın; kendi
kimliksizleştirilmiş verinizle indeksi `import_anamnez` ve
`build_anamnez_vectors` scriptleri üretir.

ICD-10 vektör veritabanı yeni klonda bir kez kurulmalıdır:

```bash
# ICD-10 kodlarını içe aktar
python -m apps.backend.src.scripts.import_icd10 docker/openemr/icd10_tr.sql

# ICD-10 vektör veritabanını oluştur
python -m apps.backend.src.scripts.build_icd10_vectors
```


### 5. Frontend kurulumu

```bash
cd apps/frontend
npm install
```

---

## Çalıştırma

**Backend** (proje kök dizininden):

```bash
uvicorn apps.backend.src.main:app --reload --host 127.0.0.1 --port 8700
```

API: <http://127.0.0.1:8700> · Dokümantasyon: <http://127.0.0.1:8700/docs>

**Frontend** (`apps/frontend` dizininden):

```bash
npm run dev
```

Electron uygulaması açılır ve backend'e `127.0.0.1:8700` üzerinden bağlanır.

**Masaüstü uygulaması derleme:**

```bash
npm run build:win      # Windows
npm run build:mac      # macOS
npm run build:linux    # Linux
```

---

## Docker ile çalıştırma

`docker-compose.yml`, tek bir MariaDB üzerinde OpenEMR + KlinikAsistan veritabanını,
OpenEMR web arayüzünü ve (opsiyonel) backend'i ayağa kaldırır:

```bash
docker compose up -d mysql        # MariaDB (init script otomatik çalışır)
docker compose up -d openemr      # OpenEMR web UI → http://localhost:8300
docker compose up openemr-init openemr-sut-init   # (ops.) ICD-10 + SUT seed
```

GPU desteği için `docker-compose.gpu.yml` override dosyası kullanılır. Ayrıntılar
ve sık karşılaşılan sorunlar: [`docker/README.md`](docker/README.md).

---

## Hasta verisini içe aktarma (paylaşılan veritabanı dump'ı)

> **Önemli:** Hasta kayıtları (OpenEMR'deki hastalar, görüşme oturumları, raporlar)
> **depoda yer almaz** — git deposu yalnızca veritabanı şemasını ve ICD-10/SUT
> tohum verisini içerir. Bir klon kurulduğunda OpenEMR **boş** gelir.
>
> Hasta verisini paylaşmak için, ekipten biri MariaDB'yi tek bir `.sql` dosyasına
> döker; diğerleri bu dosyayı içe aktarır. Hastaları OpenEMR arayüzünden tek tek
> oluşturmaya gerek yoktur.

Önkoşul: Docker ve MariaDB container'ı çalışıyor olmalı (`docker compose up -d mysql`).

**Veriyi dışa aktarma (gönderen taraf):**

```bash
./scripts/db-export.sh
```

Script, `openemr` ve `klinikasistan` veritabanlarını
`data/dumps/klinik_dump_<tarih>.sql` adlı tek bir dosyaya döker. Bu dosya ekiple
paylaşılır (Drive, WeTransfer vb.).

**Veriyi içe aktarma (alan taraf):**

```bash
./scripts/db-import.sh data/dumps/klinik_dump_<tarih>.sql
```

Script onay ister; **mevcut tabloların üzerine yazar.** İçe aktarma bittikten sonra
backend çalışıyorsa yeniden başlatın (önbellek tazeleme için).

> Scriptler `klinikasistan-mysql-1` container adını bekler. Container adınız
> farklıysa (`docker ps` ile kontrol edin) script başındaki `CONTAINER=` satırını
> düzenleyin.

---

## OpenEMR (HBYS) entegrasyonu

OpenEMR ayarları ayrı bir dosyada tutulur (secret'lar `.gitignore`'da):

```bash
cp .env.openemr.example .env.openemr
```

`.env.openemr` içinde:
1. Kurulum senaryonuzu seçin — (A) Docker compose, (B) compose + host backend,
   (C) native XAMPP — ilgili bloğun yorumunu kaldırın.
2. OpenEMR yönetim panelinden OAuth client kaydı yapın
   (**Administration → System → API Clients**), çıkan `client_id` / `client_secret`
   değerlerini dosyaya yazın.

---

## Testler

```bash
# Backend birim testleri
pytest apps/backend/tests/ -v

# Uçtan uca pipeline testi
python test_e2e_pipeline.py

# RAG testi
python test_rag.py

# Frontend testleri
cd apps/frontend && npm test
```

---

## Proje yapısı

```
.
├── apps/
│   ├── backend/            # FastAPI backend
│   │   └── src/
│   │       ├── asr/        # Konuşma tanıma pipeline
│   │       ├── rag/        # Anamnez RAG (BGE-M3 + ChromaDB)
│   │       ├── routes/     # REST endpoint'leri
│   │       ├── services/   # LLM, ICD-10, SUT, OpenEMR, deid servisleri
│   │       ├── ws/         # WebSocket işleyicileri
│   │       └── main.py     # Uygulama giriş noktası
│   └── frontend/           # Electron + React masaüstü uygulaması
│       └── src/renderer/   # React arayüzü (sayfalar, bileşenler, store)
├── src/, config/           # Eski/temel ASR pipeline (değiştirilmez)
├── shared/                 # Katmanlar arası API sözleşmesi
├── docker/                 # MariaDB + OpenEMR init scriptleri
├── data/                   # Yerel SQLite/ChromaDB verisi (depoda yok, scriptlerle üretilir)
├── docs/                   # Araştırma ve değerlendirme raporları
├── bench_data/, bench_results/   # LLM/ASR kıyaslama verileri
├── scripts/                # Yardımcı scriptler
├── docker-compose.yml      # Docker stack tanımı
├── Dockerfile              # Backend imajı (CPU/GPU varyantlı)
├── environment.yml         # Conda ortamı
└── requirements-*.txt      # Python bağımlılıkları
```

---

## Dokümantasyon

`docs/` dizininde projenin geliştirme süreci, araştırma ve değerlendirme raporları
bulunur (ASR performansı, LLM pipeline, RAG ablation çalışmaları, diarization
hata ayıklama, ICD/SUT araştırma notları vb.).

---

## Lisans

Bu depo için ayrı bir lisans dosyası tanımlanmamıştır. Kullanım koşulları için
proje sahibiyle iletişime geçin.
