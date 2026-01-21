# app/services/data_service.py
def get_inbound_data(start_date, end_date):
    return [
        {
            "입고일자": str(start_date),
            "거래처" : "골든",
            "품목명": "사과",
            "수량": 100,
            "단가": 3000,
            "합계금액": 300000
        },
        {
            "입고일자": str(end_date),
            "거래처": "골든",
            "품목명": "배",
            "수량": 50,
            "단가": 4000,
            "합계금액": 200000
        }
    ]
