import jaydebeapi
import re
from datetime import date
from app.document.schemas.documents import DocumentType, DocumentIntent
from app.document.templates.inbound_excel import build_inbound_excel
from app.document.templates.outbound_excel import build_outbound_excel

H2_JAR_PATH = r"C:\Users\rbwls\h2/bin\h2-2.2.224.jar"

# DB 연결 정보
DB_URL = "jdbc:h2:tcp://localhost/~/test2"
DB_USER = "sa"
DB_PASSWORD = ""
DB_DRIVER = "org.h2.Driver"


def get_db_connection():
    conn = jaydebeapi.connect(
        DB_DRIVER,
        DB_URL,
        [DB_USER, DB_PASSWORD],
        H2_JAR_PATH
    )
    return conn

def camel_to_snake(name: str) -> str:
    # outboundDate → outbound_date
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def dict_fetchall(cursor):
    """
    JDBC 결과(Tuple)를 Dictionary 리스트로 변환
    - 컬럼명: camelCase / 대문자 → snake_case 소문자
    """
    columns = [camel_to_snake(col[0]) for col in cursor.description]

    return [
        dict(zip(columns, row))
        for row in cursor.fetchall()
    ]
# 2. 직접 쿼리 실행 함수 (Inbound)
def fetch_inbound_from_db(start_date, end_date):
    # H2(JDBC)는 파라미터 플레이스홀더로 '?'를 사용합니다.
    sql = """
        SELECT 
            i.inbound_date AS "inboundDate",
            i.sku_no AS "skuNo",
            i.quantity AS "quantity"
        FROM tb_inbound i
        WHERE i.inbound_date BETWEEN ? AND ?
        ORDER BY i.inbound_date DESC
    """

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(sql, (str(start_date), str(end_date)))
            result = dict_fetchall(cursor)  # 딕셔너리 변환
            print(f"💾 DB 조회(Inbound): {len(result)}건")
            return result
    except Exception as e:
        print(f"❌ DB Error(Inbound): {e}")
        return []
    finally:
        if conn:
            conn.close()


# 3. 직접 쿼리 실행 함수 (Outbound)
def fetch_outbound_from_db(start_date, end_date):
    # Alias에 쌍따옴표("")를 붙여야 대소문자가 유지되는 경우가 많습니다(H2 설정에 따라 다름)
    sql = """
        SELECT 
            o.outbound_date AS "outboundDate",
            o.lot_no AS "lotNo",
            l.sku_no AS "skuNo",
            o.quantity AS "quantity",
            o.outbound_price AS "outboundPrice"
        FROM
            tb_outbound AS o
        JOIN
           tb_lot AS l
        ON o.lot_no = l.lot_no
        WHERE 
            o.outbound_date BETWEEN ? AND ?
        ORDER BY o.outbound_date DESC
    """

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(sql, (str(start_date), str(end_date)))
            result = dict_fetchall(cursor)  # 딕셔너리 변환
            print(f"💾 DB 조회(Outbound): {len(result)}건")
            return result
    except Exception as e:
        print(f"❌ DB Error(Outbound): {e}")
        return []
    finally:
        if conn:
            conn.close()


def get_data_for_intent(intent: DocumentIntent):
    base_data = {
        "start_date": intent.start_date,
        "end_date": intent.end_date,
        "created_at": date.today().strftime("%Y-%m-%d")
    }

    # INBOUND 처리
    if intent.document_type == DocumentType.INBOUND:
        db_rows = fetch_inbound_from_db(intent.start_date, intent.end_date)
        items = [
            {
                # 키 값을 모두 소문자로 변경
                "date": row.get("inbound_date"),
                "sku": row.get("sku_no"),
                "qty": row.get("quantity")
            }
            for row in db_rows
        ]
        return build_inbound_excel(base_data, items)

    # OUTBOUND 처리
    elif intent.document_type == DocumentType.OUTBOUND:
        db_rows = fetch_outbound_from_db(intent.start_date, intent.end_date)
        items = []
        for row in db_rows:
            # 여기도 키 값을 모두 소문자로 변경
            items.append({
                "date": row.get("outbound_date"),
                "LOT": row.get("lot_no"),
                "sku": row.get("sku_no"),
                "qty": row.get("quantity", 0),
                "price": row.get("outbound_price", 0),
                "amount": row.get("quantity", 0) * row.get("outbound_price", 0)
            })

            print(db_rows[0])
        return build_outbound_excel(base_data, items)

    return {}