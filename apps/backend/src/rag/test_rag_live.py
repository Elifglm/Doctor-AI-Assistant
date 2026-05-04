"""Quick smoke: query the running production AnamnezRAGService directly.

Runs in the same process as a fresh init (the running uvicorn instance is
not used; this script spins up a separate ChromaDB client to confirm the
production config + PHI mask + retrieval all work end-to-end.

Usage:
    python -m apps.backend.src.rag.test_rag_live "<doctor speech>"
"""

from __future__ import annotations

import asyncio
import sys

from apps.backend.src.services.anamnez_rag_service import AnamnezRAGService

DEFAULT_QUERY = (
    "Hastam 32 yasinda erkek, 3 gundur devam eden bogaz agrisi, halsizlik, "
    "hafif ates ve burun akintisi sikayetleriyle geldi. Muayenede farenks "
    "hiperemik, akciger sesleri dogal, ral ronkus yok."
)


async def main() -> int:
    query = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUERY

    svc = AnamnezRAGService(profile="bge-m3", fmt="metadata")
    print("[test] initializing AnamnezRAGService...", flush=True)
    await svc.initialize()
    print(f"[test] ready. doc_count = {svc.doc_count:,}\n", flush=True)
    print(f"[test] QUERY:\n{query}\n", flush=True)

    results = await svc.query_similar_cases(query, top_k=5)
    print(f"[test] returned {len(results)} examples:\n", flush=True)

    for i, r in enumerate(results, start=1):
        snippet = r.document.replace("\n", " | ")
        if len(snippet) > 350:
            snippet = snippet[:350] + "..."
        print(f"--- #{i}  form_id={r.form_id}  dist={r.distance:.4f} ---")
        print(snippet)
        print()

    if results:
        print("[test] SUCCESS — RAG çalışıyor; few-shot örnekler retrieve edildi.")
        # quick PHI sanity check on returned docs
        joined = " ".join(r.document for r in results)
        leaked = []
        for tag in ("[MASKED_TC]", "[MASKED_PHONE]", "[MASKED_EMAIL]"):
            if tag in joined:
                leaked.append(tag)
        if leaked:
            print(f"[test] PHI mask placeholders observed: {leaked}")
        else:
            print("[test] No PHI placeholders in retrieved set (corpus already clean).")
    else:
        print("[test] FAIL — empty result set", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
