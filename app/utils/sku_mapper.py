def get_search_keyword(sku_no: str) -> str:
    """
    SKU 번호를 입력받아, PDF 검색에 유리한 '한글 상품명'을 반환합니다.
    실제로는 DB의 Product 테이블을 조회해야 하지만, 우선 하드코딩으로 매핑합니다.
    """
    sku_map = {
        "SKU-05-04": "사과 후지 과일 전망",  # 검색 잘 되게 키워드 조합
        "SKU-01-01": "배 신고",
        "SKU-02-02": "샤인머스캣 포도",
    }
    # 매핑 없으면 그냥 SKU 반환 (혹은 '농산물' 같은 공통 키워드)
    return sku_map.get(sku_no, sku_no)