"""Prep sub-agent inputs WITH HyDE (hypothetical document embeddings).

Compared to baseline prep_subagent_inputs.py:
  - For each form, generate HyDE hypothetical clinical summary via Haiku
  - Use HyDE summary as primary query for vector search (alongside NER terms)
  - Outputs to data/subagent_inputs_hyde/

Cost: ~$0.10-0.15 total (20 forms × 2 layers × 1 Haiku call each).

Usage:
  python -m apps.backend.src.scripts.prep_subagent_inputs_hyde
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = PROJECT_ROOT / "data" / "eval_synthetic"
OUT_DIR = PROJECT_ROOT / "data" / "subagent_inputs_hyde"
HYDE_CACHE = PROJECT_ROOT / "data" / "hyde_cache"
FORM_IDS = [f"T{i:02d}" for i in range(1, 21)]


async def init_services():
    from apps.backend.src.services.icd10_service import ICD10Service
    from apps.backend.src.services.icd10_vector_service import ICD10VectorService
    from apps.backend.src.services.sut_service import SUTService
    from apps.backend.src.services.sut_vector_service import SUTVectorService
    from apps.backend.src.services.ner_service import NERService
    from apps.backend.src.services.hyde_service import HyDEService
    from apps.backend.src.services.llm_factory import create_llm_service
    from config.settings import AppSettings

    settings = AppSettings()
    llm = create_llm_service(settings)
    await llm.initialize()
    print(f"LLM ready: {llm.provider_name} / {llm.model_name}")

    ner = NERService()
    icd_svc = ICD10Service()
    icd_vec = ICD10VectorService()
    await icd_vec.initialize()
    sut_svc = SUTService()
    sut_vec = SUTVectorService()
    await sut_vec.initialize()
    hyde = HyDEService(llm=llm)
    return {
        "ner": ner, "icd": icd_svc, "icd_vec": icd_vec,
        "sut": sut_svc, "sut_vec": sut_vec,
        "hyde": hyde, "llm": llm,
    }


async def get_or_generate_hyde(services, form_id, layer, source_text):
    """Cache HyDE outputs to avoid re-paying for re-runs."""
    HYDE_CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = HYDE_CACHE / f"{form_id}_{layer}_hyde.txt"
    if cache_file.exists():
        return cache_file.read_text(encoding='utf-8')

    if layer == "icd":
        hypo = await services["hyde"].generate_for_icd(source_text)
    else:
        hypo = await services["hyde"].generate_for_sut(source_text)

    cache_file.write_text(hypo, encoding='utf-8')
    return hypo


async def prep_icd(services: dict, form_id: str) -> dict:
    from apps.backend.src.services.icd10_suggestion_service import (
        ICD10SuggestionService, ICD10_REPORT_SELECTION_PROMPT,
    )

    anam = json.loads((DATA_DIR / f"gold_{form_id}_anamnez.json").read_text(encoding="utf-8"))
    fields = anam.get("fields", {})

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

    # ─── HyDE: generate hypothetical clinical summary ───
    hyde_doc = await get_or_generate_hyde(services, form_id, "icd", report_text)
    print(f"  {form_id} HyDE: {hyde_doc[:120]!r}")

    suggestion_svc = ICD10SuggestionService(
        llm=None,
        icd10_service=services["icd"],
        vector_service=services["icd_vec"],
        ner_service=services["ner"],
        validation_mode="strict",
    )

    # Standard NER + token expansion
    ner_terms = await suggestion_svc._extract_ner_terms(report_text)
    for part_text in parts:
        for fragment in part_text.split("----"):
            fragment = fragment.strip()
            if fragment and len(fragment) > 2 and fragment not in {"BELIRTILMEDI", "BELIRTILMEDI."}:
                if fragment not in ner_terms:
                    ner_terms.append(fragment)

    # ─── KEY DIFFERENCE: ALSO add HyDE doc as a query term ───
    # Vector search will encode HyDE separately and merge candidates.
    if hyde_doc and hyde_doc.strip() and len(hyde_doc) > 20:
        ner_terms.insert(0, hyde_doc)  # prioritize HyDE query

    candidates = await suggestion_svc._find_vector_candidates(ner_terms)
    text_candidates = await suggestion_svc._text_search_fallback(ner_terms)
    seen = {c["icd_kodu"] for c in candidates}
    for tc in text_candidates:
        if tc["icd_kodu"] not in seen:
            seen.add(tc["icd_kodu"])
            candidates.append(tc)
    await suggestion_svc._augment_with_unspecified(candidates, seen)

    candidates_text = "\n".join(
        f"({c['icd_kodu']}) - {c['tani']} [skor: {c.get('score', 0):.2f}]"
        for c in candidates
    )
    full_prompt = ICD10_REPORT_SELECTION_PROMPT.format(
        report_text=report_text,
        candidates=candidates_text,
    )

    return {
        "form_id": form_id,
        "layer": "icd10",
        "config": {"hyde": True},
        "report_text": report_text,
        "hyde_doc": hyde_doc,
        "candidates": candidates,
        "n_candidates": len(candidates),
        "full_prompt": full_prompt,
        "instruction": (
            "You are simulating the LLM selection step of a Turkish medical AI ICD-10 "
            "pipeline (config: HyDE enabled). Apply medical reasoning per `full_prompt`. "
            "Select codes ONLY from `candidates`. Output JSON: "
            '[{"icd_kodu":"...","tani":"...","confidence":0.0-1.0,"source":"tani|semptom","reasoning":"..."}]'
        ),
    }


async def prep_sut(services: dict, form_id: str) -> dict:
    from apps.backend.src.services.sut_suggestion_service import (
        SUTSuggestionService, SUT_SELECTION_PROMPT_V3, _safe_for_format,
    )

    transcript = (DATA_DIR / f"transcript_{form_id}.txt").read_text(encoding="utf-8")

    # ─── HyDE for SUT: hypothetical formal test list ───
    hyde_doc = await get_or_generate_hyde(services, form_id, "sut", transcript)
    print(f"  {form_id} SUT-HyDE: {hyde_doc[:120]!r}")

    suggestion_svc = SUTSuggestionService(
        llm=None,
        sut_service=services["sut"],
        vector_service=services["sut_vec"],
        ner_service=services["ner"],
        validation_mode="strict",
    )

    ner_terms = await suggestion_svc._extract_ner_terms(transcript)
    if hyde_doc and hyde_doc.strip() and len(hyde_doc) > 10:
        ner_terms.insert(0, hyde_doc)  # prioritize

    candidates = await suggestion_svc._find_vector_candidates(ner_terms, brans="dahiliye")
    text_candidates = await suggestion_svc._text_search_fallback(ner_terms, brans="dahiliye")
    seen = {c["kodu"] for c in candidates}
    for tc in text_candidates:
        if tc["kodu"] not in seen:
            seen.add(tc["kodu"])
            candidates.append(tc)

    candidates_text = "\n".join(
        f"({c['kodu']}) - {c['adi']} [{c.get('brans','')}] [skor: {c.get('score',0):.2f}]"
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
        "config": {"hyde": True},
        "transcript": transcript,
        "hyde_doc": hyde_doc,
        "candidates": candidates,
        "n_candidates": len(candidates),
        "full_prompt": full_prompt,
        "instruction": (
            "You are simulating the LLM selection step of a Turkish medical AI SUT "
            "tetkik intent disambiguation pipeline (config: HyDE enabled, V3 prompt). "
            "Apply step-by-step V3 reasoning per `full_prompt`. Select REQUEST mentions "
            "ONLY from `candidates`. Output JSON per V3 schema."
        ),
    }


async def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    services = await init_services()
    print(f"Services ready. Generating HyDE-augmented inputs for {len(FORM_IDS)} forms × 2 layers...")

    summary = {"icd": {}, "sut": {}}
    for fid in FORM_IDS:
        print(f"  {fid}: ICD...", end=" ", flush=True)
        try:
            icd_pkg = await prep_icd(services, fid)
            (OUT_DIR / f"{fid}_icd_input.json").write_text(
                json.dumps(icd_pkg, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            summary["icd"][fid] = icd_pkg["n_candidates"]
            print(f"{icd_pkg['n_candidates']} cand", end=" | ")
        except Exception as e:
            print(f"FAIL ({e})", end=" | ")
            summary["icd"][fid] = f"FAIL: {e}"

        print(f"SUT...", end=" ", flush=True)
        try:
            sut_pkg = await prep_sut(services, fid)
            (OUT_DIR / f"{fid}_sut_input.json").write_text(
                json.dumps(sut_pkg, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            summary["sut"][fid] = sut_pkg["n_candidates"]
            print(f"{sut_pkg['n_candidates']} cand")
        except Exception as e:
            print(f"FAIL ({e})")
            summary["sut"][fid] = f"FAIL: {e}"

    print("\n=== Summary ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nWritten to: {OUT_DIR}")
    print(f"HyDE cache: {HYDE_CACHE} (re-run uses cached docs, no LLM cost)")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
