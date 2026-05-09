"""Prep sub-agent inputs WITH HyDE + Hierarchical + BM25/RRF (Phase 2.1 cumulative).

Builds on Phase 1.2 (prep_subagent_inputs_hierarchical.py) by ADDING a third
retrieval channel:
  - Channel 1: Dense vector (BGE-M3 + ChromaDB) with HyDE-augmented queries
  - Channel 2: Text fallback (SQL LIKE)
  - Channel 3: NEW — BM25 sparse retrieval

All three channels are fused via RRF (Reciprocal Rank Fusion, k=60).

Phase 2.1 hedef: kapatılması beklenen retrieval gap'ler:
  - T11/T12: E11.9 BM25 ile gelir mi? (doktor "Tip 2 DM" der, BM25 "diabetes" tokenize)
  - T14: E78 BM25 ile gelir
  - T17: D50.0 vs D50.9 ayrımı zaten yapılıyor
  - SUT: troponin, INR, sodyum, kreatinin, arter kan gazı, HBsAg

Outputs to data/subagent_inputs_bm25/

Usage:
  python -m apps.backend.src.scripts.prep_subagent_inputs_bm25
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
# Phase 3.2: Synonym retrieval (P2.3) + Constitutional prompt
OUT_DIR = PROJECT_ROOT / "data" / "subagent_inputs_constitutional"
HYDE_CACHE = PROJECT_ROOT / "data" / "hyde_cache"
FORM_IDS = [f"T{i:02d}" for i in range(1, 21)]


async def init_services():
    from apps.backend.src.services.icd10_service import ICD10Service
    from apps.backend.src.services.icd10_vector_service import ICD10VectorService
    from apps.backend.src.services.sut_service import SUTService
    from apps.backend.src.services.sut_vector_service import SUTVectorService
    from apps.backend.src.services.ner_service import NERService
    from apps.backend.src.services.hyde_service import HyDEService
    from apps.backend.src.services.bm25_service import BM25Service
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
    icd_bm25 = await BM25Service.for_icd10()
    sut_bm25 = await BM25Service.for_sut()
    print("BM25 indexes ready")
    return {
        "ner": ner, "icd": icd_svc, "icd_vec": icd_vec,
        "sut": sut_svc, "sut_vec": sut_vec,
        "hyde": hyde, "llm": llm,
        "icd_bm25": icd_bm25, "sut_bm25": sut_bm25,
    }


async def get_hyde(services, form_id, layer, source_text):
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


def _bm25_search_multi(bm25_service, queries: list[str], id_field: str, top_k_per_query: int = 10) -> list[dict]:
    """Run BM25 for each query, return DEDUPED list ranked by max score across queries.

    This produces a single ranked list suitable for RRF fusion.
    """
    score_map: dict[str, float] = {}
    rep_map: dict[str, dict] = {}
    for q in queries:
        if not q or not q.strip():
            continue
        results = bm25_service.search(q, top_k=top_k_per_query)
        for r in results:
            kid = r.get(id_field)
            if not kid:
                continue
            existing = score_map.get(kid, -1.0)
            if r["score"] > existing:
                score_map[kid] = r["score"]
                rep_map[kid] = {**r, "source": "bm25"}
    sorted_ids = sorted(score_map.keys(), key=lambda k: score_map[k], reverse=True)
    return [rep_map[kid] for kid in sorted_ids]


async def prep_icd(services: dict, form_id: str) -> dict:
    from apps.backend.src.services.icd10_suggestion_service import (
        ICD10SuggestionService, ICD10_REPORT_SELECTION_PROMPT_CONSTITUTIONAL,
    )
    from apps.backend.src.services.rrf_fusion import rrf_fuse

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

    hyde_doc = await get_hyde(services, form_id, "icd", report_text)

    suggestion_svc = ICD10SuggestionService(
        llm=None,
        icd10_service=services["icd"],
        vector_service=services["icd_vec"],
        ner_service=services["ner"],
        validation_mode="strict",
    )

    ner_terms = await suggestion_svc._extract_ner_terms(report_text)
    for part_text in parts:
        for fragment in part_text.split("----"):
            fragment = fragment.strip()
            if fragment and len(fragment) > 2 and fragment not in {"BELIRTILMEDI", "BELIRTILMEDI."}:
                if fragment not in ner_terms:
                    ner_terms.append(fragment)

    if hyde_doc and hyde_doc.strip() and len(hyde_doc) > 20:
        ner_terms.insert(0, hyde_doc)

    # ─── Channel 1: Dense vector (BGE-M3 + HyDE) ───
    vector_candidates = await suggestion_svc._find_vector_candidates(ner_terms)

    # ─── Channel 2: Text fallback (SQL LIKE) ───
    text_candidates = await suggestion_svc._text_search_fallback(ner_terms)

    # ─── Channel 3: NEW — BM25 sparse retrieval ───
    # Use HyDE doc + top NER terms as BM25 queries
    bm25_queries = [hyde_doc] + ner_terms[1:8]  # HyDE first, then top 7 NER
    bm25_candidates = _bm25_search_multi(services["icd_bm25"], bm25_queries, "icd_kodu", top_k_per_query=15)

    # ─── RRF fusion: 3 channels → single ranked list ───
    fused = rrf_fuse(
        ranked_lists=[vector_candidates, text_candidates, bm25_candidates],
        id_field="icd_kodu",
        k=60,
    )

    # Cap fused first, THEN augment with .9 codes — ensures .9 codes survive
    # the cap. Without this, BM25 boosts parent codes (E11, D50, J44) above
    # their .9 children (E11.9, D50.9, J44.9), pushing .9 codes out of top-60.
    candidates = fused[:55]  # leave headroom for .9 augmentation
    seen = {c["icd_kodu"] for c in candidates}
    await suggestion_svc._augment_with_unspecified(candidates, seen)

    candidates_text = "\n".join(
        f"({c['icd_kodu']}) - {c['tani']} [skor: {c.get('rrf_score', 0):.4f}]"
        for c in candidates
    )

    full_prompt = ICD10_REPORT_SELECTION_PROMPT_CONSTITUTIONAL.format(
        report_text=report_text,
        candidates=candidates_text,
    )

    return {
        "form_id": form_id,
        "layer": "icd10",
        "config": {"hyde": True, "hierarchical": True, "bm25_rrf": True},
        "report_text": report_text,
        "hyde_doc": hyde_doc,
        "candidates": candidates,
        "n_candidates": len(candidates),
        "n_vector": len(vector_candidates),
        "n_text": len(text_candidates),
        "n_bm25": len(bm25_candidates),
        "full_prompt": full_prompt,
        "instruction": (
            "You are simulating the LLM selection step of a Turkish medical AI ICD-10 "
            "pipeline (config: HyDE + Hierarchical + BM25/RRF). Apply 3-stage reasoning "
            "per `full_prompt`. Select codes ONLY from `candidates`. Output JSON: "
            '[{"icd_kodu":"...","tani":"...","confidence":0.0-1.0,"source":"tani|semptom","reasoning":"..."}]'
        ),
    }


async def prep_sut(services: dict, form_id: str) -> dict:
    from apps.backend.src.services.sut_suggestion_service import (
        SUTSuggestionService, SUT_SELECTION_PROMPT_V3, _safe_for_format,
    )
    from apps.backend.src.services.rrf_fusion import rrf_fuse

    transcript = (DATA_DIR / f"transcript_{form_id}.txt").read_text(encoding="utf-8")
    hyde_doc = await get_hyde(services, form_id, "sut", transcript)

    suggestion_svc = SUTSuggestionService(
        llm=None,
        sut_service=services["sut"],
        vector_service=services["sut_vec"],
        ner_service=services["ner"],
        validation_mode="strict",
    )

    ner_terms = await suggestion_svc._extract_ner_terms(transcript)
    if hyde_doc and hyde_doc.strip() and len(hyde_doc) > 10:
        ner_terms.insert(0, hyde_doc)

    # Channel 1: Dense
    vector_candidates = await suggestion_svc._find_vector_candidates(ner_terms, brans="dahiliye")
    # Channel 2: Text fallback
    text_candidates = await suggestion_svc._text_search_fallback(ner_terms, brans="dahiliye")
    # Channel 3: BM25
    bm25_queries = [hyde_doc] + ner_terms[1:8]
    bm25_all = _bm25_search_multi(services["sut_bm25"], bm25_queries, "kodu", top_k_per_query=15)
    # SUT brans filter (dahiliye + her ikisi)
    bm25_candidates = [
        c for c in bm25_all
        if c.get("brans") in {"dahiliye", "her ikisi", None}
    ]

    fused = rrf_fuse(
        ranked_lists=[vector_candidates, text_candidates, bm25_candidates],
        id_field="kodu",
        k=60,
    )

    candidates = fused[:60]

    candidates_text = "\n".join(
        f"({c['kodu']}) - {c['adi']} [{c.get('brans','')}] [rrf: {c.get('rrf_score',0):.4f}]"
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
        "config": {"hyde": True, "bm25_rrf": True},
        "transcript": transcript,
        "hyde_doc": hyde_doc,
        "candidates": candidates,
        "n_candidates": len(candidates),
        "n_vector": len(vector_candidates),
        "n_text": len(text_candidates),
        "n_bm25": len(bm25_candidates),
        "full_prompt": full_prompt,
        "instruction": (
            "You are simulating the LLM selection step of a Turkish medical AI SUT tetkik "
            "pipeline (config: HyDE + BM25/RRF, V3 prompt). Apply step-by-step V3 morphology "
            "reasoning. Select REQUEST mentions ONLY from `candidates`. Output JSON per V3 schema."
        ),
    }


async def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    services = await init_services()
    print(f"Services ready. Generating BM25/RRF inputs for {len(FORM_IDS)} forms × 2 layers...")

    summary = {"icd": {}, "sut": {}}
    for fid in FORM_IDS:
        print(f"  {fid}: ICD...", end=" ", flush=True)
        try:
            icd_pkg = await prep_icd(services, fid)
            (OUT_DIR / f"{fid}_icd_input.json").write_text(
                json.dumps(icd_pkg, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            summary["icd"][fid] = (icd_pkg["n_candidates"], icd_pkg["n_vector"], icd_pkg["n_text"], icd_pkg["n_bm25"])
            print(f"cand={icd_pkg['n_candidates']} (v={icd_pkg['n_vector']} t={icd_pkg['n_text']} bm25={icd_pkg['n_bm25']})", end=" | ")
        except Exception as e:
            print(f"FAIL ({e})", end=" | ")
            summary["icd"][fid] = f"FAIL: {e}"

        print(f"SUT...", end=" ", flush=True)
        try:
            sut_pkg = await prep_sut(services, fid)
            (OUT_DIR / f"{fid}_sut_input.json").write_text(
                json.dumps(sut_pkg, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            summary["sut"][fid] = (sut_pkg["n_candidates"], sut_pkg["n_vector"], sut_pkg["n_text"], sut_pkg["n_bm25"])
            print(f"cand={sut_pkg['n_candidates']} (v={sut_pkg['n_vector']} t={sut_pkg['n_text']} bm25={sut_pkg['n_bm25']})")
        except Exception as e:
            print(f"FAIL ({e})")
            summary["sut"][fid] = f"FAIL: {e}"

    print("\n=== Summary ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
