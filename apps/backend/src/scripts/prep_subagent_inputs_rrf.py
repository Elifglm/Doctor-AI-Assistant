"""Prep sub-agent inputs WITH RRF + Reranker enabled (new recall stack).

Compared to prep_subagent_inputs.py:
  - Sets ASR_RRF_ENABLED=true (RRF fusion of vector+text+llm-extract channels)
  - Sets ASR_RERANKER_ENABLED=true (cross-encoder reranker)
  - Initializes RerankerService and passes to ICD/SUT services
  - Outputs to data/subagent_inputs_rrf/ (preserves baseline)

Usage:
  python -m apps.backend.src.scripts.prep_subagent_inputs_rrf
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# Set feature flags BEFORE importing services (they read env at import/init)
os.environ.setdefault("ASR_RRF_ENABLED", "true")
os.environ.setdefault("ASR_RERANKER_ENABLED", "true")

try:
    from dotenv import load_dotenv
    load_dotenv()
    # Re-set after dotenv (in case .env had different values)
    os.environ["ASR_RRF_ENABLED"] = "true"
    os.environ["ASR_RERANKER_ENABLED"] = "true"
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = PROJECT_ROOT / "data" / "eval_synthetic"
OUT_DIR = PROJECT_ROOT / "data" / "subagent_inputs_rrf"
FORM_IDS = [f"T{i:02d}" for i in range(1, 21)]


async def init_services():
    from apps.backend.src.services.icd10_service import ICD10Service
    from apps.backend.src.services.icd10_vector_service import ICD10VectorService
    from apps.backend.src.services.sut_service import SUTService
    from apps.backend.src.services.sut_vector_service import SUTVectorService
    from apps.backend.src.services.ner_service import NERService
    from apps.backend.src.services.reranker_service import RerankerService

    ner = NERService()
    icd_svc = ICD10Service()
    icd_vec = ICD10VectorService()
    await icd_vec.initialize()
    sut_svc = SUTService()
    sut_vec = SUTVectorService()
    await sut_vec.initialize()

    # Reranker — shared across ICD and SUT (same cross-encoder)
    reranker = RerankerService()
    print(f"Reranker enabled={reranker.is_enabled}, loading model (~30s first time)...")
    await reranker.initialize()
    print(f"Reranker ready={reranker.is_ready}")

    return {
        "ner": ner,
        "icd": icd_svc, "icd_vec": icd_vec,
        "sut": sut_svc, "sut_vec": sut_vec,
        "reranker": reranker,
    }


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

    # Pass reranker to service
    suggestion_svc = ICD10SuggestionService(
        llm=None,
        icd10_service=services["icd"],
        vector_service=services["icd_vec"],
        ner_service=services["ner"],
        reranker=services["reranker"],
        validation_mode="strict",
    )

    # Use the public suggest_from_report path BUT we need to capture the
    # candidate pool BEFORE LLM selection. Easiest: call internal methods
    # mirroring suggest_from_report logic up to the LLM selection step.

    ner_terms = await suggestion_svc._extract_ner_terms(report_text)
    for part_text in parts:
        for fragment in part_text.split("----"):
            fragment = fragment.strip()
            if fragment and len(fragment) > 2 and fragment not in {"BELIRTILMEDI", "BELIRTILMEDI."}:
                if fragment not in ner_terms:
                    ner_terms.append(fragment)

    # New pipeline path: vector + text + RRF fuse + reranker
    vector_candidates = await suggestion_svc._find_vector_candidates(ner_terms)
    text_candidates = await suggestion_svc._text_search_fallback(ner_terms)

    # Apply RRF fusion if enabled
    from apps.backend.src.services.rrf_fusion import rrf_fuse, is_rrf_enabled
    if is_rrf_enabled():
        candidates = rrf_fuse(
            ranked_lists=[vector_candidates, text_candidates],
            id_field="icd_kodu",
            k=60,
        )
    else:
        # Naive merge (baseline)
        candidates = list(vector_candidates)
        seen = {c["icd_kodu"] for c in candidates}
        for tc in text_candidates:
            if tc["icd_kodu"] not in seen:
                seen.add(tc["icd_kodu"])
                candidates.append(tc)

    await suggestion_svc._augment_with_unspecified(candidates, {c["icd_kodu"] for c in candidates})

    # Reranker step (if enabled)
    if services["reranker"].is_ready:
        candidates = await services["reranker"].rerank(
            query=report_text,
            candidates=candidates,
            top_k=25,
            doc_field="tani",
        )

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
        "config": {"rrf": True, "reranker": True},
        "report_text": report_text,
        "candidates": candidates,
        "n_candidates": len(candidates),
        "full_prompt": full_prompt,
        "instruction": (
            "You are simulating the LLM selection step of a Turkish medical AI ICD-10 "
            "pipeline (NEW: RRF fusion + cross-encoder reranker enabled). Apply medical "
            "reasoning per `full_prompt`. Select codes ONLY from `candidates`. Output "
            'JSON: [{"icd_kodu":"...","tani":"...","confidence":0.0-1.0,"source":"tani|semptom","reasoning":"..."}]'
        ),
    }


async def prep_sut(services: dict, form_id: str) -> dict:
    from apps.backend.src.services.sut_suggestion_service import (
        SUTSuggestionService, SUT_SELECTION_PROMPT_V3, _safe_for_format,
    )

    transcript = (DATA_DIR / f"transcript_{form_id}.txt").read_text(encoding="utf-8")

    suggestion_svc = SUTSuggestionService(
        llm=None,
        sut_service=services["sut"],
        vector_service=services["sut_vec"],
        ner_service=services["ner"],
        reranker=services["reranker"],
        validation_mode="strict",
    )

    ner_terms = await suggestion_svc._extract_ner_terms(transcript)
    vector_candidates = await suggestion_svc._find_vector_candidates(ner_terms, brans="dahiliye")
    text_candidates = await suggestion_svc._text_search_fallback(ner_terms, brans="dahiliye")

    from apps.backend.src.services.rrf_fusion import rrf_fuse, is_rrf_enabled
    if is_rrf_enabled():
        candidates = rrf_fuse(
            ranked_lists=[vector_candidates, text_candidates],
            id_field="kodu",
            k=60,
        )
    else:
        candidates = list(vector_candidates)
        seen = {c["kodu"] for c in candidates}
        for tc in text_candidates:
            if tc["kodu"] not in seen:
                seen.add(tc["kodu"])
                candidates.append(tc)

    if services["reranker"].is_ready:
        candidates = await services["reranker"].rerank(
            query=transcript,
            candidates=candidates,
            top_k=25,
            doc_field="adi",
        )

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
        "config": {"rrf": True, "reranker": True},
        "transcript": transcript,
        "candidates": candidates,
        "n_candidates": len(candidates),
        "full_prompt": full_prompt,
        "instruction": (
            "You are simulating the LLM selection step of a Turkish medical AI SUT "
            "tetkik intent disambiguation pipeline (NEW: RRF + reranker enabled, V3 prompt). "
            "Apply step-by-step V3 reasoning per `full_prompt`. Select REQUEST mentions "
            "ONLY from `candidates`. Output JSON per V3 schema."
        ),
    }


async def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    services = await init_services()
    print(f"Services ready. Generating inputs for {len(FORM_IDS)} forms × 2 layers (RRF+Reranker)...")

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


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
