"""Pre-compute sub-agent input packages for ICD-10 and SUT layer evaluations.

For each transcript T01-T20:
  - ICD: load gold anamnez → run NER + vector search → build candidate pool → save
  - SUT: load transcript → run NER + vector search → build candidate pool → save

Sub-agents will then read these JSON inputs, apply medical reasoning (using
their model's intelligence — Opus), and output selected codes. No additional
local pipeline work needed during sub-agent execution.

Output:
  data/subagent_inputs/T<XX>_icd_input.json  (anamnez + ICD candidates + prompt)
  data/subagent_inputs/T<XX>_sut_input.json  (transcript + SUT candidates + prompt)

Usage:
  python -m apps.backend.src.scripts.prep_subagent_inputs
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = PROJECT_ROOT / "data" / "eval_synthetic"
OUT_DIR = PROJECT_ROOT / "data" / "subagent_inputs"
FORM_IDS = [f"T{i:02d}" for i in range(1, 21)]


async def init_services():
    from apps.backend.src.services.icd10_service import ICD10Service
    from apps.backend.src.services.icd10_vector_service import ICD10VectorService
    from apps.backend.src.services.sut_service import SUTService
    from apps.backend.src.services.sut_vector_service import SUTVectorService
    from apps.backend.src.services.ner_service import NERService

    ner = NERService()
    icd_svc = ICD10Service()
    icd_vec = ICD10VectorService()
    await icd_vec.initialize()
    sut_svc = SUTService()
    sut_vec = SUTVectorService()
    await sut_vec.initialize()
    return {"ner": ner, "icd": icd_svc, "icd_vec": icd_vec,
            "sut": sut_svc, "sut_vec": sut_vec}


async def prep_icd(services: dict, form_id: str) -> dict:
    """Produce the package a sub-agent needs to do ICD-10 selection."""
    from apps.backend.src.services.icd10_suggestion_service import (
        ICD10SuggestionService, ICD10_REPORT_SELECTION_PROMPT,
    )

    # Load gold anamnez (input to ICD pipeline, isolated mode)
    anam = json.loads((DATA_DIR / f"gold_{form_id}_anamnez.json").read_text(encoding="utf-8"))
    fields = anam.get("fields", {})

    # Build report text from relevant fields (mirroring suggest_from_report logic)
    relevant_keys = {
        "hastanin_yakinmasi", "hastanin_oykusu", "muayene_bulgulari",
        "on_tani", "kesin_tani", "oz_gecmisi_soy_gecmisi", "soy_gecmisi",
        "konsultasyon_muayene", "konsultasyon_sonuc", "konsultasyon_oneri",
        "tedavi",
    }
    parts = []
    for k in relevant_keys:
        v = fields.get(k, "").strip()
        if v and v not in {"BELIRTILMEDI", "BELIRTILMEDI."}:
            parts.append(v)
    report_text = "\n".join(parts)

    # Use service to compute candidates the same way production does
    suggestion_svc = ICD10SuggestionService(
        llm=None,  # we don't need the LLM, we'll route to sub-agent
        icd10_service=services["icd"],
        vector_service=services["icd_vec"],
        ner_service=services["ner"],
        validation_mode="strict",  # for candidate generation only
    )

    # NER + vector + text fallback (skip LLM-explicit since it needs LLM)
    ner_terms = await suggestion_svc._extract_ner_terms(report_text)

    # Add fragments split by ----
    for part_text in parts:
        for fragment in part_text.split("----"):
            fragment = fragment.strip()
            if fragment and len(fragment) > 2 and fragment not in {"BELIRTILMEDI", "BELIRTILMEDI."}:
                if fragment not in ner_terms:
                    ner_terms.append(fragment)

    candidates = await suggestion_svc._find_vector_candidates(ner_terms)
    text_candidates = await suggestion_svc._text_search_fallback(ner_terms)
    seen = {c["icd_kodu"] for c in candidates}
    for tc in text_candidates:
        if tc["icd_kodu"] not in seen:
            seen.add(tc["icd_kodu"])
            candidates.append(tc)
    await suggestion_svc._augment_with_unspecified(candidates, seen)

    # Build the exact prompt our pipeline would send to LLM
    candidates_text = "\n".join(
        f"({c['icd_kodu']}) - {c['tani']} [skor: {c['score']:.2f}]"
        for c in candidates
    )
    full_prompt = ICD10_REPORT_SELECTION_PROMPT.format(
        report_text=report_text,
        candidates=candidates_text,
    )

    return {
        "form_id": form_id,
        "layer": "icd10",
        "report_text": report_text,
        "candidates": candidates,
        "n_candidates": len(candidates),
        "full_prompt": full_prompt,
        "instruction": (
            "You are simulating the LLM selection step of a Turkish medical AI ICD-10 "
            "pipeline. Apply medical reasoning per the rules in `full_prompt`. Select "
            "appropriate codes ONLY from the `candidates` list. Output JSON array of "
            "selected codes with format: "
            '[{"icd_kodu": "...", "tani": "...", "confidence": 0.0-1.0, '
            '"source": "tani|semptom", "reasoning": "..."}]'
        ),
    }


async def prep_sut(services: dict, form_id: str) -> dict:
    """Produce the package a sub-agent needs to do SUT intent selection."""
    from apps.backend.src.services.sut_suggestion_service import (
        SUTSuggestionService, SUT_SELECTION_PROMPT_V3, _safe_for_format,
    )

    # Load transcript (input to SUT pipeline)
    transcript = (DATA_DIR / f"transcript_{form_id}.txt").read_text(encoding="utf-8")

    suggestion_svc = SUTSuggestionService(
        llm=None,
        sut_service=services["sut"],
        vector_service=services["sut_vec"],
        ner_service=services["ner"],
        validation_mode="strict",
    )

    ner_terms = await suggestion_svc._extract_ner_terms(transcript)
    candidates = await suggestion_svc._find_vector_candidates(ner_terms, brans="dahiliye")
    text_candidates = await suggestion_svc._text_search_fallback(ner_terms, brans="dahiliye")
    seen = {c["kodu"] for c in candidates}
    for tc in text_candidates:
        if tc["kodu"] not in seen:
            seen.add(tc["kodu"])
            candidates.append(tc)

    candidates_text = "\n".join(
        f"({c['kodu']}) - {c['adi']} [{c.get('brans','')}] [skor: {c['score']:.2f}]"
        for c in candidates
    )
    full_prompt = SUT_SELECTION_PROMPT_V3.format(
        transcript=_safe_for_format(transcript),
        icd_context="",
        candidates=_safe_for_format(candidates_text),
    )

    return {
        "form_id": form_id,
        "layer": "sut",
        "transcript": transcript,
        "candidates": candidates,
        "n_candidates": len(candidates),
        "full_prompt": full_prompt,
        "instruction": (
            "You are simulating the LLM selection step of a Turkish medical AI SUT "
            "tetkik intent disambiguation pipeline (V3 prompt). Apply step-by-step "
            "reasoning per the rules in `full_prompt`. Select REQUEST mentions "
            "ONLY from the `candidates` list. Output JSON array per V3 schema."
        ),
    }


async def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    services = await init_services()
    print(f"Services initialized. Generating inputs for {len(FORM_IDS)} forms × 2 layers...")

    summary = {"icd": {}, "sut": {}}
    for fid in FORM_IDS:
        print(f"  {fid}: ICD...", end=" ", flush=True)
        try:
            icd_pkg = await prep_icd(services, fid)
            (OUT_DIR / f"{fid}_icd_input.json").write_text(
                json.dumps(icd_pkg, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            summary["icd"][fid] = icd_pkg["n_candidates"]
            print(f"{icd_pkg['n_candidates']} candidates", end=" | ")
        except Exception as e:
            print(f"FAILED ({e})", end=" | ")
            summary["icd"][fid] = f"FAIL: {e}"

        print(f"SUT...", end=" ", flush=True)
        try:
            sut_pkg = await prep_sut(services, fid)
            (OUT_DIR / f"{fid}_sut_input.json").write_text(
                json.dumps(sut_pkg, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            summary["sut"][fid] = sut_pkg["n_candidates"]
            print(f"{sut_pkg['n_candidates']} candidates")
        except Exception as e:
            print(f"FAILED ({e})")
            summary["sut"][fid] = f"FAIL: {e}"

    print("\n=== Summary ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nWritten to: {OUT_DIR}")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
