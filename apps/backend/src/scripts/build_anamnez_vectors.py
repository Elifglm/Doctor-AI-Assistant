"""Build a ChromaDB collection of dahiliye anamneses for retrieval.

Reads ic_anamnez_filt_v1_corpus, formats embedding text per the chosen
ablation format (baseline / no_titles / metadata), and encodes via the
selected embedding profile (bge-m3 / e5-base / etc.). Each (profile, format)
combination gets its own ChromaDB directory and collection so they stay
side-by-side for evaluation.

Usage:
    python -m apps.backend.src.scripts.build_anamnez_vectors \\
        --profile e5-base --format baseline [--batch-size 8] [--device cuda]

Per Faz 0 strategy B: run 3 passes with e5-base (one per format), pick the
winner from eval, then run 1 final pass with bge-m3 on the winning format.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from apps.backend.src.rag.embed_text_builder import FORMATS, build
from apps.backend.src.rag.phi_guard import mask_phi_count
from apps.backend.src.services.embedding_config import PROFILES, get_profile

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DB_PATH = _PROJECT_ROOT / "data" / "anamnez.db"


def chroma_dir_for(profile: str, fmt: str) -> Path:
    return _PROJECT_ROOT / "data" / f"anamnez_chroma_{profile}_{fmt}"


def collection_name_for(fmt: str) -> str:
    return f"anamnez_{fmt}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True, choices=sorted(PROFILES))
    parser.add_argument("--format", required=True, choices=FORMATS)
    parser.add_argument("--source", default="ic_anamnez_filt_v1_corpus")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--device", default=None, help="cuda / cpu (auto-detect if omitted)")
    parser.add_argument(
        "--max-seq-length", type=int, default=512,
        help="Truncate inputs at this token length (default 512; ample for our texts)",
    )
    args = parser.parse_args()

    if not _DB_PATH.exists():
        print(f"DB not found: {_DB_PATH}", file=sys.stderr)
        return 1

    profile = get_profile(args.profile)
    chroma_path = chroma_dir_for(args.profile, args.format)
    collection_name = collection_name_for(args.format)

    print(f"[build] profile={profile.name}  model={profile.model_id}", flush=True)
    print(f"[build] format={args.format}", flush=True)
    print(f"[build] source={args.source}", flush=True)
    print(f"[build] chroma_dir={chroma_path.relative_to(_PROJECT_ROOT)}", flush=True)
    print(f"[build] collection={collection_name}", flush=True)
    print(f"[build] batch_size={args.batch_size}  device={args.device or 'auto'}", flush=True)
    print()

    # --- 1. Read corpus ---
    with sqlite3.connect(_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = list(conn.execute(f'SELECT * FROM "{args.source}"'))
    n_rows = len(rows)
    print(f"[build] corpus: {n_rows:,} rows", flush=True)

    # --- 2. Format texts (with defense-in-depth PHI mask) ---
    t0 = time.perf_counter()
    texts: list[str] = []
    keep_indices: list[int] = []
    metadatas: list[dict] = []
    phi_totals = {"tc": 0, "phone": 0, "email": 0}
    for i, row in enumerate(rows):
        text = build(dict(row), args.format)
        if not text.strip():
            continue
        text, phi_counts = mask_phi_count(text)
        for k, v in phi_counts.items():
            phi_totals[k] += v
        if profile.passage_prefix:
            text = profile.passage_prefix + text
        texts.append(text)
        keep_indices.append(i)
        # Lean metadata — vital values stored separately for filterable queries
        meta: dict = {"form_id": int(row["FORM_ID"])}
        for k in ("sistolik", "diyastolik", "nabiz", "ates", "so2", "boy", "kilo", "agri_skalasi"):
            v = row[k]
            if v is None:
                continue
            try:
                meta[k] = float(v)
            except (TypeError, ValueError):
                meta[k] = str(v)[:64]
        for k in ("sigara", "alkol", "alerji"):
            v = row[k]
            if v is not None and str(v).strip():
                meta[k] = str(v).strip()[:128]
        metadatas.append(meta)
    print(f"[build] formatted {len(texts):,} non-empty texts in {time.perf_counter()-t0:.1f}s", flush=True)
    if any(phi_totals.values()):
        print(f"[build] PHI masked: tc={phi_totals['tc']} phone={phi_totals['phone']} email={phi_totals['email']}", flush=True)
    else:
        print("[build] PHI masked: 0 hits (defense-in-depth, expected from prior scan)", flush=True)

    if not texts:
        print("[ERROR] no non-empty texts to embed", file=sys.stderr)
        return 1

    # --- 3. Load embedding model ---
    t1 = time.perf_counter()
    print(f"[build] loading model {profile.model_id}...", flush=True)
    model_kwargs: dict = {}
    if args.device:
        model_kwargs["device"] = args.device
    model = SentenceTransformer(profile.model_id, **model_kwargs)
    if args.max_seq_length:
        model.max_seq_length = args.max_seq_length
    print(f"[build] model loaded in {time.perf_counter()-t1:.1f}s  device={model.device}", flush=True)

    # --- 4. Encode in batches with fp16 if on cuda ---
    t2 = time.perf_counter()
    use_fp16 = "cuda" in str(model.device).lower()
    embeddings = model.encode(
        texts,
        batch_size=args.batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
        precision="float32",  # store fp32 in chroma; fp16 only for compute
    )
    elapsed = time.perf_counter() - t2
    sps = len(texts) / elapsed if elapsed else 0
    print(f"[build] encoded {len(texts):,} texts in {elapsed:.1f}s  ({sps:.1f} sentences/sec)", flush=True)
    print(f"[build] embedding dim: {embeddings.shape[1]}", flush=True)

    # --- 5. Write to ChromaDB ---
    t3 = time.perf_counter()
    chroma_path.parent.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(chroma_path))
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    collection = client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    ids = [f"row_{i}_{rows[idx]['FORM_ID']}" for i, idx in enumerate(keep_indices)]
    BATCH = 1000
    for i in range(0, len(texts), BATCH):
        collection.add(
            ids=ids[i : i + BATCH],
            embeddings=embeddings[i : i + BATCH].tolist(),
            metadatas=metadatas[i : i + BATCH],
            documents=texts[i : i + BATCH],
        )
    n_in_collection = collection.count()
    print(f"[build] wrote {n_in_collection:,} docs to chroma in {time.perf_counter()-t3:.1f}s", flush=True)

    # --- 6. Smoke query ---
    print("\n[smoke] querying with sample text...", flush=True)
    sample_query = profile.query_prefix + "boğaz ağrısı öksürük halsizlik 2 gündür"
    sample_emb = model.encode([sample_query], normalize_embeddings=True, convert_to_numpy=True)
    res = collection.query(query_embeddings=sample_emb.tolist(), n_results=3)
    for i, (doc_id, doc, dist) in enumerate(zip(res["ids"][0], res["documents"][0], res["distances"][0])):
        snippet = doc[:120].replace("\n", " ") + ("..." if len(doc) > 120 else "")
        print(f"  #{i+1}  dist={dist:.4f}  {doc_id}  | {snippet}")

    # --- 7. Persist run summary ---
    summary = {
        "profile": profile.name,
        "model_id": profile.model_id,
        "format": args.format,
        "source": args.source,
        "n_corpus": n_rows,
        "n_embedded": len(texts),
        "embed_dim": int(embeddings.shape[1]),
        "encode_seconds": round(elapsed, 2),
        "sentences_per_sec": round(sps, 2),
        "device": str(model.device),
        "chroma_dir": str(chroma_path.relative_to(_PROJECT_ROOT)),
        "collection": collection_name,
    }
    summary_path = chroma_path / "build_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[build] summary -> {summary_path.relative_to(_PROJECT_ROOT)}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
