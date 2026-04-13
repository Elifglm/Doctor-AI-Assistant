"""Build SUT tetkik vector database using Turkish BERT embeddings + ChromaDB."""

from __future__ import annotations

import sqlite3
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_SUT_DB = _PROJECT_ROOT / "data" / "sut_tetkik.db"
_CHROMA_DIR = _PROJECT_ROOT / "data" / "sut_tetkik_chroma"
_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def main() -> None:
    print(f"1) SUT tetkik kodlari okunuyor: {_SUT_DB}")
    conn = sqlite3.connect(str(_SUT_DB))
    rows = conn.execute(
        "SELECT kodu, adi, brans, ana_kategori, alt_kategori, puan FROM sut_tetkik"
    ).fetchall()
    conn.close()
    print(f"   {len(rows)} tetkik bulundu")

    print(f"\n2) Embedding modeli yukleniyor: {_EMBEDDING_MODEL}")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(_EMBEDDING_MODEL)

    ids = []
    documents = []
    metadatas = []
    for kodu, adi, brans, ana_kategori, alt_kategori, puan in rows:
        ids.append(kodu)
        # Document text: code + name for better matching
        documents.append(f"{kodu} {adi}")
        metadatas.append({
            "kodu": kodu,
            "adi": adi,
            "brans": brans,
            "ana_kategori": ana_kategori or "",
            "alt_kategori": alt_kategori or "",
            "puan": puan or 0.0,
        })

    print(f"\n3) {len(documents)} tetkik vektorlestiriliyor...")
    embeddings = model.encode(documents, show_progress_bar=True, batch_size=128)
    print(f"   Embedding boyutu: {embeddings.shape}")

    print(f"\n4) ChromaDB olusturuluyor: {_CHROMA_DIR}")
    import chromadb

    if _CHROMA_DIR.exists():
        import shutil
        shutil.rmtree(_CHROMA_DIR)

    _CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(_CHROMA_DIR))
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
            query_embeddings=model.encode([q]).tolist(),
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
