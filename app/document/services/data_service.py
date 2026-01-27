import requests
from datetime import date
from app.document.schemas.documents import DocumentType, DocumentIntent
from app.document.templates.inbound_excel import build_inbound_excel
from app.document.templates.outbound_excel import build_outbound_excel

# Java 서버 주소
JAVA_API_URL = "http://localhost:8088"


# Java API 연동
def fetch_inbound_from_java(start_date, end_date):
    try:
        params = {
            "page": 1,
            "size": 200,
            "startDate": str(start_date),
            "endDate": str(end_date)
        }

        print(f"📡 Java 서버 입고 요청: {JAVA_API_URL}/api/inbound {params}")

        response = requests.get(f"{JAVA_API_URL}/api/inbound", params=params)
        response.raise_for_status()

        return response.json().get("data", [])
    except Exception as e:
        print(f"INBOUND 통신 실패: {e}")
        return []


def fetch_outbound_from_java(start_date, end_date):
    try:
        params = {
            "page": 1,
            "size": 200,
            "startDate": str(start_date),
            "endDate": str(end_date)
        }

        print(f"📡 Java 서버 출고 요청: {JAVA_API_URL}/api/outbound {params}")

        response = requests.get(f"{JAVA_API_URL}/api/outbound", params=params)
        response.raise_for_status()

        return response.json().get("data", [])
    except Exception as e:
        print(f"OUTBOUND 통신 실패: {e}")
        return []

def get_data_for_intent(intent: DocumentIntent):

    base_data = {
        "start_date": intent.start_date,
        "end_date": intent.end_date,
        "created_at": date.today().strftime("%Y-%m-%d")
    }

    # INBOUND
    if intent.document_type == DocumentType.INBOUND:
        java_rows = fetch_inbound_from_java(
            intent.start_date,
            intent.end_date
        )

        items = [
            {
                "date": row.get("inboundDate"),
                "sku": row.get("skuNo"),
                "qty": row.get("quantity")
            }
            for row in java_rows
        ]

        return build_inbound_excel(base_data, items)

    # OUTBOUND
    elif intent.document_type == DocumentType.OUTBOUND:
        java_rows = fetch_outbound_from_java(
            intent.start_date,
            intent.end_date
        )

        items = []
        for row in java_rows:
            qty = row.get("quantity", 0)
            price = row.get("outboundPrice", 0)

            items.append({
                "date": row.get("outboundDate"),
                "LOT": row.get("lotNo"),
                "sku": row.get("skuNo"),
                "qty": qty,
                "price": price,
                "amount": qty * price
            })

        return build_outbound_excel(base_data, items)

    return {}
