"""Build ICD-10 vector database — DAHİLİYE-RESTRICTED variant.

Reads filtered code list from JSON (produced by /tmp/dahiliye_filter.py),
embeds with BGE-M3 (same model as production), writes to a separate
ChromaDB directory so the full-catalog index stays untouched.

Usage:
    EMBEDDING_MODEL=bge-m3 python -m apps.backend.src.scripts.build_icd10_vectors_dahiliye \
        --input /Users/elif/Downloads/icd_dahiliye_filter/chromadb_rebuild_input.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from apps.backend.src.services.embedding_config import get_profile

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_ICD10_DB = _PROJECT_ROOT / "data" / "icd10.db"
_DEFAULT_INPUT = "/Users/elif/Downloads/icd_dahiliye_filter/chromadb_rebuild_input.json"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=_DEFAULT_INPUT,
                    help="JSON file with filtered ICD codes (icd_kodu, tani, decision)")
    ap.add_argument("--suffix", default="dahiliye",
                    help="Suffix appended to chroma dir (default: dahiliye)")
    args = ap.parse_args()

    profile = get_profile()
    base_dir = profile.icd_chroma_dir
    chroma_dir = base_dir.parent / f"{base_dir.name}_{args.suffix}"
    embedding_model = profile.model_id

    print(f"Embedding profile: {profile.name}  ({embedding_model})")
    print(f"Source JSON      : {args.input}")
    print(f"Chroma dir       : {chroma_dir}")
    print(f"(Original full-catalog dir untouched: {base_dir})")
    print()

    # Load filtered codes from JSON
    print(f"1) Filtreli ICD-10 kodları okunuyor: {args.input}")
    with open(args.input, encoding="utf-8") as f:
        filtered = json.load(f)
    filtered_codes = {item["icd_kodu"]: item for item in filtered}
    print(f"   {len(filtered_codes)} kod (include + borderline) bulundu")

    # Cross-reference with DB to get ust_kod + seviye metadata
    print(f"\n2) DB'den metadata çekiliyor: {_ICD10_DB}")
    conn = sqlite3.connect(str(_ICD10_DB))
    db_rows = conn.execute("SELECT icd_kodu, tani, ust_kod, seviye FROM icd10").fetchall()
    conn.close()
    db_lookup = {r[0]: r for r in db_rows}

    rows = []
    missing = 0
    for code, item in filtered_codes.items():
        if code not in db_lookup:
            missing += 1
            continue
        rows.append(db_lookup[code] + (item["decision"],))
    print(f"   {len(rows)} kod metadata ile eşleşti, {missing} kod DB'de bulunamadı")

    # Embed
    print(f"\n3) Embedding modeli yükleniyor: {embedding_model}")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(embedding_model)

    ids = []
    documents = []
    encode_inputs = []
    metadatas = []
    for icd_kodu, tani, ust_kod, seviye, decision in rows:
        ids.append(icd_kodu)
        text = f"{icd_kodu} {tani}"
        documents.append(text)
        encode_inputs.append(profile.passage_prefix + text)
        metadatas.append({
            "icd_kodu": icd_kodu,
            "tani": tani,
            "ust_kod": ust_kod or "",
            "seviye": seviye,
            "decision": decision,  # "include" or "borderline" — useful for diagnostic queries
        })

    print(f"\n4) {len(encode_inputs)} tanı vektörleştiriliyor (BGE-M3, batch=128)...")
    embeddings = model.encode(
        encode_inputs,
        show_progress_bar=True,
        batch_size=128,
        normalize_embeddings=True,
    )
    print(f"   Embedding boyutu: {embeddings.shape}")

    print(f"\n5) ChromaDB oluşturuluyor: {chroma_dir}")
    import chromadb

    if chroma_dir.exists():
        import shutil
        shutil.rmtree(chroma_dir)

    chroma_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = client.create_collection(
        name="icd10_vectors",
        metadata={"hnsw:space": "cosine"},
    )

    BATCH = 5000
    for i in range(0, len(ids), BATCH):
        end = min(i + BATCH, len(ids))
        collection.add(
            ids=ids[i:end],
            documents=documents[i:end],
            embeddings=embeddings[i:end].tolist(),
            metadatas=metadatas[i:end],
        )
        print(f"   {end}/{len(ids)} eklendi")

    print(f"\n6) Doğrulama:")
    print(f"   Toplam kayıt: {collection.count()}")

    test_queries = ["şeker hastalığı", "tansiyon yüksek", "öksürük"]
    for q in test_queries:
        test = collection.query(
            query_embeddings=model.encode(
                [profile.query_prefix + q],
                normalize_embeddings=True,
            ).tolist(),
            n_results=3,
        )
        print(f"\n   Test: '{q}'")
        for doc, meta, dist in zip(
            test["documents"][0],
            test["metadatas"][0],
            test["distances"][0],
        ):
            print(f"     {meta['icd_kodu']} [{meta['decision']}]: {meta['tani'][:60]} (mesafe: {dist:.3f})")

    print("\nTamamlandı!")


if __name__ == "__main__":
    main()
