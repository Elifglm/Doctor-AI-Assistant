# Doctor AI Assistant - Kapsamli Test Senaryolari

> 5 farkli perspektiften hazirlanmis, toplam 222 test senaryosu.
> Tarih: 2026-03-01
> Son guncelleme: 2026-03-01
>
> **Sonuc: 222/222 senaryo incelendi, 215 PASS, 4 ERTELENDI, 3 TASARIM GEREGI**
> Tum kritik bulgular (B1-B5, S1-S7, U1-U5) cozuldu veya degerlendirildi.

---

## Icerik

1. [Temel Kullanici Akisi (Mutlu Yol)](#1-temel-kullanici-akisi)
2. [Hata ve Edge Case Senaryolari](#2-hata-ve-edge-case-senaryolari)
3. [UI/UX Tutarliligi](#3-uiux-tutarliligi)
4. [State Yonetimi ve Veri Akisi](#4-state-yonetimi-ve-veri-akisi)
5. [Guvenlik ve KVKK Uyumlulugu](#5-guvenlik-ve-kvkk-uyumlulugu)

---

# 1. Temel Kullanici Akisi

## 1.1 Login Sayfasi

| # | Senaryo | Beklenen Davranis |
|---|---------|-------------------|
| 1 | admin/admin ile giris | Dashboard'a yonlendirilmeli, token kaydedilmeli |
| 2 | Bos kullanici adi ile giris | HTML5 required validasyon engellenmeli |
| 3 | Bos sifre ile giris | HTML5 required validasyon engellenmeli |
| 4 | Yanlis kimlik bilgileri | "Giris sirasinda bir hata olustu" mesaji goruntulenmeli |
| 5 | Loading durumu | Buton disabled + spinner goruntulenmeli |
| 6 | Basarili giris URL | Hash-tabanli routing ile `#/` (Dashboard) adresine yonlendirilmeli |

## 1.2 Dashboard Sayfasi

| # | Senaryo | Beklenen Davranis |
|---|---------|-------------------|
| 7 | Dashboard acilisi | "Ana Sayfa" basligi, istatistik bari, son 10 gorusme listesi goruntulenmeli |
| 8 | "Yeni Gorusme Baslat" butonu | `/session/new` sayfasina yonlendirilmeli |
| 9 | Gecmis gorusmeler yuklemesi | API'den son gorusmeler yuklenmeli (limit:10, sort:created_at:desc) |
| 10 | Bos gorusme durumu | "Henuz gorusme bulunmuyor" mesaji + "Ilk gorusmenizi baslatin" linki |
| 11 | Gorusme sayilari | Bugunku, beklemede olan, tamamlanan sayilar dogru hesaplanmali |
| 12 | Gorusme kartina tiklama | NOT_STARTED/RECORDING → `/session/{id}/live`, PROCESSING → `/session/{id}/processing`, AWAITING_REVIEW/COMPLETED → `/session/{id}/review` |
| 13 | Hata durumu | Kirmizi hata banneri "Gorusmeler yuklenirken hata olustu" goruntulenmeli |

## 1.3 Yeni Gorusme (Pre-Session) Sayfasi

| # | Senaryo | Beklenen Davranis |
|---|---------|-------------------|
| 14 | Sayfa acilisi | Hasta ID, Ziyaret Tipi, Doktor Adi, On Tani, Konum, KVKK Onay alanlari goruntulenmeli |
| 15 | Doktor adi otomatik doldur | Giris yapmis kullanicinin display_name'i otomatik doldurulmali |
| 16 | Ziyaret tipi secenekleri | Ilk Muayene, Kontrol, Konsultasyon, Acil secenekleri goruntulenmeli |
| 17 | KVKK onay zorunlulugu | KVKK checkbox isaretlenmeden "Kaydi Baslat" disabled olmali |
| 18 | KVKK checkbox tiklama | Isaretlenince buton enabled olmali |
| 19 | Hasta ID opsiyonel | Bos birakildigi durumda kayit yapilabilmeli |
| 20 | On Tani ve Konum opsiyonel | Bos birakilabilmeli |
| 21 | Kayit baslatma | POST /api/v1/sessions sonrasi `/session/{id}/live` sayfasina yonlendirme |
| 22 | Loading durumu | Spinner + disabled buton |
| 23 | Hata goruntuleme | Kirmizi hata alert'i goruntulenmeli |

## 1.4 Canli Oturum - Kayit Asamasi

| # | Senaryo | Beklenen Davranis |
|---|---------|-------------------|
| 24 | Otomatik kayit baslat | Sayfa acildiginda startRecording() otomatik calistirilmali |
| 25 | Kayit kontrolleri | RecordingControls bileseni goruntulenmeli |
| 26 | Kayit durumu gostergesi | Kirmizi pulse: "Kayit yapiliyor", Sari: "Duraklatildi", Gri: "Bekleniyor" |
| 27 | Gecen zaman sayaci | MM:SS formatinda gercek zamanli guncellenmeli |
| 28 | Ses seviyesi metre | Audio level meter gelen ses seviyesine gore degismeli |
| 29 | Bilgi banner | "Kaydi durdurunca isleme baslanacak" mavi banner goruntulenmeli |
| 30 | Duraklat butonu | Kayit yapilirken "Duraklat" ikonu goruntulenmeli |
| 31 | Devam et butonu | Duraklatilmis durumda "Devam et" ikonu goruntulenmeli |
| 32 | Kaydi durdur butonu | Her zaman gorunur, tiklayinca islemeye gecmeli |
| 33 | Transkript goruntulenmesi | Kayit sirasinda segmentler goruntulenmeli |

## 1.5 Canli Oturum - Isleme Asamasi

| # | Senaryo | Beklenen Davranis |
|---|---------|-------------------|
| 34 | Kayit durdurulduktan sonra | recordingState "processing" olmali, islem UI goruntulenmeli |
| 35 | Processing overlay | Spinner + "Isleniyor" basligi + asama metni |
| 36 | Asama gostergeleri | 6-7 adet stage indicator bar goruntulenmeli |
| 37 | Asama numarasi | "Asama X/7" metni goruntulenmeli |
| 38 | Ilerleme cubugu | 0%-100% progress bar goruntulenmeli |
| 39 | Yuzde gosterimi | Yuzde degeri guncellenmeli |
| 40 | Islem tamamlaninca | Otomatik olarak `/session/{id}/review` sayfasina yonlendirme (500ms delay) |
| 41 | Asama etiketleri | Stage 0: Dosya dogrulaniyor, Stage 1: Gurultu bastirma, Stage 2: Transkripsiyon, Stage 3: Konusmaci ayristirma, Stage 4+: NER/LLM/Kaydetme |

## 1.6 Rapor Inceleme Sayfasi

| # | Senaryo | Beklenen Davranis |
|---|---------|-------------------|
| 42 | Split panel layout | Sol: Transkript, Sag: Rapor, Orta: Ayarilabilir divider |
| 43 | Divider tasima | Mouse drag ile sol/sag panel genisligi degistirilmeli (min 25%, max 75%) |
| 44 | Transkript segmentleri | Konusmaci bilgisi, zaman dilimi, metin; tiklayinca secim highlight |
| 45 | Header bar | Geri butonu, oturum bilgisi, hasta bilgisi, AI olustur butonu |
| 46 | Rapor varsa | ReportEditor goruntulenmeli |
| 47 | Rapor yoksa | "Henuz rapor olusturulmamis" + AI/Bos Sablon butonlari |
| 48 | AI rapor olusturma | POST /api/v1/reports {method:'ai_generated'} → rapor editor goruntulenmeli |
| 49 | Bos rapor olusturma | POST /api/v1/reports → bos sablon acilmali |
| 50 | AI butonu disable | Transkript yoksa disabled + uyari mesaji |
| 51 | Hata mesajlari | Kirmizi alert "Rapor olusturulamadi" goruntulenmeli |

## 1.7 Rapor Editor

| # | Senaryo | Beklenen Davranis |
|---|---------|-------------------|
| 52 | Bolum goruntulenmesi | Tum rapor seksiyonlari ReportSection kartlarinda goruntulenmeli |
| 53 | Onaylanan bolum sayisi | "X/Y bolum onaylandi" metni goruntulenmeli |
| 54 | Bolum duzenlemesi | Metin alanina tiklayinca editable olmali |
| 55 | Degisiklik izleme | Metin degistirildiginde status "edited" olmali |
| 56 | Bolum onayla | "Onayla" butonu ile status "approved" olmali |
| 57 | Taslak kaydet | PUT /api/v1/reports/{id} ile guncel seksiyonlar gonderilmeli |
| 58 | Tumunu onayla | Tum bolumler "approved" yapilmali, PUT {status:'APPROVED'} gonderilmeli |
| 59 | Tumunu onayla disable | Tumu onayliysa buton disabled olmali |
| 60 | Kayit basarisi | "Kaydedildi" yesil mesaji goruntulenmeli |
| 61 | Kayit hatasi | "Kaydetme hatasi" kirmizi mesaji goruntulenmeli |

## 1.8 Oturum Gecmisi Sayfasi

| # | Senaryo | Beklenen Davranis |
|---|---------|-------------------|
| 62 | Sayfa acilisi | "Gorusme Gecmisi" basligi goruntulenmeli |
| 63 | Filtreler | Durum dropdown, Arama input, Baslangic/Bitis tarihi goruntulenmeli |
| 64 | Tablo sutunlari | Tarih, Doktor Adi, Ziyaret Tipi, Durum, Sure goruntulenmeli |
| 65 | Durum filtresi | Secim yapilinca sayfa=1'e sifirlanmali, filtrelenmeli |
| 66 | Arama | Metin yazilinca search parametresi ile filtrelenmeli |
| 67 | Tarih filtresi | from_date/to_date parametreleri ile filtrelenmeli |
| 68 | Sayfalama | 15/sayfa, Onceki/Sonraki butonlari goruntulenmeli |
| 69 | Sayfalama buton disabled | Sayfa 1'de Onceki disabled, son sayfada Sonraki disabled |
| 70 | Tablo satir tiklama | Status'e gore ilgili sayfaya yonlendirme |
| 71 | Ziyaret tipi etiketleri | Turkce goruntulenmeli (Ilk Muayene, Kontrol, vs.) |
| 72 | Sure formatlama | "45dk 30sn" veya "-" (null ise) |
| 73 | Bos tablo | "Gorusme bulunamadi" + "Filtrelerinizi degistirmeyi deneyin" |
| 74 | Sayfa bilgisi | "Toplam X gorusme, Sayfa Y/Z" goruntulenmeli | ✅ Duzeltildi: tek sayfada da toplam gosteriliyor |

## 1.9 Ayarlar Sayfasi

| # | Senaryo | Beklenen Davranis |
|---|---------|-------------------|
| 75 | Tab navigasyonu | Profil, Ses, LLM, Sablonlar, Goruntu, Gizlilik tablari |
| 76 | Profil tabi | Gorunen Ad, Kullanici Adi, Rol (read-only) |
| 77 | Ses tabi | Mikrofon Secimi dropdown, ses cihazlari listesi |
| 78 | LLM tabi | Ollama durumu, model bilgisi, RAG doc count, GPU info |
| 79 | Baglanti testi | Health endpoint sorgulanmali, durumlar yenilenmeli |
| 80 | Sablonlar tabi | "Yakin zamanda eklenecek" placeholder |
| 81 | Goruntu tabi | Tema toggle (Acik/Koyu), Yazi boyutu slider (14-24px) |
| 82 | Gizlilik tabi | KVKK aciklamasi, "Tum verileri sil" butonu + onay dialogu |

## 1.10 Sidebar Navigasyon

| # | Senaryo | Beklenen Davranis |
|---|---------|-------------------|
| 83 | Nav itemleri | Ana Sayfa, Yeni Gorusme, Gecmis, Ayarlar goruntulenmeli |
| 84 | Aktif sayfa highlight | Mevcut sayfanin nav item'i vurgulanmali |
| 85 | Cikis butonu | En altta "Cikis Yap" butonu, tiklayinca logout + login sayfasina yonlendirme |
| 86 | Kayit uyarisi | Kayit yapiliyorken baska sayfaya gitmek veya cikis yapmak isterse onay dialogu gostermeli | ✅ Duzeltildi: logout butonu da guard iceriyor |

## 1.11 Kayit Akisi Detay

| # | Senaryo | Beklenen Davranis |
|---|---------|-------------------|
| 87 | Kayit → Duraklat | Indicator sari, "Duraklatildi" metni, "Devam et" butonu |
| 88 | Duraklat → Devam | Indicator kirmizi pulse, "Kayit yapiliyor" metni, "Duraklat" butonu |
| 89 | Kaydi durdur | RecordingControls kaybolmali, Processing overlay goruntulenmeli |

## 1.12 Tam E2E Mutlu Yol

| # | Senaryo |
|---|---------|
| 90 | Login → Dashboard → Yeni Gorusme Baslat → Form doldur (Hasta ID, Ziyaret Tipi, KVKK) → Kaydi Baslat → 5-10sn kayit → Duraklat → Devam → Durdur → Processing tamamlaninca → Report Review → AI ile Olustur → Bolum onayla → Taslak Kaydet → Tumunu Onayla → Gecmis → Oturuma tikla → Report Review goruntulenmeli |

---

# 2. Hata ve Edge Case Senaryolari

## 2.1 Ag Hatalari (Network Errors)

| # | Sayfa | Senaryo | Beklenen Davranis |
|---|-------|---------|-------------------|
| 91 | Login | Backend kapaliyken giris denemesi | "Giris sirasinda bir hata olustu" mesaji, buton enabled'a donmeli |
| 92 | PreSession | Session olusturma sirasinda timeout | Kirmizi hata banner, buton tekrar tiklanabilir olmali |
| 93 | ReportReview | Session yukleme sirasinda 500 error | "Oturum yuklenemedi" mesaji + hata detayi |
| 94 | SessionHistory | Oturum listesi yuklerken API hatasi | "Gorusmeler yuklenirken hata olustu" mesaji |
| 95 | Tum sayfalar | 401 Unauthorized yaniti | Otomatik logout, login sayfasina yonlendirme |
| 96 | LiveSession | WS baglantisi kesilirse (network kesintisi) | Max 3 retry (exponential backoff), basarisizsa "Baglanti kesildi" hatasi + Tekrar Dene butonu | ✅ Duzeltildi: auto-reconnect eklendi |
| 97 | ReportReview | AI Report uretimi cok uzun surerse | Spinner devam etmeli, buton disabled kalmali |

## 2.2 Gecersiz Girisler (Invalid Inputs)

| # | Sayfa | Senaryo | Beklenen Davranis |
|---|-------|---------|-------------------|
| 98 | Login | Bos username/password gonderimi | HTML5 required validation engellemeli |
| 99 | PreSession | KVKK onaylanmadan submit | Buton disabled, form gonderilmemeli |
| 100 | PreSession | 50.000 karakterlik on tani metni | Backend Pydantic validasyon hatasi donmeli |
| 101 | PreSession | Turkce ozel karakterler (c,s,g,u,o,i) | UTF-8 encoding dogru calismalı |
| 102 | SessionHistory | SQL injection denemesi arama alaninda | Backend parameterized query kullanmali |

## 2.3 Mikrofon Hatalari

| # | Senaryo | Beklenen Davranis |
|---|---------|-------------------|
| 103 | Mikrofon izni reddedildi (NotAllowedError) | "Mikrofon erisimi reddedildi. Lutfen mikrofon iznini kontrol edin." |
| 104 | Mikrofon bulunamadi (NotFoundError) | "Mikrofon bulunamadi. Lutfen bir mikrofon baglayip tekrar deneyin." |
| 105 | Ses format desteklenmiyor (NotSupportedError) | "Ses kayit formati desteklenmiyor." |
| 106 | Mikrofon mid-recording kesilmesi | onError callback ile kullaniciya hata gosteriliyor (B1 fix) | ✅ |

## 2.4 WebSocket Kesintileri

| # | Senaryo | Beklenen Davranis |
|---|---------|-------------------|
| 107 | Recording sirasinda WS kesilmesi | recordingState idle'a donmeli, hata mesaji gosterilmeli |
| 108 | Processing sirasinda WS kesilmesi | "Baglanti kesildi. Islem tamamlanamadi." mesaji |
| 109 | Max reconnect attempts asilmasi | "Baglanti kesildi. Maksimum yeniden baglanma denemesi asildi." mesaji | ✅ Duzeltildi |

## 2.5 Cift Tiklama / Hizli Buton Basilmasi

| # | Sayfa | Senaryo | Beklenen Davranis |
|---|-------|---------|-------------------|
| 110 | Login | Login butonuna cift tiklama | disabled={loading} ile korunuyor ✓ |
| 111 | PreSession | "Kaydi Baslat" cift tiklama | disabled={isPending} ile korunuyor ✓ |
| 112 | ReportReview | "AI ile Olustur" hizli tiklamalar | disabled={isPending} ile korunuyor ✓ |
| 113 | LiveSession | "Tekrar Dene" hizli tiklamalar | callGeneration ile stale call detection ✓ |

## 2.6 Browser Back/Forward Navigasyonu

| # | Senaryo | Beklenen Davranis |
|---|---------|-------------------|
| 114 | Recording sirasinda back | useRecording cleanup tetiklenmeli, audio/WS kapatilmali |
| 115 | Processing sirasinda back | cleanup() tetiklenmeli, backend'deki processing durumu kontrol edilmeli |
| 116 | Report Review'da back | React Query cache'den veri donmeli |

## 2.7 Ozel Durumlar

| # | Senaryo | Beklenen Davranis |
|---|---------|-------------------|
| 117 | Segment olmayan session'da AI rapor | Buton disabled olmali + "AI rapor olusturmak icin transkript gereklidir" uyarisi |
| 118 | Segment olmadan bos sablon | generateReport.mutate() ile bos rapor olusturulmali |
| 119 | Cok kisa kayit (<1 saniye) | Backend FFmpeg/ASR hatasi donmeli, kullaniciya gosterilmeli |
| 120 | Cok uzun kayit (2+ saat) | Memory consumption ve WS timeout kontrol edilmeli |
| 121 | Multi-tab ayni session | 4 katmanli koruma eklendi (B2 fix) | ✅ |
| 122 | localStorage cross-tab sync | Electron tek pencere, sorun degil (B3) | ⚠ |
| 123 | Progress > 100% | Math.min(..., 100) ile cap eklendi (B4 fix) | ✅ |

---

# 3. UI/UX Tutarliligi

## 3.1 Yukleme Durumlari (Loading States)

| # | Konum | Kontrol |
|---|-------|---------|
| 124 | Dashboard gorusmeler | Spinner + "Gorusmeler yukleniyor..." metni gosterilmeli |
| 125 | ReportReview oturum yukleme | Merkezde spinner + "Oturum yukleniyor..." gosterilmeli |
| 126 | SessionHistory tablo yukleme | Spinner gosterilmeli, sayfalama disabled olmali |
| 127 | Settings LLM baglanti testi | Buton disabled + spinner, sonuc guncellenmeli |

## 3.2 Bos Durum Alanlari (Empty States)

| # | Konum | Kontrol |
|---|-------|---------|
| 128 | Dashboard sifir gorusme | "Henuz gorusme bulunmuyor" + "Ilk gorusmenizi baslatin" linki |
| 129 | SessionHistory bos filtre | "Gorusme bulunamadi" + "Filtrelerinizi degistirmeyi deneyin" |
| 130 | ReportReview rapor yok | "Henuz rapor olusturulmamis" + AI/Bos Sablon butonlari |
| 131 | TranscriptView bos | "Henuz transkript yok. Kayit devam ediyor..." |

## 3.3 Buton Durumlari

| # | Konum | Kontrol |
|---|-------|---------|
| 132 | Login butonu | Loading sirasinda disabled + spinner |
| 133 | Kaydi Baslat | KVKK unchecked ise disabled |
| 134 | Tumunu Onayla | Tumu onayliysa disabled |
| 135 | Sayfalama Onceki/Sonraki | Ilk/son sayfada disabled |
| 136 | Hover efektleri | Tum butonlar hover'da 1 shade koyu olmali |

## 3.4 Renk Tutarliligi

| # | Kategori | Renk | Kullanim |
|---|----------|------|----------|
| 137 | Basari/Onay | Emerald-600 | Kaydi Baslat, Onayla, Tumunu Onayla |
| 138 | AI Islemi | Violet-600 | AI ile Olustur, AI ile Yeniden Olustur |
| 139 | Uyari | Amber-50/700 | Duzenlendi status, permission warning |
| 140 | Hata | Red-50/600 | Hata bannerlari, kayit gostergesi |
| 141 | Bilgi | Blue-600 | Giris Yap, info banner |
| 142 | Doktor/Hasta | Blue-600 / Emerald-600 | Transcript segmentlerde border rengi |

## 3.5 Tipografi Tutarliligi

| # | Sorun | Detay |
|---|-------|-------|
| 143 | Font weight hiyerarsisi | text-2xl+font-bold (sayfa), text-lg+font-semibold (bolum) - kasitli hiyerarsi | ⚠ U2 ertelendi |
| 144 | Baslik boyutlari | text-2xl (sayfa basliklari), text-lg (bolum basliklari), text-sm (form labels) |
| 145 | Text overflow | Uzun doktor adlari/hasta ID'leri truncate olmali |

## 3.6 Turkce Metin Sorunlari

| # | Sorun | Detay |
|---|-------|-------|
| 146 | Turkce karakter duzeltmesi | U1 fix ile 10 dosyada 30+ Turkce karakter duzeltildi | ✅ |
| 147 | Terminoloji | "Gorusme" (kullanici-facing) ve "oturum" (teknik) baglama gore kullaniliyor | ✅ |
| 148 | Noktalama | Basliklar noktasiz, mesajlar noktali - tutarli | ✅ |

## 3.7 Scroll Davranisi

| # | Konum | Kontrol |
|---|-------|---------|
| 149 | TranscriptView | Auto-scroll to bottom, "Canli metne don" butonu scroll up'da gorulmeli |
| 150 | ReportEditor | Section'lar scroll'lanabilir olmali (overflow-auto) |
| 151 | Settings tab content | Uzun icerik scroll'lanabilir olmali |

## 3.8 Animasyonlar

| # | Konum | Kontrol |
|---|-------|---------|
| 152 | Sidebar acma/kapatma | transition-all duration-300 smooth olmali |
| 153 | Progress bar | transition-all duration-500 ease-out smooth olmali |
| 154 | Recording indicator | animate-pulse kirmizi pulse olmali |
| 155 | Tab gecisleri | fadeIn 150ms animasyon eklendi (U4 fix) | ✅ |

## 3.9 Toast/Bildirim Geri Bildirimi

| # | Tur | Konum | Kontrol |
|---|-----|-------|---------|
| 156 | Basari | ReportEditor kaydet | "Kaydedildi" yesil metni goruntulenmeli |
| 157 | Hata | ReportEditor kaydet | "Kaydetme hatasi" kirmizi metni |
| 158 | Hata | API hatalari | Alert card (red-50 bg, AlertCircle icon) |
| 159 | Bilgi | LiveSession | Mavi banner "Kaydi durdurunca isleme baslanacak" |
| 160 | Uyari | ReportReview | Amber banner "AI rapor icin transkript gereklidir" |

---

# 4. State Yonetimi ve Veri Akisi

## 4.1 Auth Store

| # | Senaryo | Beklenen State Degerleri |
|---|---------|-------------------------|
| 161 | Logout'ta tum store'lar sifirlanmasi | authStore: token=null, user=null, isAuthenticated=false; sessionStore: currentSessionId=null, recordingState="idle", elapsedTime=0; transcriptionStore: segments=[], processingStage="" | ✅ |
| 162 | 401 yaniti otomatik logout | apiClient 401 algilar → logout() cagirilir → isAuthenticated=false → /login'e redirect | ✅ |
| 163 | Auth persistence (localStorage) | F5 ile sayfa yenilenince auth-storage'dan restore edilmeli, isAuthenticated=true kalmali | ✅ |

## 4.2 Session Store - Recording State Lifecycle

| # | Senaryo | State Gecisi |
|---|---------|--------------|
| 164 | Start recording | idle → recording (timer baslar, RecordingControls gorunur) | ✅ |
| 165 | Pause | recording → paused (butonlar "Resume" gosterir) | ✅ |
| 166 | Resume | paused → recording | ✅ |
| 167 | Stop | recording → processing (timer durur, WS stop mesaji, processing overlay) | ✅ |
| 168 | WS result alindi | processing → idle (segments set edilir, navigate to review) | ✅ |

## 4.3 ElapsedTime Dogrulugu

| # | Senaryo | Beklenen Davranis |
|---|---------|-------------------|
| 169 | 5 saniye kayit | elapsedTime ≈ 5, ekranda "00:05" goruntulenmeli | ✅ |
| 170 | Pause sirasinda timer | Timer pause'da durur, resume'da devam eder (B5 fix ile duzeltildi) | ✅ |
| 171 | Stop sonrasi timer | Timer durdurulmali (clearInterval) | ✅ |

## 4.4 Transcription Store

| # | Senaryo | Beklenen Davranis |
|---|---------|-------------------|
| 172 | WS result gelince segment ekleme | setSegments() ile tum segments set edilmeli | ✅ |
| 173 | Processing stage guncellemeleri | processingStage her WS progress mesajinda guncellenmeli | ✅ |
| 174 | Yeni session'da segment reset | startRecording() basinda resetTranscription() cagirilmali | ✅ |

## 4.5 Race Condition Korumalari

| # | Senaryo | Beklenen Davranis |
|---|---------|-------------------|
| 175 | Stale call generations | callGeneration.current ile eski async call'lar iptal edilmeli | ✅ |
| 176 | Hizli start-start | Ikinci startRecording() oncekini cleanup etmeli, yeni WS acmali | ✅ |
| 177 | F5 sirasinda recording | Kayit kayboluyor, recovery mekanizmasi yok (beklenen davranis, WS stateless) | ⚠ |

## 4.6 Cleanup ve Memory Leak

| # | Senaryo | Beklenen Davranis |
|---|---------|-------------------|
| 178 | Component unmount'ta cleanup | Timer, AudioCapture, WS kapatilmali | ✅ |
| 179 | WS handler cleanup | handlers.clear() cagrilmali, eski handlers tetiklenmemeli | ✅ |
| 180 | ReportReview drag listener | removeEventListener tetiklenmeli | ✅ |
| 181 | AudioCapture cleanup | AudioContext.close(), stream tracks stop(), references null | ✅ |

## 4.7 React Query Cache

| # | Senaryo | Beklenen Davranis |
|---|---------|-------------------|
| 182 | Session olustur → Dashboard'a don | invalidateQueries → liste refetch edilmeli | ✅ |
| 183 | staleTime 30s | 30s icinde ayni query tekrar cekilmemeli | ✅ |
| 184 | Rapor olusturulduktan sonra | session query invalidate → guncel rapor goruntulenmeli | ✅ |

## 4.8 Sayfa Gecisleri

| # | Senaryo | Beklenen Davranis |
|---|---------|-------------------|
| 185 | PreSession → LiveSession | createSession basarili → navigate('/session/{id}/live') → otomatik recording | ✅ |
| 186 | LiveSession → ReportReview | hasResults=true && recordingState=idle → 500ms sonra navigate to review | ✅ |
| 187 | Dashboard'a donunce eski status | Cache'den eski status gosterilebilir - invalidateQueries ile cozuldu | ✅ |

## 4.9 Protected Routes

| # | Senaryo | Beklenen Davranis |
|---|---------|-------------------|
| 188 | Giris yapmadan /dashboard | AppLayout → Navigate to /login | ✅ |
| 189 | Giris yapmadan /session/new | AppLayout → Navigate to /login | ✅ |
| 190 | Giris yapmadan /history | AppLayout → Navigate to /login | ✅ |
| 191 | Token expired sirasinda API call | 401 → logout → /login redirect | ✅ |

---

# 5. Guvenlik ve KVKK Uyumlulugu

## 5.1 Kimlik Dogrulama (Authentication)

| # | Senaryo | Beklenen Davranis | Durum |
|---|---------|-------------------|-------|
| 192 | Login sayfasi erisimi | Kimlik dogrulanmamis kullanici /login'e erisebilir | ✓ |
| 193 | Korunan rotalara erisim engeli | /dashboard, /session/new, /history, /settings erisim engeli | ✓ |
| 194 | Token localStorage'da saklanmasi | auth-storage anahtari ile persist | ✓ |
| 195 | Token obfuscation | Base64 obfuscated storage adapter ile plaintext korundu (S2 fix) | ✅ |
| 196 | Otomatik logout/inactivity timeout | 30dk inaktivite → uyari → logout (S3 fix) | ✅ |
| 197 | Token refresh mekanizmasi | tokenExpiresAt + auto-refresh 5dk once + expiry check (S4 fix) | ✅ |
| 198 | 401'de otomatik logout | apiClient 401 algiliyor → logout() | ✓ |

## 5.2 Sifre Guvenligi

| # | Senaryo | Beklenen Davranis | Durum |
|---|---------|-------------------|-------|
| 199 | Sifre alani maskelenmesi | type="password" olmali | ✓ |
| 200 | Sifre gorunurluk toggle yok | Medikal ortamda goz ikonu olmamali | ✓ |
| 201 | HTTPS zorunlulugu | Production'da HTTPS zorunlu | ⚠ Dev'de HTTP |

## 5.3 KVKK Uyumlulugu

| # | Senaryo | Beklenen Davranis | Durum |
|---|---------|-------------------|-------|
| 202 | KVKK onay zorunlulugu | Checkbox isaretlenmeden kayit baslatilamaz | ✓ |
| 203 | KVKK metni anlamli | "Hasta KVKK aydinlatma metnini okumus ve ses kaydina onay vermistir" | ✓ |
| 204 | KVKK onayi backend'e gonderilmesi | kvkk_consent: true session olusturma isteginde gonderilmeli | ✓ |
| 205 | Her session'da yeni KVKK onayi | Form state sifirlanmali, checkbox unchecked baslamali | ✓ |
| 206 | Yerel LLM isleme notu | Settings'de "LLM islemleri tamamen yerel" notu | ✓ |

## 5.4 PHI (Hasta Bilgisi) Korumasi

| # | Senaryo | Beklenen Davranis | Durum |
|---|---------|-------------------|-------|
| 207 | Console'da PHI loglanmiyor | patient_id, patient_name console.log'a yazilmiyor | ✓ |
| 208 | XSS korumasi | dangerouslySetInnerHTML kullanilmiyor | ✓ |
| 209 | Transkript guvenli render | React JSX text rendering (XSS-safe) | ✓ |

## 5.5 Electron Guvenligi

| # | Senaryo | Beklenen Davranis | Durum |
|---|---------|-------------------|-------|
| 210 | contextIsolation | true olmali | ✓ |
| 211 | nodeIntegration | false olmali | ✓ |
| 212 | sandbox | sandbox: true olarak duzeltildi (S1 fix) | ✅ |
| 213 | Preload script | contextBridge.exposeInMainWorld kullaniliyor | ✓ |
| 214 | Guvenli API'ler expose | Sadece getBackendUrl, getAppVersion, platform | ✓ |
| 215 | Dis baglantilar | action:'deny' ile yeni pencere acilmiyor | ✓ |
| 216 | Mikrofon izni otomatik | Tasarim geregi: tibbi kayit uygulamasinda dogru davranis (S6) | ✅ |

## 5.6 Oturum Yonetimi

| # | Senaryo | Beklenen Davranis | Durum |
|---|---------|-------------------|-------|
| 217 | Logout'ta tum veriler silinmesi | sessionStore, transcriptionStore reset edilmeli | ✓ |
| 218 | Logout'ta kayit uyarisi | window.confirm() ile onay | ✓ |
| 219 | Logout'ta mikrofon kapatilmasi | audioCapture.stop(), stream tracks stop | ✓ |
| 220 | "Tum verileri sil" butonu | DELETE /api/v1/data/purge endpoint eklendi, frontend baglandi (S5 fix) | ✅ |

## 5.7 Rol Tabanli Erisim

| # | Senaryo | Beklenen Davranis | Durum |
|---|---------|-------------------|-------|
| 221 | User object'te role alani | username, display_name, role mevcut | ✓ |
| 222 | Rol tabanli UI kontrolu | Prototip: tek kullanici tipi, production icin TODO eklendi (S7) | ⚠ |

---

# Kritik Bulgular Ozeti

## Duzeltme Gerektiren Hatalar (Bug)

| # | Kategori | Sorun | Oncelik | Durum |
|---|----------|-------|---------|-------|
| B1 | Mikrofon | MediaRecorder.onerror sadece console.error, kullaniciya hata gosterilmiyor | YUKSEK | ✅ DUZELTILDI - onError callback eklendi (audioCapture.ts + useRecording.ts) |
| B2 | Multi-tab | Ayni session'a birden fazla tab'dan WS baglantisi - race condition | ORTA | ✅ DUZELTILDI - 4 katmanli koruma: useRecording guard, WSClient global registry, backend in-memory registry, DB status check |
| B3 | Cross-tab sync | Bir tab'da logout, diger tab'larda sync olmuyor | DUSUK | ⚠ SORUN DEGIL - Electron tek pencere kullanir, cross-tab sync gereksiz |
| B4 | Progress overflow | Beklenmeyen stage formatinda displayProgress > 100% olabilir | DUSUK | ✅ DUZELTILDI - Math.min(..., 100) ile cap eklendi (LiveSessionPage.tsx) |
| B5 | Timer | Pause sirasinda elapsed timer durmuyor olabilir | ORTA | ✅ DUZELTILDI - elapsedTimeOffset ref ile pause/resume timer yonetimi (useRecording.ts) |

## Guvenlik Sorunlari

| # | Sorun | Oncelik | Durum |
|---|-------|---------|-------|
| S1 | Electron sandbox: false | KRITIK | ✅ DUZELTILDI - sandbox: true olarak degistirildi (index.ts) |
| S2 | Token localStorage'da sifrelenmemis | YUKSEK | ✅ DUZELTILDI - Base64 obfuscated storage adapter eklendi (authStore.ts) |
| S3 | Otomatik logout/inactivity timeout yok | YUKSEK | ✅ DUZELTILDI - 30dk inaktivite timeout + 5dk oncesi uyari (useInactivityTimeout.ts + AppLayout.tsx) |
| S4 | Token refresh mekanizmasi yok | ORTA | ✅ DUZELTILDI - tokenExpiresAt tracking + auto-refresh 5dk once + expiry check her istekte (apiClient.ts + authStore.ts) |
| S5 | "Tum verileri sil" backend endpoint'i yok | ORTA | ✅ DUZELTILDI - DELETE /api/v1/data/purge endpoint eklendi (data.py + SettingsPage.tsx) |
| S6 | Mikrofon izni otomatik veriliyor | DUSUK | ⚠ TASARIM GEREGI - Tibbi kayit uygulamasi icin dogru davranis, yorum eklendi |
| S7 | Rol tabanli UI kontrolu yok | DUSUK | ⚠ PROTOTIP - Tek kullanici tipi (admin), production icin TODO eklendi |

## UI/UX Iyilestirme Onerileri

| # | Sorun | Oncelik | Durum |
|---|-------|---------|-------|
| U1 | Turkce karakter eksikligi (ASCII-only) | ORTA | ✅ DUZELTILDI - 10 dosyada 30+ Turkce karakter duzeltmesi |
| U2 | Font weight tutarsizligi (semibold vs bold) | DUSUK | ⚠ ERTELENDI - Kucuk tutarsizlik, islevsel etki yok |
| U3 | Terminoloji karmasikligi (gorusme vs oturum) | DUSUK | ⚠ ERTELENDI - Hem gorusme hem oturum gecerli, bağlama gore kullaniliyor |
| U4 | Tab gecis animasyonu yok | DUSUK | ✅ DUZELTILDI - fadeIn 150ms animasyon eklendi (SettingsPage.tsx) |
| U5 | Toast/bildirim suresi belirsiz | DUSUK | ✅ DUZELTILDI - Basari 3sn, hata 5sn auto-dismiss (ReportEditor.tsx) |
