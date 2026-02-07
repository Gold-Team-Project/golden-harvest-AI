INBOUND_COLUMNS = [
    "입고일자",
    "SKU번호",
    "품목명",
    "품종명",
    "등급",
    "수량"
]

def build_inbound_excel(base_data, items):
    return {
        **base_data,
        "title": "입고 내역서",
        "headers": INBOUND_COLUMNS,
        "items": items or [
            {
                "date": "조회 결과 없음",
                "sku": "-",
                "item_name": "-",
                "variety_name": "-",
                "grade_name": "-",
                "qty": "-"
            }
        ]
    }
