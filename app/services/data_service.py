from app.schemas.documents import DocumentType, DocumentIntent


def get_data_for_intent(intent: DocumentIntent) -> dict:
    base = {
        "start_date": intent.start_date,
        "end_date": intent.end_date,
        "created_at": "2026-01-21"
    }

    if intent.document_type == DocumentType.INBOUND:
        return {**base, "title": "입고 내역서", "headers": ["입고일자", "거래처", "품목", "수량", "단가", "금액"], "items": [
            {"d": "2026-01-10", "v": "알파유통", "i": "노트북", "q": 5, "p": 1200000, "a": 6000000}
        ]}

    elif intent.document_type == DocumentType.OUTBOUND:
        return {**base, "title": "출고 내역서", "headers": ["출고일자", "거래처", "품목", "수량", "단가", "금액"], "items": [
            {"d": "2026-01-15", "v": "부산지점", "i": "노트북", "q": 2, "p": 1200000, "a": 2400000}
        ]}

    elif intent.document_type in [DocumentType.PURCHASE_ORDER, DocumentType.ORDER_SHEET]:
        is_order = intent.document_type == DocumentType.ORDER_SHEET
        return {
            **base,
            "doc_title": "주 문 서" if is_order else "발 주 서",
            "doc_no": "ORD-2026-001",
            "doc_date": "2026-01-21",
            "due_date": "2026-01-25",
            "buyer": {"label": "주문자" if is_order else "발주처", "name": "그린컴퍼니", "contact": "홍길동", "tel": "010-1111-2222"},
            "supplier": {"label": "판매자" if is_order else "공급처", "name": "프레시마켓", "contact": "김철수",
                         "tel": "010-3333-4444"},
            "table_items": [["사과", "경북", "특", "10kg", 5, 150000], ["배", "나주", "상", "15kg", 3, 180000]],
            "total_amount": 330000
        }
    return {}