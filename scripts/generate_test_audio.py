"""Turkce tibbi test ses dosyalari olustur (gTTS ile)."""

import json
import subprocess
import os
from pathlib import Path
from gtts import gTTS

OUTPUT_DIR = Path("data/test_audio")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FFMPEG_PATH = "ffmpeg"
import glob as _glob
_ffmpeg_pattern = os.path.expandvars(
    r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"
    r"\Gyan.FFmpeg_Microsoft.Winget.Source_*"
    r"\ffmpeg-*-full_build\bin\ffmpeg.exe"
)
_ffmpeg_matches = _glob.glob(_ffmpeg_pattern)
if _ffmpeg_matches:
    FFMPEG_PATH = _ffmpeg_matches[0]

# 5 farkli tibbi diyalog (her biri ~3 dakikalik)
DIALOGUES = {
    "test_kardiyoloji": (
        "Merhaba, hoş geldiniz. Şikayetiniz nedir? "
        "Son birkaç haftadır göğüs ağrısı yaşıyorum. Özellikle merdiven çıkarken veya hızlı yürürken ağrı artıyor. "
        "Bu ağrı tam olarak nerede hissediyorsunuz? Sol tarafta mı, ortada mı? "
        "Göğsümün sol tarafında, bazen ortaya doğru yayılıyor. Koluma da yayılıyor bazen. "
        "Ağrı ne kadar sürüyor? Dinlenince geçiyor mu? "
        "Genellikle beş ile on dakika sürüyor. Dinlenince biraz hafifliyor ama tamamen geçmiyor. "
        "Daha önce kalp hastalığı tanısı aldınız mı? Ailenizde kalp hastalığı öyküsü var mı? "
        "Babam altmış yaşında kalp krizi geçirdi. Ben de hipertansiyon tedavisi görüyorum. "
        "Hangi ilaçları kullanıyorsunuz şu anda? "
        "Ramipril on miligram günde bir kez ve atorvastatin yirmi miligram akşamları alıyorum. "
        "Tansiyon değerleriniz nasıl seyrediyor? Son ölçümleriniz neydi? "
        "Genellikle yüz kırk bölü doksan civarında seyrediyor. Bazen daha yüksek çıkıyor. "
        "Elektrokardiyografi ve ekokardiyografi çekeceğiz. Ayrıca troponin ve kreatin kinaz testleri isteyeceğim. "
        "Efor testi de yapmamız gerekebilir. Koroner anjiyografi açısından değerlendireceğiz. "
    ),
    "test_dahiliye": (
        "Hoş geldiniz, bugün nasıl yardımcı olabilirim? "
        "Doktor bey, son zamanlarda çok halsiz hissediyorum. İştahım azaldı ve kilo veriyorum. "
        "Ne kadar kilo verdiniz? Bu durum ne zamandır devam ediyor? "
        "Son üç ayda yaklaşık beş kilo verdim. Halsizlik iki aydır var. "
        "Ateş, gece terlemesi gibi şikayetleriniz var mı? "
        "Ara sıra gece terlemesi oluyor. Ateşim olduğunu düşünmüyorum ama ölçmedim. "
        "Daha önce bilinen bir hastalığınız var mı? Tiroid, diyabet gibi? "
        "Tip iki diyabetim var. Metformin bin miligram günde iki kez kullanıyorum. "
        "Kan şekerinizi düzenli ölçüyor musunuz? Son hemoglobin A bir C değeriniz neydi? "
        "Aç kan şekerim genellikle yüz elli civarında. Son hemoglobin A bir C sekiz virgül iki çıkmıştı. "
        "Hemogram, biyokimya, tiroid fonksiyon testleri ve tam idrar tahlili isteyeceğim. "
        "Ayrıca karın ultrasonografisi de çekelim. Karaciğer ve dalak büyüklüğüne bakalım. "
        "Diyabet regulasyonunuz bozuk görünüyor. İnsülin tedavisine geçmemiz gerekebilir. "
    ),
    "test_noroloji": (
        "Buyurun, şikayetlerinizi dinliyorum. "
        "Son bir haftadır şiddetli baş ağrısı çekiyorum. Özellikle sabahları daha yoğun oluyor. "
        "Baş ağrınız hangi bölgede? Zonklayıcı mı, basınç hissi mi? "
        "Şakak bölgesinde, zonklayıcı tarzda. Bazen mide bulantısı da eşlik ediyor. "
        "Işığa veya sese karşı hassasiyet var mı? Görme bozukluğu yaşıyor musunuz? "
        "Evet, ışık rahatsız ediyor. Bazen göz önünde parlak noktalar görüyorum. "
        "Bu bulgular migren ile uyumlu görünüyor. Daha önce migren tanısı aldınız mı? "
        "Annem de migren hastası ama ben ilk defa bu kadar şiddetli yaşıyorum. "
        "Nörolojik muayene yapacağım. Kranial sinir muayenesi, motor ve duyusal muayene. "
        "Beyin manyetik rezonans görüntüleme isteyeceğim. Elektroensefalografi de çekelim. "
        "Şimdilik parasetamol bin miligram ve metoklopramid on miligram reçete ediyorum. "
        "Profilaksi için topiramat veya propranolol başlayabiliriz. Kontrol muayenesine gelin. "
    ),
    "test_ortopedi": (
        "Hoş geldiniz, ne şikayetle geldiniz? "
        "Sol dizimde ağrı var. Merdiven inerken ve çömelirken çok ağrıyor. "
        "Bu ağrı ne zamandır var? Herhangi bir travma veya düşme oldu mu? "
        "Yaklaşık iki aydır var. Düşme olmadı ama uzun yürüyüşlerden sonra başladı. "
        "Dizinizde şişlik var mı? Takılma veya boşalma hissi oluyor mu? "
        "Biraz şişlik var. Bazen merdiven çıkarken takılma hissi oluyor. "
        "Fizik muayenede menisküs testleri yapacağım. McMurray testi ve Apley testi. "
        "Diz röntgeni ve manyetik rezonans görüntüleme isteyeceğim. "
        "Menisküs yırtığı veya kıkırdak hasarı olabilir. Görüntüleme sonuçlarına göre karar vereceğiz. "
        "Şimdilik anti enflamatuar ilaç ve fizik tedavi öneriyorum. "
        "Buz uygulaması yapın. Diz çevresindeki kasları güçlendirme egzersizleri başlayalım. "
        "İki hafta sonra kontrole gelin. Manyetik rezonans sonucunu getirin. "
    ),
    "test_genel_muayene": (
        "Merhaba, genel sağlık kontrolü için geldiniz değil mi? "
        "Evet doktor hanım, yıllık check up yaptırmak istiyorum. Herhangi bir şikayetim yok. "
        "Bilinen hastalığınız veya düzenli kullandığınız ilaç var mı? "
        "Hayır, herhangi bir hastalığım yok. Vitamin takviyesi dışında ilaç kullanmıyorum. "
        "Ailede kronik hastalık öyküsü var mı? Diyabet, hipertansiyon, kanser? "
        "Annemde tip iki diyabet var. Babam da hipertansiyon hastası. "
        "Sigara veya alkol kullanıyor musunuz? "
        "Sigara içmiyorum. Sosyal olarak haftada bir iki kadeh alkol tüketiyorum. "
        "Düzenli egzersiz yapıyor musunuz? Beslenme alışkanlıklarınız nasıl? "
        "Haftada üç gün yürüyüş yapıyorum. Genellikle ev yemekleri yiyorum ama bazen dışarıda yemek yiyorum. "
        "Tam kan sayımı, açlık kan şekeri, lipid paneli, karaciğer ve böbrek fonksiyon testleri isteyeceğim. "
        "Tiroid fonksiyon testleri ve idrar tahlili de ekleyelim. "
        "Boy ve kilonuzu ölçelim. Vücut kitle indeksinizi hesaplayalım. "
        "Tansiyon ölçümü ve elektrokardiyografi de yapalım. Rutin kontroller önemli. "
    ),
}

manifest = []

for name, text in DIALOGUES.items():
    print(f"Olusturuluyor: {name}...")
    mp3_path = OUTPUT_DIR / f"{name}.mp3"
    wav_path = OUTPUT_DIR / f"{name}.wav"
    txt_path = OUTPUT_DIR / f"{name}.txt"

    # gTTS ile MP3 olustur
    tts = gTTS(text=text, lang="tr", slow=False)
    tts.save(str(mp3_path))

    # FFmpeg ile WAV'a donustur (16kHz mono)
    cmd = [FFMPEG_PATH, "-y", "-i", str(mp3_path), "-ar", "16000", "-ac", "1",
           "-c:a", "pcm_s16le", str(wav_path)]
    subprocess.run(cmd, capture_output=True, timeout=30)

    # MP3 sil
    mp3_path.unlink(missing_ok=True)

    # Referans transkripsiyon kaydet
    txt_path.write_text(text.strip(), encoding="utf-8")

    # Sure hesapla
    import wave
    with wave.open(str(wav_path), "rb") as wf:
        duration = wf.getnframes() / wf.getframerate()

    manifest.append({
        "name": name,
        "wav": str(wav_path),
        "txt": str(txt_path),
        "duration_s": round(duration, 1),
        "source": "gTTS synthetic Turkish medical dialogue",
    })
    print(f"  {duration:.0f}s")

# Manifest kaydet
with open(OUTPUT_DIR / "manifest.json", "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

print(f"\nToplam: {len(manifest)} test dosyasi")
for m in manifest:
    print(f"  {m['name']}: {m['duration_s']}s")
