"""Build ICD-10 vector database using Turkish BERT embeddings + ChromaDB."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_ICD10_DB = _PROJECT_ROOT / "data" / "icd10.db"
_CHROMA_DIR = _PROJECT_ROOT / "data" / "icd10_chroma"
_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def main() -> None:
    print(f"1) ICD-10 kodları okunuyor: {_ICD10_DB}")
    conn = sqlite3.connect(str(_ICD10_DB))
    rows = conn.execute("SELECT icd_kodu, tani, ust_kod, seviye FROM icd10").fetchall()
    conn.close()
    print(f"   {len(rows)} kod bulundu")

    print(f"\n2) Embedding modeli yükleniyor: {_EMBEDDING_MODEL}")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(_EMBEDDING_MODEL)

    # Prepare documents: combine code + description for richer embeddings
    ids = []
    documents = []
    metadatas = []
    for icd_kodu, tani, ust_kod, seviye in rows:
        ids.append(icd_kodu)
        # Document text: both code and Turkish description for better matching
        documents.append(f"{icd_kodu} {tani}")
        metadatas.append({
            "icd_kodu": icd_kodu,
            "tani": tani,
            "ust_kod": ust_kod or "",
            "seviye": seviye,
        })

    print(f"\n3) {len(documents)} tanı vektörleştiriliyor...")
    embeddings = model.encode(documents, show_progress_bar=True, batch_size=128)
    print(f"   Embedding boyutu: {embeddings.shape}")

    print(f"\n4) ChromaDB oluşturuluyor: {_CHROMA_DIR}")
    import chromadb

    # Clean start
    if _CHROMA_DIR.exists():
        import shutil
        shutil.rmtree(_CHROMA_DIR)

    _CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(_CHROMA_DIR))
    collection = client.create_collection(
        name="icd10_vectors",
        metadata={"hnsw:space": "cosine"},
    )

    # ChromaDB has batch limits, insert in chunks
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

    print(f"\n5) Doğrulama:")
    print(f"   Toplam kayıt: {collection.count()}")

    # Test query
    test_results = collection.query(
        query_embeddings=model.encode(["şeker hastalığı"]).tolist(),
        n_results=5,
    )
    print(f"\n   Test sorgusu: 'şeker hastalığı'")
    for doc, meta, dist in zip(
        test_results["documents"][0],
        test_results["metadatas"][0],
        test_results["distances"][0],
    ):
        print(f"   {meta['icd_kodu']}: {meta['tani']} (mesafe: {dist:.3f})")

    print("\nTamamlandı!")


if __name__ == "__main__":
    main()
