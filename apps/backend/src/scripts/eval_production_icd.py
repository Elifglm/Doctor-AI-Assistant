"""End-to-end production ICD-10 pipeline eval.

Calls ICD10SuggestionService.suggest_from_report() directly with all
production features enabled (HyDE + BM25 + Synonym + Constitutional).

Outputs match the sub-agent format so we can score with the same scorer.

Usage:
  python -m apps.backend.src.scripts.eval_production_icd
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
OUT_DIR = PROJECT_ROOT / "data" / "subagent_outputs_production"
FORM_IDS = [f"T{i:02d}" for i in range(1, 21)]


async def init_production_service():
    from apps.backend.src.services.icd10_service import ICD10Service
    from apps.backend.src.services.icd10_vector_service import ICD10VectorService
    from apps.backend.src.services.icd10_suggestion_service import ICD10SuggestionService
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
    vec_svc = ICD10VectorService()
    await vec_svc.initialize()
    hyde = HyDEService(llm=llm)
    bm25 = await BM25Service.for_icd10()
    print("All ICD services initialized (HyDE + BM25 + Vector)")

    suggestion_svc = ICD10SuggestionService(
        llm=llm,
        icd10_service=icd_svc,
        vector_service=vec_svc,
        ner_service=ner,
        validation_mode="strict",
        hyde_service=hyde,
        bm25_service=bm25,
    )
    return suggestion_svc


async def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    svc = await init_production_service()
    print(f"\nRunning production ICD on {len(FORM_IDS)} forms...")

    summary = {}
    for fid in FORM_IDS:
        anam_path = DATA_DIR / f"gold_{fid}_anamnez.json"
        if not anam_path.exists():
            continue
        anam = json.loads(anam_path.read_text(encoding="utf-8"))
        fields = anam.get("fields", {})

        try:
            suggestions = await svc.suggest_from_report(fields)
        except Exception as e:
            print(f"  {fid}: FAIL ({e})")
            summary[fid] = f"FAIL: {e}"
            continue

        # Format like sub-agent output
        output = [
            {
                "icd_kodu": s.icd_kodu,
                "tani": s.tani,
                "confidence": s.confidence,
                "source": getattr(s, "source", "tani"),
                "reasoning": s.reasoning or "",
            }
            for s in suggestions
        ]
        out_path = OUT_DIR / f"{fid}_icd_opus_output.json"
        out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        codes = [s.icd_kodu for s in suggestions]
        summary[fid] = codes
        print(f"  {fid}: {codes}")

    print("\n=== Summary ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
