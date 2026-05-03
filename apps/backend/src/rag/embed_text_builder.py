"""Build the embedding text for an anamnesis row, in 3 ablation formats.

Formats:
- "baseline"  : titled concat of yakinma + oyku + muayene
- "no_titles" : raw concat (no section headers)
- "metadata"  : baseline + oz_gecmisi + sigara/alkol/alerji + vitals appended

E5 prefix ('passage: ' / 'query: ') is added by the build script wrapper,
not here — keep the formats model-agnostic.
"""

from __future__ import annotations

from typing import Mapping

FORMATS = ("baseline", "no_titles", "metadata")


def _clean(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _vital_line(row: Mapping) -> str:
    parts: list[str] = []
    sis = _clean(row.get("sistolik"))
    dia = _clean(row.get("diyastolik"))
    if sis or dia:
        parts.append(f"TA {sis or '?'}/{dia or '?'}")
    nabiz = _clean(row.get("nabiz"))
    if nabiz:
        parts.append(f"Nabız {nabiz}")
    ates = _clean(row.get("ates"))
    if ates:
        parts.append(f"Ateş {ates}")
    so2 = _clean(row.get("so2"))
    if so2:
        parts.append(f"SO2 {so2}")
    agri = _clean(row.get("agri_skalasi"))
    if agri:
        parts.append(f"VAS {agri}")
    return ", ".join(parts)


def build(row: Mapping, fmt: str) -> str:
    """Return the embedding text for a row in the given format."""
    if fmt not in FORMATS:
        raise ValueError(f"unknown format: {fmt!r}; pick from {FORMATS}")

    yak = _clean(row.get("yakinma"))
    oyk = _clean(row.get("oyku"))
    muay = _clean(row.get("muayene"))

    if fmt == "no_titles":
        parts = [p for p in (yak, oyk, muay) if p]
        return " ".join(parts)

    sections: list[str] = []
    if yak:
        sections.append(f"YAKINMA:\n{yak}")
    if oyk:
        sections.append(f"ÖYKÜ:\n{oyk}")
    if muay:
        sections.append(f"MUAYENE:\n{muay}")

    if fmt == "metadata":
        oz = _clean(row.get("oz_gecmisi"))
        soy = _clean(row.get("soy_gecmisi"))
        sig = _clean(row.get("sigara"))
        alk = _clean(row.get("alkol"))
        alj = _clean(row.get("alerji"))
        if oz:
            sections.append(f"ÖZ GEÇMİŞ:\n{oz}")
        if soy:
            sections.append(f"SOY GEÇMİŞ:\n{soy}")
        lifestyle = []
        if sig:
            lifestyle.append(f"sigara: {sig}")
        if alk:
            lifestyle.append(f"alkol: {alk}")
        if alj:
            lifestyle.append(f"alerji: {alj}")
        if lifestyle:
            sections.append("YAŞAM TARZI:\n" + ", ".join(lifestyle))
        vitals = _vital_line(row)
        if vitals:
            sections.append(f"VİTAL:\n{vitals}")

    return "\n\n".join(sections)


def build_query(text: str, prefix: str | None = None) -> str:
    """Build the eval query text from the holdout's yakinma field.

    Optional `prefix` (e.g. 'query: ' for E5 family) is prepended.
    """
    base = _clean(text)
    if prefix:
        return f"{prefix}{base}"
    return base
