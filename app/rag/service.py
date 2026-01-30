# app/rag/service.py
from app.rag.store import get_vector_store

# SKU 매핑 테이블 (실제로는 DB에서 관리 권장)
SKU_MAPPER = {
    "411": "사과",
    "412": "배",
    "413": "배추",
    # 테스트용 SKU가 있다면 여기에 추가하세요
}


def search_general_reports(query: str, k: int = 3) -> str:
    """
    일반 질문(Chat)에 대해 관련 문서를 검색합니다.
    """
    vector_store = get_vector_store()

    # 질문과 유사한 문서 검색
    docs = vector_store.similarity_search(query, k=k)

    if not docs:
        return ""

    # 검색된 내용 포맷팅
    context_list = []
    for doc in docs:
        period = doc.metadata.get("period", "날짜미상")
        category = doc.metadata.get("category", "일반")
        content = doc.page_content.replace("\n", " ").strip()
        context_list.append(f"- [{period} {category} 보고서] {content}")

    return "\n\n".join(context_list)


def get_expert_insight(sku_no: str, query_month: int = None) -> str:
    """
    SKU 번호를 받아서 해당 품목의 전문가 리포트를 검색합니다. (Forecast용)
    """
    sku_name = SKU_MAPPER.get(sku_no, "")

    # 매핑된 이름이 없으면 검색하지 않음
    if not sku_name:
        return ""

    # 검색 쿼리 구성 (예: "사과 작황 전망 8월")
    search_query = f"{sku_name} 수급 전망 작황 가격"
    if query_month:
        search_query += f" {query_month}월"

    return search_general_reports(search_query, k=3)