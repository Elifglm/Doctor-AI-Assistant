# ICD-10 Backfill Rehberi — claude.ai Projects

100 anamnez raporunu Türkiye ICD-10 kodlarıyla zenginleştirmek için adım adım rehber.

## Hazırlanan Dosyalar

Proje kökünde aşağıdaki dosyalar `prepare_reports.py` ile üretildi:

- `icd10_export.csv` — 9,296 spesifik ICD-10 kodu (seviye ≥ 2)
- `reports_for_claude.json` — 100 random rapor, anamnez + tetkik birleştirilmiş
- `batch_1.json` ... `batch_5.json` — her biri 20 rapor

**Dataset özeti:** `data/Anemnez_tetkik/IcAnemnez.xlsx` (38,222 satır × 48 sütun) + `Tetkik.xlsx` (51,399 satır, `FORM_ID` üzerinden join). 500 satırlık PHI taraması temiz — veri anonim.

---

## Adım 1 — Dosyaları local PC'ye indir

claude.ai browser'da açılacağı için dosyaların local'de olması gerek.

### VS Code Remote-SSH ile (önerilen)

Sol Explorer paneli → `icd10_export.csv` ve `batch_*.json` dosyalarına sağ tıkla → **Download...**

### scp ile (alternatif)

Local PowerShell'de:

```powershell
scp furkan@100.70.112.125:/c/Users/Furkan/Documents/GitHub/KlinikAsistan/icd10_export.csv .
scp "furkan@100.70.112.125:/c/Users/Furkan/Documents/GitHub/KlinikAsistan/batch_*.json" .
```

## Adım 2 — claude.ai'de Project oluştur

1. [claude.ai](https://claude.ai) aç → sol menüden **Projects** → **Create project**
2. İsim: `Türkiye ICD-10 Backfill`
3. Açıklama: `Türkçe anamnez raporlarından ICD-10 kodu önerme`
4. Model: **Claude Opus 4.7** (sağ üst dropdown)

## Adım 3 — ICD-10 listesini knowledge olarak yükle

**Project knowledge** paneli → **Add content** → **Upload file** → `icd10_export.csv`

Yükleme sonrası "9,296 rows" gösterir. Bu liste Claude'un her sorguda otomatik context'ine girer.

## Adım 4 — Project instructions yaz

**Set project instructions** alanına yapıştır:

```
Sen Türkiye Sağlık Bakanlığı ICD-10 kodlamasında uzman bir tıbbi kodlayıcısın.
Türkçe doktor anamnez raporlarını okuyup uygun ICD-10 kodlarını öneriyorsun.

KURALLAR:
1. ICD-10 kodlarını SADECE yüklenmiş icd10_export.csv dosyasındaki listeden seç.
   Listede olmayan hiçbir kod önerme — uydurma, tahmin etme.
2. Her anamnez için 1-3 arası en uygun kod öner. Birincil tanı en başta.
3. Spesifiklik için alt kodu tercih et: E11 yerine E11.9 (en detaylı mevcut kod).
4. Gerekçeyi kısa tut: 1 cümle, anamnezden somut alıntı içersin.
5. Güven seviyesi: "yuksek" (net tanı), "orta" (güçlü ipucu), "dusuk" (sadece semptom düzeyinde).
6. Sadece semptom varsa R kodları (semptom kodları) tercih et, uydurma hastalık tanısı koyma.
7. Tetkik listesi (TETKIK/HIZMET) ve vitaller tanıyı destekleyici ipucu — ağır tahliller + yüksek AKŞ → diyabet gibi.

CIKTI FORMATI: Sadece JSON dizisi döndür, başka metin yok:
[
  {
    "id": "r001",
    "codes": [
      {"kod": "E11.9", "tani": "Tip 2 diyabetes mellitus, komplikasyonsuz", "guven": "yuksek", "gerekce": "AKŞ:377, HbA1c:14.94, Galvus başlandı"},
      {"kod": "N39.0", "tani": "İdrar yolu enfeksiyonu", "guven": "orta", "gerekce": "idrar yaparken yanma"}
    ]
  }
]
```

## Adım 5 — İlk batch'i gönder

Yeni bir chat aç (project içinden). Şunu gönder:

```
Aşağıda 20 anamnez raporu var. Her biri için ICD-10 kodu öner.
Proje instructions'ındaki kurallara uy. Sadece JSON dizisi döndür.

<batch_1.json dosyasının içeriğini buraya yapıştır>
```

Çıktıyı kopyala → `claude_output_batch_1.json` olarak local'e kaydet.

## Adım 6 — Kalan 4 batch için tekrarla

Aynı chat'te devam et:

```
Batch 2. Aynı format.

<batch_2.json içeriği>
```

Her batch ~1-2 dk sürer. Toplam 5 batch ≈ 10 dk.

## Adım 7 — Sonuçları birleştir ve doğrula

5 çıktı dosyasını birleştirip halüsinasyon kontrolü için doğrulama script'i çalıştır (ayrıca hazırlanacak). Invalid kod varsa raporla, değerlendir.

---

## Faydalı Notlar

- **Artifact kullanma** — JSON doğrudan mesajda dönsün (kopyalama kolay)
- **İlk batch'i gözle kontrol et** — prompt tuning gerekirse oradan düzelt, sonra devam et
- **"Extended thinking"** opsiyonu varsa aç (ICD seçimi çok adımlı reasoning gerektirir)
- **KVKK:** Veri anonim (isim/TC/telefon yok) — bu tur raporlar için claude.ai güvenli
- **100 ötesi için:** `prepare_reports.py` içindeki `SAMPLE_SIZE` arttır. 38K rapor için claude.ai manuel batch imkansız → API batch veya local `icd10_suggestion_service.py` gerekir.

## Pipeline Mimarisi

```
IcAnemnez.xlsx (38K) ──┐
                       ├─► prepare_reports.py ──► reports_for_claude.json (100)
Tetkik.xlsx (51K) ─────┘        [FORM_ID join]     └─► batch_1..5.json

icd10.db (11,332 kod) ──► icd10_export.csv (9,296)

claude.ai Projects:
  icd10_export.csv (knowledge) + batch_N.json (chat) ──► ICD önerileri JSON
```
