import jaydebeapi
import os
from datetime import date
from typing import List, Dict, Optional


H2_JAR_PATH = r"C:\Users\rbwls\h2/bin\h2-2.2.224.jar"

DB_URL = "jdbc:h2:tcp://localhost/~/test2"
DB_USER = "sa"
DB_PASSWORD = ""
DB_DRIVER = "org.h2.Driver"


def fetch_outbound_history_by_sku(
    sku_no: str,
    start_date: date,
    end_date: date,
    lot_no: Optional[str] = None
) -> List[Dict]:
    """
    SKU 기준 출고 이력을 조회합니다.
    (Java OutboundMapper.findAllOutbounds 쿼리 구조를 그대로 따름)
    """

    if not os.path.exists(H2_JAR_PATH):
        return []

    sql = """
        SELECT
            o.outbound_date   AS "outboundDate",
            o.quantity        AS "quantity",
            o.outbound_price  AS "outboundPrice",
            l.sku_no          AS "skuNo",
            o.lot_no          AS "lotNo"
        FROM tb_outbound o
        JOIN tb_lot l
          ON o.lot_no = l.lot_no
        WHERE l.sku_no = ?
          AND o.outbound_date BETWEEN ? AND ?
    """

    params = [sku_no, str(start_date), str(end_date)]

    if lot_no:
        sql += " AND o.lot_no = ?"
        params.append(lot_no)

    sql += " ORDER BY o.outbound_date"

    conn = None
    cursor = None

    try:
        conn = jaydebeapi.connect(
            DB_DRIVER,
            DB_URL,
            [DB_USER, DB_PASSWORD],
            H2_JAR_PATH
        )
        cursor = conn.cursor()

        cursor.execute(sql, params)

        columns = [col[0].lower() for col in cursor.description]
        rows = cursor.fetchall()

        result = [dict(zip(columns, row)) for row in rows]

        return result

    except Exception as e:
        return []

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
