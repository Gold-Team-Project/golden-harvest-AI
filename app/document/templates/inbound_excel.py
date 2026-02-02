INBOUND_COLUMNS = [
    "입고일자",
    "SKU번호",
    "수량"
]

def build_inbound_excel(base_data, items):
    return {
        **base_data,
        "title": "입고 내역서",
        "headers": INBOUND_COLUMNS,
        "items": items or [
            {"date": "조회 결과 없음", "sku": "-", "qty": "-"}
        ]
    }
