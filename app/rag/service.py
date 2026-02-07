# app/rag/service.py
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional, Dict, Any, List, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.rag.store import get_vector_store, DEFAULT_COLLECTION


# -----------------------------
# MariaDB (Master Data) - env 기반 inline 세팅
# -----------------------------
def _env(key: str, default: str = "") -> str:
    return (os.getenv(key, default) or "").strip()


def _build_mariadb_dsn_from_env() -> str:
    host = _env("MDB_HOST")
    port = _env("MDB_PORT")
    dbname = _env("MDB_DBNAME")
    user = _env("MDB_USER")
    password = _env("MDB_PASSWORD")
    charset = _env("MDB_CHARSET", "utf8mb4")
    extra = _env("MDB_PARAMS")

    if not dbname:
        raise RuntimeError("MDB_DBNAME 환경변수가 비어있습니다.")
    if not user:
        raise RuntimeError("MDB_USER 환경변수가 비어있습니다.")

    if extra:
        if "charset=" not in extra:
            extra = f"charset={charset}&{extra}"
        query = extra
    else:
        query = f"charset={charset}"

    return f"mysql+asyncmy://{user}:{password}@{host}:{port}/{dbname}?{query}"


@lru_cache(maxsize=1)
def _get_mariadb_engine() -> AsyncEngine:
    dsn = _build_mariadb_dsn_from_env()
    return create_async_engine(
        dsn,
        pool_pre_ping=True,
        future=True,
    )


@lru_cache(maxsize=1)
def _get_mariadb_session_factory():
    return sessionmaker(_get_mariadb_engine(), class_=AsyncSession, expire_on_commit=False)


async def _fetch_one_mariadb(sql: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    factory = _get_mariadb_session_factory()
    async with factory() as session:
        res = await session.execute(text(sql), params)
        row = res.mappings().first()
        return dict(row) if row else None


def _trim_text(s: str, max_chars: int) -> str:
    s = (s or "").replace("\n", " ").strip()
    if len(s) <= max_chars:
        return s
    return s[:max_chars].rstrip() + "…"


def _try_similarity_search_with_filter(vector_store, query: str, k: int, meta_filter: Optional[Dict[str, Any]]):
    # 메타 필터가 있으면 먼저 시도
    if meta_filter:
        try:
            results = vector_store.similarity_search(query, k=k, filter=meta_filter)
            if results:
                return results
        except Exception as e:
            print(f"⚠️ [RAG] Filter search error (ignored): {e}")

    # 필터 검색 결과가 없거나 실패 시, 일반 유사도 검색 수행
    return vector_store.similarity_search(query, k=k)


def _filter_docs_by_tags(docs: List[Any], item_name: Optional[str], variety_name: Optional[str], k: int) -> List[Any]:
    out: List[Any] = []
    for d in docs:
        md = d.metadata or {}
        # metadata 필드명이 다를 수 있으므로 유연하게 체크
        item_tags = md.get("item_tags") or md.get("item_tag") or []
        variety_tags = md.get("variety_tags") or md.get("variety_tag") or []

        # 문자열인 경우 리스트로 취급
        if isinstance(item_tags, str): item_tags = [item_tags]
        if isinstance(variety_tags, str): variety_tags = [variety_tags]

        if item_name:
            if not (isinstance(item_tags, list) and item_name in item_tags):
                continue
        if variety_name:
            if not (isinstance(variety_tags, list) and variety_name in variety_tags):
                continue

        out.append(d)
        if len(out) >= k:
            break
    return out


def search_general_reports(
        query: str,
        k: int = 3,
        doc_category: Optional[str] = None,
        period: Optional[str] = None,
        source: Optional[str] = None,
        item_tag: Optional[str] = None,
        variety_tag: Optional[str] = None,
        collection_name: str = DEFAULT_COLLECTION,
        max_context_chars: int = 1200,
) -> str:
    vector_store = get_vector_store(collection_name=collection_name)
    print(f"🔍 [RAG Search] Query='{query}', Item='{item_tag}', Variety='{variety_tag}'")

    meta_filter: Dict[str, Any] = {}
    if doc_category: meta_filter["doc_category"] = doc_category
    if period: meta_filter["period"] = period
    if source: meta_filter["source"] = source

    # 더 넓게 검색 (보통 k의 10배 정도)
    base_k = 30
    docs = _try_similarity_search_with_filter(vector_store, query, k=base_k, meta_filter=meta_filter or None)

    if not docs:
        print(f"   -> Found 0 documents in VectorStore for '{query}'. (DB가 비어있을 가능성 있음)")
        return ""

    print(f"   -> Found {len(docs)} documents before tag filtering.")

    # 태그 필터링 시도
    if item_tag or variety_tag:
        filtered_docs = _filter_docs_by_tags(docs, item_tag, variety_tag, k=k)
        if filtered_docs:
            print(f"   -> Found {len(filtered_docs)} documents after tag filtering.")
            docs = filtered_docs
        else:
            print(f"   -> ⚠️ No match for tags {item_tag}/{variety_tag}. Falling back to top-N results.")
            # 태그가 안 맞아도 가장 유사한 문서는 상위 3개 그대로 반환 (Fallback)
            docs = docs[:k]
    else:
        docs = docs[:k]
    context_list: List[str] = []
    for doc in docs[:k]:
        md = doc.metadata or {}
        period_val = md.get("period", "날짜미상")
        doc_cat_val = md.get("doc_category", "일반")
        source_val = md.get("source", "unknown")
        section_title = md.get("section_title", "")
        page = md.get("page", None)
        item_tags = md.get("item_tags", [])
        variety_tags = md.get("variety_tags", [])

        content = _trim_text(doc.page_content, max_context_chars)

        head = f"[{period_val} | {doc_cat_val} | {source_val}"
        if page is not None:
            head += f" | p.{page}"
        if section_title:
            head += f" | {section_title}"
        if item_tags:
            head += f" | item_tags={item_tags}"
        if variety_tags:
            head += f" | variety_tags={variety_tags}"
        head += "]"

        context_list.append(f"- {head} {content}")

    return "\n\n".join(context_list)


FALLBACK_SKU_MAPPER = {
    "411": "사과",
    "412": "배",
    "413": "배추",
}


async def resolve_sku_to_item_and_variety(sku_no: str) -> Tuple[str, str, str, str]:
    sku_no = (sku_no or "").strip()
    if not sku_no:
        return "", "", "", ""

    SQL = """
    SELECT
        pm.item_name      AS item_name,
        v.variety_name    AS variety_name,
        s.item_code       AS item_code,
        s.variety_code    AS variety_code
    FROM tb_sku s
    JOIN tb_produce_master pm
      ON pm.item_code = s.item_code
    JOIN tb_variety v
      ON v.item_code = s.item_code
     AND v.variety_code = s.variety_code
    WHERE s.sku_no = :sku_no
    LIMIT 1
    """

    row = await _fetch_one_mariadb(SQL, {"sku_no": sku_no})
    if not row:
        key = sku_no.split("-")[0] if "-" in sku_no else sku_no
        return FALLBACK_SKU_MAPPER.get(key, ""), "", key, ""

    item_name = str(row.get("item_name") or "").strip()
    variety_name = str(row.get("variety_name") or "").strip()
    item_code = str(row.get("item_code") or "").strip()
    variety_code = str(row.get("variety_code") or "").strip()
    return item_name, variety_name, item_code, variety_code


async def get_expert_insight(
        sku_no: str,
        query_month: Optional[int] = None,
        query_period: Optional[str] = None,  # 예: "2025-08"
        collection_name: str = DEFAULT_COLLECTION,
) -> str:
    item_name, variety_name, _, _ = await resolve_sku_to_item_and_variety(sku_no)
    if not item_name:
        return ""

    if variety_name:
        base_query = f"{item_name} {variety_name} 수급 전망 작황 가격 관측월보"
    else:
        base_query = f"{item_name} 수급 전망 작황 가격 관측월보"

    if query_month and not query_period:
        try:
            base_query += f" {int(query_month)}월"
        except Exception:
            pass

    ctx = search_general_reports(
        query=base_query,
        k=3,
        doc_category=None,
        period=query_period,
        source=None,
        item_tag=item_name,
        variety_tag=variety_name or None,
        collection_name=collection_name,
        max_context_chars=1200,
    )
    if ctx:
        return ctx

    ctx = search_general_reports(
        query=f"{item_name} 수급 전망 작황 가격 관측월보",
        k=3,
        doc_category=None,
        period=query_period,
        source=None,
        item_tag=item_name,
        variety_tag=None,
        collection_name=collection_name,
        max_context_chars=1200,
    )
    if ctx:
        return ctx

    # 3. Fallback: 태그 필터 없이 검색 (문서 내 텍스트 매칭 유도)
    return search_general_reports(
        query=f"{item_name} {variety_name or ''} 수급 전망 작황",
        k=3,
        doc_category=None,
        period=query_period,
        source=None,
        item_tag=None,  # 태그 필터 제거
        variety_tag=None,  # 태그 필터 제거
        collection_name=collection_name,
        max_context_chars=1200,
    )
