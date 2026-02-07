OUTBOUND_COLUMNS = [
    "출고일자",
    "LOT번호",
    "SKU번호",
    "품목명",
    "품종명",
    "등급",
    "수량",
    "단가",
    "금액"
]

def build_outbound_excel(base_data, items):
    return {
        **base_data,
        "title": "출고 내역서",
        "headers": OUTBOUND_COLUMNS,
        "items": items or [{
            "date": "조회 결과 없음",
            "LOT": "-",
            "sku": "-",
            "item_name": "-",
            "variety_name": "-",
            "grade_name": "-",
            "qty": "-",
            "price": "-",
            "amount": "-"
        }]
    }
