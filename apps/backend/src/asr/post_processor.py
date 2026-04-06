"""Turkce tibbi metin post-processing: deASCIIfication + Zemberek morfoloji + tibbi terim duzeltme."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Whisper'in sik yanlis yazdigi Turkce tibbi terimler
MEDICAL_CORRECTIONS: dict[str, str] = {
    # Whisper Turkce fonetik karisikliklari (gozlemlenen hatalar)
    "kulunuzda": "kolunuzda",
    "kulumda": "kolumda",
    "kulunda": "kolunda",
    "kulunuz": "kolunuz",
    "haram mi": "ağrınız mı",
    "haram mı": "ağrınız mı",
    # Vucut bolumleri - sesli harf karisikliklari
    "gogus": "göğüs",
    "gogsum": "göğsüm",
    "gogsunde": "göğsünde",
    "bacaginda": "bacağında",
    "karnimda": "karnımda",
    "basim": "başım",
    "belim": "belim",
    # Tibbi terimler
    "paracetamol": "parasetamol",
    "miyokard enfarktusu": "miyokard enfarktüsü",
    # Code-switching varyantlari
    "kardiak": "kardiyak",
    "anjiografi": "anjiyografi",
    "psikiatri": "psikiyatri",
    "pnomotoraks": "pnömotoraks",
    "pnomoni": "pnömoni",
    # Semptomlar
    "bulanti": "bulantı",
    "nefes darligi": "nefes darlığı",
    "oksuruk": "öksürük",
}

# Tibbi terimler whitelist - Zemberek bu kelimeleri DEGISTIRMEMELI
# (Latince/Yunanca kokenli tibbi terimler Zemberek sozlugunde yok)
MEDICAL_WHITELIST: set[str] = {
    # Tani/hastalik
    "hipertansiyon", "hipotansiyon", "diyabet", "diyabetes", "mellitus",
    "hiperlipidemi", "hipertiroidizm", "hipotiroidizm", "epilepsi",
    "miyokard", "enfarktüsü", "pnömoni", "bronşit", "gastrit", "kolesistit",
    "pnömotoraks", "kardiyomiyopati", "aritmia", "aritmi", "anemi",
    # Ilaclar
    "parasetamol", "amoksisilin", "metformin", "atorvastatin", "ramipril",
    "omeprazol", "lansoprazol", "asetilsalisilik", "klopidogrel", "insülin",
    # Tetkikler
    "hemogram", "biyokimya", "sedimentasyon", "kreatinin", "troponin",
    "ekokardiyografi", "elektrokardiyografi", "ultrasonografi", "tomografi",
    "endoskopi", "kolonoskopi", "mamografi", "anjiyografi",
    # Kisaltmalar
    "EKG", "EEG", "EMG", "CRP", "KOAH", "BT", "MR",
    # Muayene terimleri
    "anamnez", "inspeksiyon", "palpasyon", "perküsyon", "oskültasyon",
    "epikriz", "konsültasyon", "prognoz", "etiyoloji", "semptom",
    # Anatomik terimler
    "temporal", "frontal", "oksipital", "servikal", "lomber", "torakal",
    "bilateral", "lateral", "medial", "anterior", "posterior",
    "abdomen", "toraks", "pelvis", "femur", "humerus", "tibia",
}


class TurkishPostProcessor:
    """Turkce tibbi metin duzeltme: deASCIIfication + Zemberek + tibbi terim sozlugu.

    Pipeline:
        1. DeASCIIfication (gogus -> göğüs)
        2. Zemberek morfolojik kontrol (kulumda -> kolumda)
        3. Statik tibbi terim duzeltme (son guvenlik agi)
    """

    def __init__(
        self,
        medical_overrides: dict[str, str] | None = None,
    ) -> None:
        self._deasciifier_available = False
        self._zemberek_available = False
        self._morphology: Any = None
        self._spell_checker: Any = None
        self._medical_overrides = {
            **MEDICAL_CORRECTIONS,
            **(medical_overrides or {}),
        }
        self._whitelist = MEDICAL_WHITELIST | set(MEDICAL_CORRECTIONS.values())

        # Lazy-init deasciifier
        try:
            from turkish.deasciifier import Deasciifier
            self._deasciifier_available = True
            logger.info("turkish-deasciifier yuklendi")
        except ImportError:
            logger.warning("turkish-deasciifier bulunamadi")

        # Lazy-init Zemberek (sadece morfolojik analiz, SpellChecker crash ediyor)
        try:
            from zemberek import TurkishMorphology
            self._morphology = TurkishMorphology.create_with_defaults()
            self._zemberek_available = True
            logger.info("Zemberek morfoloji yuklendi (analiz modu)")
        except ImportError:
            logger.warning("zemberek-python bulunamadi, morfolojik duzeltme atlanacak")
        except Exception as e:
            logger.warning("Zemberek yukleme hatasi: %s", e)

    def process(self, text: str) -> str:
        """Metni duzelt: deASCIIfication + Zemberek + tibbi terim.

        Args:
            text: Ham transkripsiyon metni

        Returns:
            Duzeltilmis metin
        """
        if not text or not text.strip():
            return text

        # 1. DeASCIIfication
        text = self._deasciify(text)

        # 2. Zemberek morfolojik duzeltme (sesli harf uyumu vb.)
        text = self._zemberek_correct(text)

        # 3. Statik tibbi terim duzeltme (son guvenlik agi)
        text = self._apply_medical_corrections(text)

        return text

    def _deasciify(self, text: str) -> str:
        """ASCII Turkce karakterleri dogru Unicode'a donustur."""
        if not self._deasciifier_available:
            return text
        try:
            from turkish.deasciifier import Deasciifier
            return Deasciifier(text).convert_to_turkish()
        except Exception as e:
            logger.debug("DeASCIIfication hatasi: %s", e)
            return text

    def _zemberek_correct(self, text: str) -> str:
        """Zemberek ile morfolojik olarak gecersiz kelimeleri tespit et ve logla.

        Not: 'kulumda' gibi hatalar Zemberek'te de gecerli Turkce olarak
        tanimlaniyor (kul+um+da). Bu metod sadece tamamen gecersiz kelimeleri
        yakalayabilir. Baglama bagimli hatalar statik sozluk ile duzeltilir.
        """
        if not self._zemberek_available:
            return text

        words = text.split()
        for word in words:
            clean = word.strip(".,;:!?\"'()-")
            if len(clean) < 3:
                continue
            if clean.lower() in self._whitelist or clean in self._whitelist:
                continue
            try:
                results = self._morphology.analyze(clean)
                if not results:
                    logger.info("Zemberek: gecersiz kelime tespit edildi: '%s'", clean)
            except Exception:
                pass

        return text  # su an sadece loglama, ileride duzeltme eklenebilir

    def _apply_medical_corrections(self, text: str) -> str:
        """Bilinen tibbi terim hatalarini duzelt."""
        for wrong, correct in self._medical_overrides.items():
            if wrong != correct and wrong in text.lower():
                pattern = re.compile(re.escape(wrong), re.IGNORECASE)
                text = pattern.sub(correct, text)
        return text
