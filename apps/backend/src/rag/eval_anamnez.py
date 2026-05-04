"""End-to-end eval over the 3 E5-base anamnez RAG configs (and BGE-M3 winner).

Pipeline per config (baseline / no_titles / metadata / bge-winner):
  1. For each query (holdout-100 + synthetic-50 + optional manual):
     - Retrieve top-5 similar anamneses
     - Compute distances, diversity
     - LLM-judge holistic Likert (1-5)
  2. On 20 sampled queries: per-result Likert deep-dive (5 ratings each)
  3. Aggregate: mean Likert, recall proxies, diversity, distance stats
  4. Write per-config CSV + summary JSON

Usage:
    python -m apps.backend.src.rag.eval_anamnez \\
        --profile e5-base --formats baseline no_titles metadata
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import random
import re
import sqlite3
import sys
import time
from pathlib import Path

import anthropic

from apps.backend.src.rag.embed_text_builder import build, build_query
from apps.backend.src.services.anamnez_rag_service import AnamnezRAGService
from apps.backend.src.services.embedding_config import get_profile

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DB_PATH = _PROJECT_ROOT / "data" / "anamnez.db"
_OUT_DIR = _PROJECT_ROOT / "apps" / "backend" / "src" / "rag" / "eval_results"

JUDGE_MODEL = "claude-haiku-4-5-20251001"

JUDGE_HOLISTIC_SYS = """Sen bir Türk dahiliye uzmanısın. Bir doktor konsültasyon yapıyor (transkript verilecek). Sistem, doktorun konuşmasına benzer geçmiş 5 hasta anamnezini retrieve ediyor. Görevin: dönen 5 anamnezin verilen konsültasyona uygunluğunu **1-5 Likert** ölçeğinde puanlamak.

Ölçek:
1 = Alakasız (farklı klinik tablo, retrieval başarısız)
2 = Marjinal (1-2 örnek hafif benzer, çoğu farklı)
3 = Orta (yarıdan fazla örnek tematik olarak alakalı)
4 = İyi (4-5 örnek doğru tablo, küçük tematik dağınıklık)
5 = Mükemmel (5/5 örnek aynı klinik tabloya odaklı, doktor için faydalı few-shot)

Sadece JSON döndür: {"likert": int, "kisa_gerekce": "..."}"""

JUDGE_DEEPDIVE_SYS = """Sen bir Türk dahiliye uzmanısın. Bir doktor konsültasyonu (sorgu) ile retrieve edilmiş 1 geçmiş anamnezi inceleyip, anamnezin sorguya uygunluğunu **1-5 Likert** ile puanla.

Ölçek:
1 = Alakasız
2 = Hafif
3 = Orta tematik benzerlik
4 = İyi tablo eşleşmesi
5 = Mükemmel klinik tablo eşleşmesi

Sadece JSON döndür: {"likert": int, "kisa_gerekce": "..."}"""


def load_queries() -> list[dict]:
    """Combine holdout + synthetic + manual eval queries."""
    queries: list[dict] = []

    # Holdout: yakinma alanı query olarak kullanılır
    with sqlite3.connect(_DB_PATH) as conn:
        rows = conn.execute(
            "SELECT FORM_ID, yakinma, oyku, muayene FROM ic_anamnez_eval_holdout"
        ).fetchall()
    for fid, yak, oyk, muay in rows:
        if not (yak and yak.strip()):
            continue
        # Holdout: doktor konuşmasını simüle etmek için yakınma+öykü birleştirilir
        text = yak.strip()
        if oyk and oyk.strip():
            text = f"{text} {oyk.strip()}"
        queries.append({
            "query_id": f"holdout_{fid}",
            "source": "holdout",
            "scenario": "real_anamnez_yakinma_oyku",
            "query_text": text,
            "gold_form_id": fid,
        })

    syn_path = _PROJECT_ROOT / "apps" / "backend" / "src" / "rag" / "eval_queries_synthetic.json"
    if syn_path.exists():
        with syn_path.open(encoding="utf-8") as f:
            for q in json.load(f):
                queries.append({**q, "source": "synthetic"})

    man_path = _PROJECT_ROOT / "apps" / "backend" / "src" / "rag" / "eval_queries_manual.json"
    if man_path.exists():
        with man_path.open(encoding="utf-8") as f:
            data = json.load(f)
            for q in data:
                if q.get("query_text", "").startswith("PLACEHOLDER"):
                    continue
                queries.append({**q, "source": "manual"})

    return queries


def diversity_score(documents: list[str]) -> float:
    """Crude lexical diversity: 1 - mean pairwise Jaccard over word sets."""
    if len(documents) < 2:
        return 0.0
    word_sets = [set(re.findall(r"\w+", d.lower())) for d in documents]
    total, n = 0.0, 0
    for i in range(len(word_sets)):
        for j in range(i + 1, len(word_sets)):
            a, b = word_sets[i], word_sets[j]
            if a or b:
                jacc = len(a & b) / len(a | b)
                total += 1.0 - jacc
                n += 1
    return total / n if n else 0.0


def parse_judge_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {"likert": None, "kisa_gerekce": text[:200], "parse_error": True}
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return {"likert": None, "kisa_gerekce": text[:200], "parse_error": True}


async def llm_judge_holistic(client, query: str, results: list[str]) -> dict:
    docs_text = "\n\n".join(f"--- ANAMNEZ {i+1} ---\n{d[:600]}" for i, d in enumerate(results))
    user = f"DOKTOR KONUŞMASI:\n{query}\n\nRETRIEVE EDİLEN 5 ANAMNEZ:\n{docs_text}"
    resp = await asyncio.to_thread(
        client.messages.create,
        model=JUDGE_MODEL,
        max_tokens=300,
        system=JUDGE_HOLISTIC_SYS,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in resp.content if hasattr(b, "text"))
    parsed = parse_judge_json(text)
    parsed["_in_tokens"] = resp.usage.input_tokens
    parsed["_out_tokens"] = resp.usage.output_tokens
    return parsed


async def llm_judge_deepdive(client, query: str, doc: str) -> dict:
    user = f"DOKTOR KONUŞMASI:\n{query}\n\nRETRIEVE EDİLEN ANAMNEZ:\n{doc[:800]}"
    resp = await asyncio.to_thread(
        client.messages.create,
        model=JUDGE_MODEL,
        max_tokens=200,
        system=JUDGE_DEEPDIVE_SYS,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in resp.content if hasattr(b, "text"))
    parsed = parse_judge_json(text)
    parsed["_in_tokens"] = resp.usage.input_tokens
    parsed["_out_tokens"] = resp.usage.output_tokens
    return parsed


async def evaluate_config(
    client, profile_name: str, fmt: str, queries: list[dict],
    deepdive_n: int, deepdive_seed: int,
) -> dict:
    print(f"\n{'='*70}\n[eval] profile={profile_name} fmt={fmt}\n{'='*70}", flush=True)
    svc = AnamnezRAGService(profile=profile_name, fmt=fmt)
    await svc.initialize()
    print(f"[eval] collection ready: {svc.doc_count:,} docs", flush=True)

    rnd = random.Random(deepdive_seed)
    deepdive_set = set(rnd.sample(range(len(queries)), min(deepdive_n, len(queries))))

    rows: list[dict] = []
    deep_rows: list[dict] = []
    in_tokens, out_tokens = 0, 0
    t0 = time.perf_counter()

    for qi, q in enumerate(queries):
        results = await svc.query_similar_cases(q["query_text"], top_k=5)
        if not results:
            continue
        docs = [r.document for r in results]
        dists = [r.distance for r in results]

        holistic = await llm_judge_holistic(client, q["query_text"], docs)
        in_tokens += holistic.get("_in_tokens", 0)
        out_tokens += holistic.get("_out_tokens", 0)

        rows.append({
            "query_id": q["query_id"],
            "source": q.get("source", "?"),
            "scenario": q.get("scenario", ""),
            "top1_form_id": results[0].form_id,
            "top1_dist": round(dists[0], 4),
            "top5_dist_mean": round(sum(dists) / 5, 4),
            "top5_dist_min": round(min(dists), 4),
            "top5_dist_max": round(max(dists), 4),
            "diversity": round(diversity_score(docs), 4),
            "judge_likert": holistic.get("likert"),
            "judge_reason": holistic.get("kisa_gerekce", "")[:200],
        })

        if qi in deepdive_set:
            for ri, (doc, dist) in enumerate(zip(docs, dists)):
                dd = await llm_judge_deepdive(client, q["query_text"], doc)
                in_tokens += dd.get("_in_tokens", 0)
                out_tokens += dd.get("_out_tokens", 0)
                deep_rows.append({
                    "query_id": q["query_id"],
                    "rank": ri + 1,
                    "form_id": results[ri].form_id,
                    "dist": round(dist, 4),
                    "judge_likert": dd.get("likert"),
                    "judge_reason": dd.get("kisa_gerekce", "")[:200],
                })

        if (qi + 1) % 10 == 0 or qi + 1 == len(queries):
            elapsed = time.perf_counter() - t0
            cost = in_tokens / 1e6 + out_tokens / 1e6 * 5
            print(
                f"  [{qi+1:>3d}/{len(queries)}]  "
                f"deep={len([r for r in deep_rows if r['query_id'] == q['query_id']]):d}  "
                f"likert={holistic.get('likert')}  "
                f"in={in_tokens:,} out={out_tokens:,}  cost~${cost:.3f}  "
                f"({elapsed:.0f}s)",
                flush=True,
            )

    cost = in_tokens / 1e6 + out_tokens / 1e6 * 5

    likerts = [r["judge_likert"] for r in rows if isinstance(r["judge_likert"], int)]
    deep_likerts = [r["judge_likert"] for r in deep_rows if isinstance(r["judge_likert"], int)]
    summary = {
        "profile": profile_name,
        "fmt": fmt,
        "n_queries": len(rows),
        "n_deepdive_results": len(deep_rows),
        "judge_holistic_mean": round(sum(likerts) / len(likerts), 3) if likerts else None,
        "judge_deepdive_mean": round(sum(deep_likerts) / len(deep_likerts), 3) if deep_likerts else None,
        "top1_dist_mean": round(sum(r["top1_dist"] for r in rows) / len(rows), 4) if rows else None,
        "diversity_mean": round(sum(r["diversity"] for r in rows) / len(rows), 4) if rows else None,
        "in_tokens": in_tokens,
        "out_tokens": out_tokens,
        "cost_usd": round(cost, 4),
        "elapsed_seconds": round(time.perf_counter() - t0, 1),
    }
    return {"summary": summary, "per_query": rows, "per_result": deep_rows}


async def main_async() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="e5-base")
    parser.add_argument("--formats", nargs="+", default=["baseline", "no_titles", "metadata"])
    parser.add_argument("--deepdive-n", type=int, default=20)
    parser.add_argument("--deepdive-seed", type=int, default=42)
    parser.add_argument("--limit-queries", type=int, default=None,
                        help="If set, evaluate only first N queries (for dry-run)")
    args = parser.parse_args()

    api_key = os.getenv("ASR_LLM__ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ASR_LLM__ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 1
    client = anthropic.Anthropic(api_key=api_key)

    queries = load_queries()
    if args.limit_queries:
        queries = queries[: args.limit_queries]
    print(f"[eval] loaded {len(queries):,} queries", flush=True)
    src_counts: dict = {}
    for q in queries:
        src_counts[q.get("source", "?")] = src_counts.get(q.get("source", "?"), 0) + 1
    print(f"[eval] sources: {src_counts}", flush=True)

    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    all_summaries: list[dict] = []
    for fmt in args.formats:
        result = await evaluate_config(
            client, args.profile, fmt, queries,
            deepdive_n=args.deepdive_n, deepdive_seed=args.deepdive_seed,
        )
        prefix = f"{args.profile}_{fmt}"

        with (_OUT_DIR / f"{prefix}_per_query.csv").open("w", encoding="utf-8", newline="") as f:
            if result["per_query"]:
                w = csv.DictWriter(f, fieldnames=list(result["per_query"][0].keys()))
                w.writeheader()
                w.writerows(result["per_query"])

        with (_OUT_DIR / f"{prefix}_per_result.csv").open("w", encoding="utf-8", newline="") as f:
            if result["per_result"]:
                w = csv.DictWriter(f, fieldnames=list(result["per_result"][0].keys()))
                w.writeheader()
                w.writerows(result["per_result"])

        with (_OUT_DIR / f"{prefix}_summary.json").open("w", encoding="utf-8") as f:
            json.dump(result["summary"], f, ensure_ascii=False, indent=2)

        all_summaries.append(result["summary"])
        print(
            f"\n[eval] {prefix} summary: "
            f"holistic={result['summary']['judge_holistic_mean']}  "
            f"deepdive={result['summary']['judge_deepdive_mean']}  "
            f"top1_dist={result['summary']['top1_dist_mean']}  "
            f"diversity={result['summary']['diversity_mean']}  "
            f"cost=${result['summary']['cost_usd']}",
            flush=True,
        )

    with (_OUT_DIR / "all_summaries.json").open("w", encoding="utf-8") as f:
        json.dump(all_summaries, f, ensure_ascii=False, indent=2)

    total_cost = sum(s["cost_usd"] for s in all_summaries)
    print(f"\n[eval] TOTAL cost across {len(all_summaries)} configs: ${total_cost:.3f}", flush=True)
    print(f"[eval] outputs in {_OUT_DIR.relative_to(_PROJECT_ROOT)}", flush=True)
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
