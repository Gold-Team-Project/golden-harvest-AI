from __future__ import annotations

import os
from datetime import date
from typing import Any, Dict, List, Optional

import pymysql
from pymysql.cursors import DictCursor


def _require_env(name: str) -> str:
    v = os.getenv(name)
    if v is None or v == "":
        raise RuntimeError(f"{name} is missing in environment.")
    return v


def _db_cfg() -> Dict[str, Any]:
    return {
        "host": _require_env("MDB_HOST"),
        "port": int(_require_env("MDB_PORT")),
        "database": _require_env("MDB_DBNAME"),
        "user": _require_env("MDB_USER"),
        "password": _require_env("MDB_PASSWORD"),
    }


def get_db_connection() -> pymysql.connections.Connection:
    cfg = _db_cfg()
    return pymysql.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
    )


def fetch_outbound_history_by_sku(
    sku_no: str,
    start_date: date,
    end_date: date,
    lot_no: Optional[str] = None,
) -> List[Dict[str, Any]]:
    sql = """
        SELECT
            o.outbound_date   AS outbound_date,
            o.quantity        AS quantity,
            o.outbound_price  AS outboundPrice,
            l.sku_no          AS skuNo,
            o.lot_no          AS lotNo
        FROM tb_outbound o
        JOIN tb_lot l
          ON o.lot_no = l.lot_no
        WHERE l.sku_no = %s
          AND o.outbound_date BETWEEN %s AND %s
    """

    params: List[Any] = [sku_no, start_date, end_date]

    if lot_no:
        sql += " AND o.lot_no = %s"
        params.append(lot_no)

    sql += " ORDER BY o.outbound_date"

    conn: Optional[pymysql.connections.Connection] = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()  # list[dict]
    except Exception as e:
        print(f"DB Error(fetch_outbound_history_by_sku): {e}")
        return []
    finally:
        if conn:
            conn.close()

