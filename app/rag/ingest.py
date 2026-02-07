# app/rag/ingest.py
from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from typing import Optional, List, Tuple

try:
    import psycopg  # psycopg3
except Exception:
    try:
        import psycopg2 as psycopg  # type: ignore
    except Exception:
        psycopg = None

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_postgres import PGVector

from app.config import embeddings, DB_CONNECTION
from app.rag.store import DEFAULT_COLLECTION
from app.rag.tagger import (
    load_item_and_variety_aliases_async,
    detect_item_tags,
    detect_variety_tags,
)


# -----------------------------
# Helpers: DB / Hash / Delete
# -----------------------------
def _require_psycopg():
    if psycopg is None:
        raise RuntimeError(
            "psycopg(또는 psycopg2)가 필요합니다."
        )


def get_pg_conn():
    _require_psycopg()
    # psycopg.connect는 순수 postgresql:// 스키마만 지원하므로 변환
    raw_conn_str = DB_CONNECTION.replace("+psycopg2", "").replace("+psycopg", "")
    return psycopg.connect(raw_conn_str)


# ✅ [추가] 테이블 초기화 함수
def init_registry_table():
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS rag_ingestion_registry (
                    collection_name VARCHAR(255) NOT NULL,
                    file_hash       VARCHAR(255) NOT NULL,
                    file_name       VARCHAR(255),
                    category        VARCHAR(255),
                    period          VARCHAR(255),
                    source          VARCHAR(255),
                    status          VARCHAR(50),
                    error           TEXT,
                    ingested_at     TIMESTAMP DEFAULT NOW(),
                    PRIMARY KEY (collection_name, file_hash)
                );
            """)
        conn.commit()
    finally:
        conn.close()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def registry_exists(collection_name: str, file_hash: str) -> bool:
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM rag_ingestion_registry
                WHERE collection_name=%s AND file_hash=%s AND status='SUCCESS'
                LIMIT 1
                """,
                (collection_name, file_hash),
            )
            return cur.fetchone() is not None
    finally:
        conn.close()


def registry_upsert_success(
    collection_name: str,
    file_name: str,
    file_hash: str,
    category: Optional[str],
    period: Optional[str],
    source: Optional[str],
):
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rag_ingestion_registry
                    (collection_name, file_name, file_hash, category, period, source, status, error)
                VALUES
                    (%s, %s, %s, %s, %s, %s, 'SUCCESS', NULL)
                ON CONFLICT (collection_name, file_hash)
                DO UPDATE SET
                    file_name=EXCLUDED.file_name,
                    category=EXCLUDED.category,
                    period=EXCLUDED.period,
                    source=EXCLUDED.source,
                    status='SUCCESS',
                    error=NULL,
                    ingested_at=NOW()
                """,
                (collection_name, file_name, file_hash, category, period, source),
            )
        conn.commit()
    finally:
        conn.close()


def registry_upsert_failed(
    collection_name: str,
    file_name: str,
    file_hash: str,
    category: Optional[str],
    period: Optional[str],
    source: Optional[str],
    error: str,
):
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rag_ingestion_registry
                    (collection_name, file_name, file_hash, category, period, source, status, error)
                VALUES
                    (%s, %s, %s, %s, %s, %s, 'FAILED', %s)
                ON CONFLICT (collection_name, file_hash)
                DO UPDATE SET
                    file_name=EXCLUDED.file_name,
                    category=EXCLUDED.category,
                    period=EXCLUDED.period,
                    source=EXCLUDED.source,
                    status='FAILED',
                    error=EXCLUDED.error,
                    ingested_at=NOW()
                """,
                (collection_name, file_name, file_hash, category, period, source, error),
            )
        conn.commit()
    finally:
        conn.close()


def delete_vectors_by_doc_id(collection_name: str, doc_id: str):
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT uuid FROM langchain_pg_collection WHERE name=%s LIMIT 1",
                (collection_name,),
            )
            row = cur.fetchone()
            if not row:
                return
            collection_uuid = row[0]

            cur.execute(
                """
                DELETE FROM langchain_pg_embedding
                WHERE collection_id=%s
                  AND (cmetadata->>'doc_id')=%s
                """,
                (collection_uuid, doc_id),
            )
        conn.commit()
    finally:
        conn.close()


# -----------------------------
# Chunking
# -----------------------------
_HEADING_RE = re.compile(
    r"(^\s*(?:\d+\.\s+|[IVX]+\.\s+|■\s+|▶\s+|○\s+|◇\s+|\[\s*.+?\s*\])\S.*$)",
    re.MULTILINE,
)


def split_by_headings(text: str) -> List[Tuple[str, str]]:
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return [("", text)]
    sections: List[Tuple[str, str]] = []
    for i, m in enumerate(matches):
        start = m.start()
        title = m.group(1).strip()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        sections.append((title, body))
    return sections


def build_chunks_from_pages(raw_documents, chunk_size=1200, chunk_overlap=150):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""],
    )
    chunks = []
    for page_doc in raw_documents:
        page_text = (page_doc.page_content or "").strip()
        if not page_text:
            continue
        page_no = page_doc.metadata.get("page", None)
        sections = split_by_headings(page_text)
        for section_title, section_text in sections:
            if len(section_text) > 8000:
                section_text = section_text[:8000]
            sub_docs = splitter.create_documents([section_text], metadatas=[page_doc.metadata])
            for d in sub_docs:
                d.metadata["section_title"] = section_title
                d.metadata["page"] = page_no
                chunks.append(d)
    for idx, d in enumerate(chunks):
        d.metadata["chunk_id"] = str(idx)
    return chunks


# -----------------------------
# Main ingest function (Async)
# -----------------------------
async def ingest_pdf_report(
    file_path: str,
    category: Optional[str],
    report_date: Optional[str],
    source: str = "KREI_관측월보",
    collection_name: str = DEFAULT_COLLECTION,
    force: bool = False,
    chunk_size: int = 1200,
    chunk_overlap: int = 150,
):
    file_name = os.path.basename(file_path)
    file_hash = sha256_file(file_path)
    doc_id = file_hash

    if not force and registry_exists(collection_name, file_hash):
        return {
            "status": "SKIPPED",
            "file_name": file_name,
            "file_hash": file_hash,
            "reason": "already_ingested",
        }

    item_aliases, variety_aliases = await load_item_and_variety_aliases_async()

    try:
        if force:
            delete_vectors_by_doc_id(collection_name, doc_id)

        print(f"   [Ingest] Loading PDF: {file_path}")
        loader = PyPDFLoader(file_path)
        raw_documents = loader.load()
        print(f"   [Ingest] Loaded {len(raw_documents)} pages.")

        if not raw_documents:
            print(f"   ⚠️ [Ingest] No text extracted from {file_name}. Check if PDF is image-only or pypdf is installed.")

        splits = build_chunks_from_pages(raw_documents, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        print(f"   [Ingest] Generated {len(splits)} chunks.")

        if splits:
            sample_text = splits[0].page_content[:100].replace('\n', ' ')
            print(f"   [Ingest] Sample chunk: {sample_text}...")

        ingested_at = datetime.utcnow().isoformat()
        # ... (tagging logic) ...
        for d in splits:
            text_ = d.page_content or ""
            item_tags = detect_item_tags(text_, item_aliases)
            variety_tags = detect_variety_tags(text_, variety_aliases)

            d.metadata["doc_category"] = category or "농업관측"
            d.metadata["period"] = report_date or "날짜미상"
            d.metadata["source"] = source
            d.metadata["file_name"] = file_name
            d.metadata["file_hash"] = file_hash
            d.metadata["doc_id"] = doc_id
            d.metadata["ingested_at"] = ingested_at
            d.metadata["item_tags"] = item_tags
            d.metadata["variety_tags"] = variety_tags

        if splits:
            print(f"   [Ingest] Storing vectors in collection '{collection_name}'...")
            PGVector.from_documents(
                embedding=embeddings,
                documents=splits,
                collection_name=collection_name,
                connection=DB_CONNECTION,
                use_jsonb=True,
            )
            print("   [Ingest] Storing vectors completed.")
        else:
            print("   ⚠️ [Ingest] No chunks to store.")

        registry_upsert_success(
            collection_name=collection_name,
            file_name=file_name,
            file_hash=file_hash,
            category=category,
            period=report_date,
            source=source,
        )

        tagged_items = sum(1 for d in splits if (d.metadata or {}).get("item_tags"))
        tagged_vars = sum(1 for d in splits if (d.metadata or {}).get("variety_tags"))
        return {
            "status": "SUCCESS",
            "file_name": file_name,
            "file_hash": file_hash,
            "pages": len(raw_documents),
            "chunks": len(splits),
            "tagged_item_chunks": tagged_items,
            "tagged_variety_chunks": tagged_vars,
            "collection_name": collection_name,
        }

    except Exception as e:
        registry_upsert_failed(
            collection_name=collection_name,
            file_name=file_name,
            file_hash=file_hash,
            category=category,
            period=report_date,
            source=source,
            error=str(e),
        )
        return {
            "status": "FAILED",
            "file_name": file_name,
            "file_hash": file_hash,
            "error": str(e),
        }