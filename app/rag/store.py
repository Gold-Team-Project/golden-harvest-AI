# app/rag/store.py
import os
from functools import lru_cache
from langchain_postgres import PGVector
from app.config import embeddings, DB_CONNECTION

DEFAULT_COLLECTION = os.getenv("RAG_COLLECTION", "agri_reports")

@lru_cache(maxsize=1)
def get_vector_store(collection_name: str = DEFAULT_COLLECTION) -> PGVector:
    return PGVector(
        embeddings=embeddings,
        collection_name=collection_name,
        connection=DB_CONNECTION,
        use_jsonb=True,
    )
