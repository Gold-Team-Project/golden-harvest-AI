# app/services/document_service.py
def build_inbound_document(data):
    return [
        [
            r["입고일자"],
            r["거래처"],
            r["품목명"],
            r["수량"],
            r["단가"],
            r["합계금액"]
        ]
        for r in data
    ]
