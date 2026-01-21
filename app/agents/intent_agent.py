from datetime import date
from langchain_core.prompts import ChatPromptTemplate
from app.config import llm, USE_LLM
from app.schemas.documents import DocumentType, DocumentIntent


def get_fallback_intent(user_message: str) -> DocumentIntent:
    today = date.today()
    dtype = DocumentType.INBOUND

    if "출고" in user_message:
        dtype = DocumentType.OUTBOUND
    elif "발주" in user_message:
        dtype = DocumentType.PURCHASE_ORDER
    elif "주문" in user_message:
        dtype = DocumentType.ORDER_SHEET

    fmt = "pdf" if dtype in [DocumentType.PURCHASE_ORDER, DocumentType.ORDER_SHEET] else "excel"

    return DocumentIntent(document_type=dtype, start_date=today, end_date=today, format=fmt)


def parse_intent(user_message: str) -> DocumentIntent:
    if not USE_LLM:
        return get_fallback_intent(user_message)

    try:
        # Pydantic 객체로 바로 구조화된 출력 요청
        structured_llm = llm.with_structured_output(DocumentIntent)

        prompt = ChatPromptTemplate.from_messages([
            ("system", "너는 ERP 문서 요청 분석가다. 오늘 날짜는 {today}다. 사용자의 요청을 분석하여 정확한 데이터를 추출해라."),
            ("human", "{text}"),
        ])

        chain = prompt | structured_llm
        return chain.invoke({"today": date.today(), "text": user_message})

    except Exception as e:
        print(f"⚠️ Intent Error: {e}")
        return get_fallback_intent(user_message)