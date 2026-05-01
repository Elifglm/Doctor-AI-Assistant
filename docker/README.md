# Docker Stack — Setup & Troubleshooting

Bu dosya `docker-compose.yml`'deki servislerin ilk kurulum, yaygın sorunlar ve
ekip içi senkronizasyon notlarını içerir. AI (Claude Code) ve yeni ekip üyesi
için referans.

## Mimari Özet

```
docker-compose.yml
├── mysql (MariaDB 10.11)            ← tek instance, IKI database
│    ├── openemr (DB)                ← OpenEMR'in hastalari
│    └── klinikasistan (DB)          ← KlinikAsistan backend verisi
│         (users, sessions, reports, transcription_segments, audit_log)
├── openemr (web UI :8300)
├── backend (FastAPI :8700)          ← prod-like; dev'de uvicorn ile direkt calistirilir
├── openemr-init (one-shot)          ← ICD-10 TR seed
└── openemr-sut-init (one-shot)      ← SUT tetkik seed
```

**Volume'lar:**
- `openemr_mysql` → MariaDB veri dosyalari (silinirse iki DB de kaybolur!)
- `openemr_data` → OpenEMR site/config dosyalari

**Port mapping:**
| Servis | Host port | Container port |
|--------|-----------|----------------|
| mysql | **3307** | 3306 |
| openemr (HTTP) | 8300 | 80 |
| openemr (HTTPS) | 9300 | 443 |
| backend | 8700 | 8700 |

> Host port 3307 secilmistir cunku 3306 cogu makinede zaten dolu olabilir
> (lokal MySQL/MariaDB kurulumu).

---

## İlk Kurulum (yeni makinede)

### 1. Servisleri başlat
```bash
docker compose up -d mysql        # MariaDB + init_klinikasistan.sql otomatik
docker compose up -d openemr      # OpenEMR (~30sn-1dk)
```

### 2. (Opsiyonel) ICD-10 + SUT seed OpenEMR'a yükle
```bash
docker compose up openemr-init openemr-sut-init
```

### 3. Backend'i dev modda başlat (host'ta)
```bash
source venv/bin/activate
python -m uvicorn apps.backend.src.main:app --reload --host 127.0.0.1 --port 8700
```

`.env` icinde `DATABASE_URL=mysql+asyncmy://klinik:klinik@127.0.0.1:3307/klinikasistan`
varsa MariaDB'ye baglanir; yoksa SQLite fallback (`data/asr.db`).

---

## Yaygın Sorunlar ve Çözümler

### 1. `address already in use` — port çakışması
**Belirtisi:**
```
Error response from daemon: ports are not available: ... bind: address already in use
```

**Sebebi:** Host'ta zaten MySQL/MariaDB çalışıyor (Homebrew, system service, eski Docker container).

**Çözümler:**
- Lokal MySQL'i durdur: `brew services stop mysql` veya `brew services stop mariadb`
- Çakışan Docker container varsa: `docker ps -a --filter "publish=3307"` ile bul, durdur
- Veya `docker-compose.yml`'de port mapping'i değiştir: `"3308:3306"` gibi
  (sonra `.env`'deki DATABASE_URL'i de güncelle)

### 2. `init_klinikasistan.sql` çalışmadı (klinikasistan DB yok)
**Belirtisi:** `docker exec mysql ... SHOW DATABASES` çıktısında `klinikasistan` yok.

**Sebebi:** Docker'ın `/docker-entrypoint-initdb.d/` script'leri **sadece volume boşken** çalışır. Volume daha önce başka bir kurulumdan kalmışsa atlanır.

**Çözüm:** Manuel çalıştır:
```bash
docker exec -i klinikasistan-mysql-1 mariadb -uroot -proot \
  < docker/mariadb/init_klinikasistan.sql
```

### 3. Backend MariaDB'ye bağlanamıyor
**Belirtisi (logda):**
```
sqlalchemy.exc.OperationalError: ... Can't connect to MySQL server
```

**Kontroller:**
```bash
# MariaDB ayakta mı?
docker ps | grep mysql

# klinik user ile bağlanabiliyor muyuz?
docker exec klinikasistan-mysql-1 mariadb -uklinik -pklinik klinikasistan -e "SHOW TABLES;"

# .env'de DATABASE_URL doğru mu?
grep DATABASE_URL .env
```

`.env` doğru ama bağlanmıyorsa: backend'i yeniden başlat (env yeniden okunur).

### 4. OpenEMR'a giriş yapamıyorum / "Database error"
**Sebebi:** Volume init sırasında OpenEMR setup wizard'ı tam tamamlanmamış olabilir.

**Sıfırla (DİKKAT: tüm veri silinir!):**
```bash
docker compose down -v          # volume'lar dahil her şey silinir
docker compose up -d
# 1-2 dakika bekle (OpenEMR ilk kurulumu yapıyor)
docker compose up openemr-init openemr-sut-init
```

### 5. Pydantic `extra_forbidden` error (DATABASE_URL)
**Belirtisi:**
```
ValidationError: 1 validation error for AppSettings
database_url - Extra inputs are not permitted
```

**Sebebi:** `config/settings.py`'de `AppSettings` `extra="ignore"` ayarı eksik.

**Çözüm:** `model_config` içine `extra="ignore"` eklenmiş olmalı. Bu repo'da
zaten ayarlı, ama branch arası rebase sırasında düşmüş olabilir.

---

## Ekip Senkronizasyonu

### Şema değişikliği (otomatik, Git üzerinden)
Backend kodunda `db/models.py` değişirse:
- Sen: `git push`
- Arkadaşın: `git pull` → backend'i restart → yeni tablolar `Base.metadata.create_all` ile otomatik oluşur

> Production'da Alembic migration kullanmak daha güvenli ama bu proje için
> şu an yeterli.

### Veri paylaşımı (manuel, dump üzerinden)

**Sen (export):**
```bash
docker exec klinikasistan-mysql-1 mariadb-dump -uroot -proot \
  --databases openemr klinikasistan > klinik_dump.sql
# klinik_dump.sql'i Whatsapp/Drive ile gönder
```

**Arkadaşın (import):**
```bash
# Önce servislerin ayakta olduğundan emin ol
docker compose up -d mysql openemr

# Sonra dump'ı yükle
docker exec -i klinikasistan-mysql-1 mariadb -uroot -proot < klinik_dump.sql

# Backend'i restart et (cache invalidation için)
```

### Tam reset + ekip dump'ı yükleme
```bash
docker compose down -v
docker compose up -d mysql
# init_klinikasistan.sql otomatik çalışır
docker exec -i klinikasistan-mysql-1 mariadb -uroot -proot < klinik_dump.sql
docker compose up -d openemr backend
```

---

## Erişim Bilgileri (DEV ortamı, production'da DEĞİŞTİRİLMELİ)

| Servis | URL | Kullanıcı | Şifre |
|--------|-----|-----------|-------|
| OpenEMR | http://localhost:8300 | admin | pass |
| MariaDB (root) | 127.0.0.1:3307 | root | root |
| MariaDB (klinik) | 127.0.0.1:3307/klinikasistan | klinik | klinik |
| MariaDB (openemr) | 127.0.0.1:3307/openemr | openemr | openemr |
| Backend | http://127.0.0.1:8700 | (JWT) | (JWT) |
| Backend seed users | — | admin / doktor1 / doktor2 | (kod tabanında) |

---

## KVKK / Güvenlik Notları

- Bu kurulum **on-premise** (lokal Docker). Hiçbir veri cloud'a gitmez.
- Default şifreler (`root`, `pass`, `klinik`) **sadece dev içindir**.
- Production deployment yapılırsa:
  - Tüm şifreler değiştirilmeli
  - MariaDB portu (3307) firewall ile kapatılmalı
  - OpenEMR HTTPS sertifikası kurulmalı
  - `.env` 600 izinleriyle korunmalı

## Hızlı Komut Referansı

```bash
# Servisler
docker compose up -d mysql openemr backend
docker compose down                  # durdur (data kalır)
docker compose down -v               # durdur + volume sil (data kaybedilir!)
docker compose ps                    # çalışan servisler

# Loglar
docker compose logs -f mysql
docker compose logs -f openemr

# DB shell
docker exec -it klinikasistan-mysql-1 mariadb -uklinik -pklinik klinikasistan
docker exec -it klinikasistan-mysql-1 mariadb -uroot -proot openemr

# Tablo durumu
docker exec klinikasistan-mysql-1 mariadb -uklinik -pklinik klinikasistan -e "SHOW TABLES;"
```
