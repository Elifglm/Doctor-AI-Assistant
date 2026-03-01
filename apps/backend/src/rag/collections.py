"""ChromaDB collection definitions for medical RAG."""

COLLECTIONS = {
    "medical_knowledge": {
        "description": "ICD-10 TR kodlari, klinik kilavuzlar, ilac bilgileri",
        "metadata": {"hnsw:space": "cosine"},
    },
}
