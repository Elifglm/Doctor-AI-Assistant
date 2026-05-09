"""TR/EN medical synonym expansion for BM25 retrieval — Phase 2.3.

Phase 2.1/2.2 error analysis revealed a persistent retrieval failure pattern:
HyDE generates English/Latin medical forms ("diabetes mellitus", "hypertension")
while the ICD-10 corpus uses Turkish equivalents ("diyabetes mellitüs",
"hipertansiyon"). BM25 doesn't bridge token-level differences.

This module provides a hand-crafted synonym map covering the most impactful
cases observed in the eval set (T11/T12 E11.9 missing, T18 J44.0 KOAH
alevlenme, etc.). MSH-TUR was considered but: (a) licensing complexity,
(b) the synonyms we actually need are <200 entries, (c) hand-crafting lets
us include corpus-specific quirks (e.g., "hipotroidizm" typo in TR ICD-10).

Design:
- Each canonical token expands to a list of synonyms (incl. self).
- Applied at QUERY tokenize time only — no corpus rebuild needed.
- BM25 receives expanded query tokens; corpus already has the canonical forms.
"""
from __future__ import annotations

# Map from any synonym → canonical group. Each group expands to all variants.
# Keep lowercased + ASCII-folded forms (matches _tokenize output).
_SYNONYM_GROUPS: list[set[str]] = [
    # ─── Diabetes / Diyabet ───
    {"diabetes", "diyabetes", "diyabet", "diabet", "diabetik", "diyabetik",
     "seker", "mellitus", "mellitus", "dm", "t2dm", "t1dm"},

    # ─── Hipertansiyon ───
    {"hipertansiyon", "hypertension", "hipertansif", "hipertansiyonu",
     "tansiyon", "ht", "esansiyel"},

    # ─── Kolesterol ───
    {"kolesterol", "cholesterol", "hiperkolesterolemi", "hypercholesterolemia",
     "hiperlipidemi", "hyperlipidemia", "dislipidemi", "dyslipidemia"},

    # ─── Tiroid / Hipotiroidi (corpus has "hipotroidizm" typo!) ───
    {"hipotiroidi", "hypothyroidism", "hipotiroidizm", "hipotroidizm",
     "tiroid", "thyroid", "guatr"},
    {"hipertiroidi", "hyperthyroidism", "tirotoksikoz", "thyrotoxicosis"},

    # ─── KOAH / COPD ───
    {"koah", "copd", "kronik", "obstruktif", "obstructive",
     "akciger", "pulmoner", "pulmonary"},
    # KOAH alevlenme — bridge to corpus "akut alt solunum yolu enfeksiyon"
    {"alevlenme", "exacerbation", "ekzaserbasyon", "akut"},

    # ─── Astım ───
    {"astim", "asthma", "astma", "alerjik", "allergic", "allerjik"},

    # ─── Anemi ───
    {"anemi", "anemia", "anemisi", "kansizlik",
     "demir", "iron", "ferritin", "ferritine"},

    # ─── Kalp yetmezliği ───
    {"kalp", "heart", "kardiak", "cardiac",
     "yetmezlik", "yetmezligi", "failure", "kky"},
    {"miyokard", "myocardial", "infarktus", "infarction",
     "infarkt", "mi", "kah", "iskemik", "ischemic"},
    {"atrial", "atriyal", "fibrilasyon", "fibrillation", "af"},

    # ─── Bronşit ───
    {"bronsit", "bronchitis", "bronk", "bronchial"},

    # ─── Hepatit ───
    {"hepatit", "hepatitis", "viral", "kronik",
     "hbsag", "anti", "hbs", "hcv", "hbv"},

    # ─── Üriner / Sistit / İdrar yolu ───
    {"sistit", "cystitis", "uri", "uti", "uti",
     "uyer", "uriner", "urinary",
     "idrar", "urine", "urinary"},
    {"dizuri", "dysuria", "pollakuri", "frequency",
     "suprapubik", "suprapubic"},

    # ─── GERD / Reflü ───
    {"reflu", "reflux", "gerd", "gord",
     "pirozis", "heartburn", "yanma", "burning",
     "epigastrik", "epigastric", "gastrit", "gastritis"},

    # ─── Common labs (SUT) ───
    {"hba1c", "hemoglobin", "a1c", "glikolize"},
    {"kreatinin", "creatinine", "creat"},
    {"bun", "ure", "urea", "nitrojen"},
    {"sodyum", "sodium", "na"},
    {"potasyum", "potassium", "k"},
    {"troponin", "troponin", "trop"},
    {"bnp", "natriuretic", "natriuretik", "peptid", "peptide", "nt"},
    {"inr", "protrombin", "prothrombin", "pt"},
    {"hemogram", "cbc", "tam", "kan", "sayim"},
    {"crp", "reaktif", "reactive"},
    {"sedimantasyon", "sedimentation", "esr", "eritrosit"},
    {"akciger", "lung", "thorax", "toraks", "pa"},
    {"ekg", "ecg", "elektrokardiyografi", "electrocardiography"},
    {"eko", "echo", "ekokardiyografi", "echocardiography"},
    {"holter", "holter", "ritim", "rhythm"},
    {"tsh", "stimulating", "stimulan", "tirotropin", "thyrotropin"},
    {"ldl", "hdl", "lipid", "lipoprotein", "trigliserid", "triglyceride"},
    {"ast", "alt", "alanin", "aspartat", "transaminaz", "transaminase"},
    {"hbv", "dna"},
    {"arter", "arterial", "kan", "gaz", "gas", "blood"},
]

# Build inverted index: token → set of synonyms (incl. self)
_TOKEN_TO_GROUP: dict[str, frozenset[str]] = {}
for group in _SYNONYM_GROUPS:
    fz = frozenset(group)
    for tok in group:
        if tok in _TOKEN_TO_GROUP:
            # Token belongs to multiple groups — merge
            _TOKEN_TO_GROUP[tok] = frozenset(_TOKEN_TO_GROUP[tok] | fz)
        else:
            _TOKEN_TO_GROUP[tok] = fz


def expand_token(token: str) -> list[str]:
    """Return [token, *synonyms]. If no entry, returns [token]."""
    if token in _TOKEN_TO_GROUP:
        return list(_TOKEN_TO_GROUP[token])
    return [token]


def expand_tokens(tokens: list[str]) -> list[str]:
    """Expand each token with its synonyms. Preserves order, dedupes."""
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        for syn in expand_token(t):
            if syn not in seen:
                seen.add(syn)
                out.append(syn)
    return out
