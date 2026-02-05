# app/rag/tagger.py
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Dict, List, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker


# -----------------------------
# Utils
# -----------------------------
def _normalize(s: str) -> str:
    return (s or "").strip()


def _env(key: str, default: str = "") -> str:
    return (os.getenv(key, default) or "").strip()


def _load_aliases_from_env_json(env_key: str) -> Dict[str, List[str]]:
    raw = os.getenv(env_key, "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        out: Dict[str, List[str]] = {}
        for k, v in data.items():
            key = _normalize(k)
            if not key:
                continue
            if isinstance(v, list):
                arr = [_normalize(x) for x in v if _normalize(x)]
                if arr:
                    out[key] = arr
            elif isinstance(v, str) and _normalize(v):
                out[key] = [_normalize(v)]
        return out
    except Exception:
        return {}


def _load_aliases_from_env_list(env_key: str) -> Dict[str, List[str]]:
    raw = os.getenv(env_key, "").strip()
    if not raw:
        return {}
    names = [_normalize(x) for x in raw.split(",") if _normalize(x)]
    return {n: [n] for n in names} if names else {}


# -----------------------------
# MariaDB (Master Data)
# -----------------------------
def _build_mariadb_dsn_from_env() -> str:
    host = _env("MDB_HOST", "localhost")
    port = _env("MDB_PORT", "3306")
    dbname = _env("MDB_DBNAME")
    user = _env("MDB_USER")
    password = _env("MDB_PASSWORD")
    charset = _env("MDB_CHARSET", "utf8mb4")
    extra = _env("MDB_PARAMS")

    if not dbname or not user:
        raise RuntimeError("MDB_DBNAME 또는 MDB_USER 환경변수가 비어있습니다.")

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
    return create_async_engine(dsn, pool_pre_ping=True, future=True)


@lru_cache(maxsize=1)
def _get_session_factory():
    return sessionmaker(_get_mariadb_engine(), class_=AsyncSession, expire_on_commit=False)


async def _fetch_names(sql: str) -> List[str]:
    factory = _get_session_factory()
    async with factory() as session:
        res = await session.execute(text(sql))
        rows = res.fetchall()
        out: List[str] = []
        for r in rows:
            v = r[0] if r else None
            s = _normalize(str(v) if v is not None else "")
            if s:
                out.append(s)
        return list(dict.fromkeys(out))


async def _load_item_names_from_db() -> List[str]:
    sql = "SELECT item_name FROM tb_produce_master WHERE item_name IS NOT NULL AND item_name <> ''"
    return await _fetch_names(sql)


async def _load_variety_names_from_db() -> List[str]:
    sql = "SELECT variety_name FROM tb_variety WHERE variety_name IS NOT NULL AND variety_name <> ''"
    return await _fetch_names(sql)


# -----------------------------
# Tag detection
# -----------------------------
def _detect_tags(text: str, aliases: Dict[str, List[str]]) -> List[str]:
    t = text or ""
    hits: List[str] = []

    for canonical, keys in (aliases or {}).items():
        name = _normalize(canonical)
        if not name:
            continue
        found = False
        for k in keys:
            key = _normalize(k)
            if not key:
                continue
            try:
                pat = rf"(^|[\s\[\(\{{<\"'“‘,.;:|/\\\-]){re.escape(key)}($|[\s\]\)\}}>\"'”’,.;:|/\\\-])"
                if re.search(pat, t):
                    found = True
                    break
            except Exception:
                pass
            if key in t:
                found = True
                break
        if found:
            hits.append(name)
    return list(dict.fromkeys(hits))


# -----------------------------
# Public API
# -----------------------------
async def load_item_and_variety_aliases_async() -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """
    비동기 버전의 태그 로더.
    """
    # 1) ENV JSON
    item_aliases = _load_aliases_from_env_json("RAG_ITEM_ALIASES_JSON")
    variety_aliases = _load_aliases_from_env_json("RAG_VARIETY_ALIASES_JSON")
    if item_aliases and variety_aliases:
        return item_aliases, variety_aliases

    # 2) ENV list
    if not item_aliases:
        item_aliases = _load_aliases_from_env_list("RAG_ITEM_NAMES")
    if not variety_aliases:
        variety_aliases = _load_aliases_from_env_list("RAG_VARIETY_NAMES")

    if item_aliases and variety_aliases:
        return item_aliases, variety_aliases

    # 3) MariaDB (Async)
    try:
        if not item_aliases:
            items = await _load_item_names_from_db()
            if items:
                item_aliases = {n: [n] for n in items}

        if not variety_aliases:
            vars_ = await _load_variety_names_from_db()
            if vars_:
                variety_aliases = {n: [n] for n in vars_}
    except Exception:
        pass

    # 4) Fallback
    if not item_aliases:
        item_aliases = {
            "사과": ["사과", "부사", "홍로", "후지"],
            "배": ["배", "신고"],
            "포도": ["포도", "샤인머스캣", "캠벨", "캠벨얼리"],
            "감귤": ["감귤", "귤", "온주"],
            "딸기": ["딸기"],
        }
    if not variety_aliases:
        variety_aliases = {
            "홍로": ["홍로"],
            "부사": ["부사", "후지"],
            "샤인머스캣": ["샤인머스캣", "샤인 머스캣"],
            "캠벨": ["캠벨", "캠벨얼리"],
            "신고": ["신고"],
            "온주": ["온주"],
        }

    return item_aliases, variety_aliases


def detect_item_tags(text: str, item_aliases: Dict[str, List[str]]) -> List[str]:
    return _detect_tags(text, item_aliases)


def detect_variety_tags(text: str, variety_aliases: Dict[str, List[str]]) -> List[str]:
    return _detect_tags(text, variety_aliases)