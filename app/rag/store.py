# app/rag/store.py
from langchain_postgres import PGVector
from app.config import embeddings, DB_CONNECTION

def get_vector_store():
    return PGVector(
        embeddings=embeddings,
        collection_name="agri_reports",
        connection=DB_CONNECTION,
        use_jsonb=True,
    )