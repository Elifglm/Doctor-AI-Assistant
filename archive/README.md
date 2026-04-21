# archive/

Tek seferlik yardımcı script'lerin yedek dizini. **Üretim kodu değil** — `apps/backend/` veya `apps/frontend/` tarafından import edilmez, runtime'da çağrılmaz. Silmeden repo'da tutuyoruz çünkü ICD-10 backfill workstream'i bitmedi ve bu script'ler aynı veri kümesi üzerinde tekrar çalıştırılabilir.

Hepsi proje root'undan çalıştırılmak üzere yazıldı:

```
.venv/Scripts/python.exe archive/<script_adı>.py
```

## İçerik

| Script | Ne yapar |
|--------|----------|
| `prepare_reports.py` | `data/Anemnez_tetkik/` altındaki 38K anamnez Excel'inden 100 raporluk rastgele örneklem çıkarıp claude.ai'ye yapıştırmaya hazır JSON üretir. |
| `scan_anamnez_quality.py` | Aynı 38K dataset üzerinde alan-bazlı doluluk + uzunluk istatistiği çıkarır; "gold" alt-küme eşiğini seçmek için. |
| `test_ner_pipeline.py` | Mock bir dahiliye transkripti üzerinde NER → De-ID → LLM batch prompt zincirini uçtan-uca çalıştırıp çıktıları basar. Backend değişikliklerinden sonra manuel sağlık kontrolü için. |

## Bağımlılıklar

`prepare_reports.py` ve `scan_anamnez_quality.py`, `data/Anemnez_tetkik/IcAnemnez.xlsx` + `Tetkik.xlsx` dosyalarını bekler. Bu dosyalar PHI içerdiği için `.gitignore`'da — repo'da yok, yerel olarak sağlanmalı.
