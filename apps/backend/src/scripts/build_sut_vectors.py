"""Build SUT tetkik vector database using Turkish BERT embeddings + ChromaDB.

Embedding profile is chosen via the ``EMBEDDING_MODEL`` env var
(see services/embedding_config.py). Each profile writes to its own
ChromaDB directory so indexes can coexist:

    EMBEDDING_MODEL=minilm    python -m apps.backend.src.scripts.build_sut_vectors
    EMBEDDING_MODEL=e5-large  python -m apps.backend.src.scripts.build_sut_vectors
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from apps.backend.src.services.embedding_config import get_profile

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_SUT_DB = _PROJECT_ROOT / "data" / "sut_tetkik.db"


def main() -> None:
    profile = get_profile()
    chroma_dir = profile.sut_chroma_dir
    embedding_model = profile.model_id

    print(f"Embedding profile: {profile.name}  ({embedding_model})")
    print(f"Chroma dir       : {chroma_dir}")
    print()
    print(f"1) SUT tetkik kodlari okunuyor: {_SUT_DB}")
    conn = sqlite3.connect(str(_SUT_DB))
    rows = conn.execute(
        "SELECT kodu, adi, brans, ana_kategori, alt_kategori, puan FROM sut_tetkik"
    ).fetchall()
    conn.close()
    print(f"   {len(rows)} tetkik bulundu")

    print(f"\n2) Embedding modeli yukleniyor: {embedding_model}")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(embedding_model)

    ids = []
    documents = []          # raw text stored in ChromaDB (without prefix)
    encode_inputs = []      # text fed to the model (with passage prefix)
    metadatas = []
    for kodu, adi, brans, ana_kategori, alt_kategori, puan in rows:
        ids.append(kodu)
        text = f"{kodu} {adi}"
        documents.append(text)
        encode_inputs.append(profile.passage_prefix + text)
        metadatas.append({
            "kodu": kodu,
            "adi": adi,
            "brans": brans,
            "ana_kategori": ana_kategori or "",
            "alt_kategori": alt_kategori or "",
            "puan": puan or 0.0,
        })

    print(f"\n3) {len(encode_inputs)} tetkik vektorlestiriliyor...")
    # normalize_embeddings=True is required for e5 models — without it
    # cosine similarity collapses (every query returns the same generic
    # cluster). Harmless for non-e5 models too.
    embeddings = model.encode(
        encode_inputs,
        show_progress_bar=True,
        batch_size=128,
        normalize_embeddings=True,
    )
    print(f"   Embedding boyutu: {embeddings.shape}")

    print(f"\n4) ChromaDB olusturuluyor: {chroma_dir}")
    import chromadb

    if chroma_dir.exists():
        import shutil
        shutil.rmtree(chroma_dir)

    chroma_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = client.create_collection(
        name="sut_tetkik_vectors",
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

    print(f"\n5) Dogrulama:")
    print(f"   Toplam kayit: {collection.count()}")

    # Test queries
    test_queries = ["kan sayımı", "şeker testi", "röntgen", "MR"]
    for q in test_queries:
        test_results = collection.query(
            query_embeddings=model.encode(
                [profile.query_prefix + q], normalize_embeddings=True,
            ).tolist(),
            n_results=3,
        )
        print(f"\n   Test sorgusu: '{q}'")
        for meta, dist in zip(
            test_results["metadatas"][0],
            test_results["distances"][0],
        ):
            print(f"   [{meta['brans']}] {meta['kodu']}: {meta['adi']} (mesafe: {dist:.3f})")

    print("\nTamamlandi!")


if __name__ == "__main__":
    main()
