OUTBOUND_COLUMNS = [
    "출고일자",
    "LOT번호",
    "SKU번호",
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
            "qty": "-",
            "price": "-",
            "amount": "-"
        }]
    }
