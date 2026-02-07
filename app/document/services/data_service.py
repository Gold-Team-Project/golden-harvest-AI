from __future__ import annotations

import os
from datetime import date
from typing import Any, Dict, List, Optional

import pymysql
from pymysql.cursors import DictCursor

from app.document.schemas.documents import DocumentType, DocumentIntent
from app.document.templates.inbound_excel import build_inbound_excel
from app.document.templates.outbound_excel import build_outbound_excel

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

# =========================
# DB 조회 (Inbound)
# =========================
def fetch_inbound_from_db(start_date, end_date) -> List[Dict[str, Any]]:
    """
    tb_inbound + Master Data 조인
    반환: [{inbound_date, sku_no, quantity, item_name, variety_name, grade_name}, ...]
    """
    sql = """
        SELECT
            i.inbound_date   AS inbound_date,
            i.sku_no         AS sku_no,
            pm.item_name     AS item_name,
            v.variety_name   AS variety_name,
            g.grade_name     AS grade_name,
            i.quantity       AS quantity
        FROM tb_inbound i
        JOIN tb_sku s ON i.sku_no = s.sku_no
        JOIN tb_produce_master pm ON s.item_code = pm.item_code
        JOIN tb_variety v ON s.item_code = v.item_code AND s.variety_code = v.variety_code
        JOIN tb_grade g ON s.grade_code = g.grade_code
        WHERE i.inbound_date BETWEEN %s AND %s
        ORDER BY i.inbound_date DESC
    """

    conn: Optional[pymysql.connections.Connection] = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(sql, (start_date, end_date))
            rows = cursor.fetchall()
            print(f"💾 DB 조회(Inbound): {len(rows)}건")
            return rows
    except Exception as e:
        print(f"DB Error(Inbound): {e}")
        return []
    finally:
        if conn:
            conn.close()


# =========================
# DB 조회 (Outbound)
# =========================
def fetch_outbound_from_db(start_date, end_date) -> List[Dict[str, Any]]:
    """
    tb_outbound + tb_lot + Master Data 조인
    """
    sql = """
        SELECT
            o.outbound_date   AS outbound_date,
            o.lot_no          AS lot_no,
            l.sku_no          AS sku_no,
            pm.item_name      AS item_name,
            v.variety_name    AS variety_name,
            g.grade_name      AS grade_name,
            o.quantity        AS quantity,
            o.outbound_price  AS outbound_price
        FROM tb_outbound o
        JOIN tb_lot l ON o.lot_no = l.lot_no
        JOIN tb_sku s ON l.sku_no = s.sku_no
        JOIN tb_produce_master pm ON s.item_code = pm.item_code
        JOIN tb_variety v ON s.item_code = v.item_code AND s.variety_code = v.variety_code
        JOIN tb_grade g ON s.grade_code = g.grade_code
        WHERE o.outbound_date BETWEEN %s AND %s
        ORDER BY o.outbound_date DESC
    """

    conn: Optional[pymysql.connections.Connection] = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(sql, (start_date, end_date))
            rows = cursor.fetchall()
            print(f"💾 DB 조회(Outbound): {len(rows)}건")
            return rows
    except Exception as e:
        print(f"DB Error(Outbound): {e}")
        return []
    finally:
        if conn:
            conn.close()


# =========================
# Intent → Excel 생성
# =========================
def get_data_for_intent(intent: DocumentIntent):
    """
    intent(document_type, start_date, end_date)에 따라
    DB 조회 후 Excel 생성(build_inbound_excel/build_outbound_excel) 결과 반환
    """
    base_data = {
        "start_date": intent.start_date,
        "end_date": intent.end_date,
        "created_at": date.today().strftime("%Y-%m-%d"),
    }

    # INBOUND
    if intent.document_type == DocumentType.INBOUND:
        db_rows = fetch_inbound_from_db(intent.start_date, intent.end_date)
        items = [
            {
                "date": row.get("inbound_date"),
                "sku": row.get("sku_no"),
                "item_name": row.get("item_name"),
                "variety_name": row.get("variety_name"),
                "grade_name": row.get("grade_name"),
                "qty": row.get("quantity"),
            }
            for row in db_rows
        ]
        return build_inbound_excel(base_data, items)

    # OUTBOUND
    if intent.document_type == DocumentType.OUTBOUND:
        db_rows = fetch_outbound_from_db(intent.start_date, intent.end_date)

        items: List[Dict[str, Any]] = []
        for row in db_rows:
            qty = row.get("quantity") or 0
            price = row.get("outbound_price") or 0

            items.append(
                {
                    "date": row.get("outbound_date"),
                    "LOT": row.get("lot_no"),
                    "sku": row.get("sku_no"),
                    "item_name": row.get("item_name"),
                    "variety_name": row.get("variety_name"),
                    "grade_name": row.get("grade_name"),
                    "qty": qty,
                    "price": price,
                    "amount": qty * price,
                }
            )

        if db_rows:
            print("sample row:", db_rows[0])

        return build_outbound_excel(base_data, items)

    return {}


if __name__ == "__main__":
    print("Set MDB_* env vars and call get_data_for_intent(intent) from your app.")
