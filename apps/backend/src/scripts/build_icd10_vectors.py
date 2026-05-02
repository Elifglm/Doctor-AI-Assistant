"""Build ICD-10 vector database using Turkish BERT embeddings + ChromaDB.

Embedding profile is chosen via the ``EMBEDDING_MODEL`` env var
(see services/embedding_config.py). Each profile writes to its own
ChromaDB directory so indexes can coexist:

    EMBEDDING_MODEL=minilm    python -m apps.backend.src.scripts.build_icd10_vectors
    EMBEDDING_MODEL=e5-large  python -m apps.backend.src.scripts.build_icd10_vectors
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from apps.backend.src.services.embedding_config import get_profile

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_ICD10_DB = _PROJECT_ROOT / "data" / "icd10.db"


def main() -> None:
    profile = get_profile()
    chroma_dir = profile.icd_chroma_dir
    embedding_model = profile.model_id

    print(f"Embedding profile: {profile.name}  ({embedding_model})")
    print(f"Chroma dir       : {chroma_dir}")
    print()
    print(f"1) ICD-10 kodları okunuyor: {_ICD10_DB}")
    conn = sqlite3.connect(str(_ICD10_DB))
    rows = conn.execute("SELECT icd_kodu, tani, ust_kod, seviye FROM icd10").fetchall()
    conn.close()
    print(f"   {len(rows)} kod bulundu")

    print(f"\n2) Embedding modeli yükleniyor: {embedding_model}")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(embedding_model)

    # Prepare documents: combine code + description for richer embeddings
    ids = []
    documents = []          # raw text stored in ChromaDB
    encode_inputs = []      # text fed to the model (with passage prefix if any)
    metadatas = []
    for icd_kodu, tani, ust_kod, seviye in rows:
        ids.append(icd_kodu)
        text = f"{icd_kodu} {tani}"
        documents.append(text)
        encode_inputs.append(profile.passage_prefix + text)
        metadatas.append({
            "icd_kodu": icd_kodu,
            "tani": tani,
            "ust_kod": ust_kod or "",
            "seviye": seviye,
        })

    print(f"\n3) {len(encode_inputs)} tanı vektörleştiriliyor...")
    # normalize_embeddings=True is required for e5 models — without it
    # cosine similarity collapses. Harmless for non-e5 models.
    embeddings = model.encode(
        encode_inputs,
        show_progress_bar=True,
        batch_size=128,
        normalize_embeddings=True,
    )
    print(f"   Embedding boyutu: {embeddings.shape}")

    print(f"\n4) ChromaDB oluşturuluyor: {chroma_dir}")
    import chromadb

    # Clean start
    if chroma_dir.exists():
        import shutil
        shutil.rmtree(chroma_dir)

    chroma_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(chroma_dir))
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
        query_embeddings=model.encode(
            [profile.query_prefix + "şeker hastalığı"],
            normalize_embeddings=True,
        ).tolist(),
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
