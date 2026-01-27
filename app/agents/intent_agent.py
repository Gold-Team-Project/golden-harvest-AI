from datetime import date, timedelta
from typing import Optional, Literal
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.config import llm, USE_LLM
from app.document.schemas.documents import DocumentIntent, ForecastIntent, DocumentType


class UnifiedIntentParsing(BaseModel):
    intent_category: Literal["FORECAST", "DOCUMENT", "CHAT"]

    sku_no: Optional[str] = None
    forecast_start: Optional[date] = None
    forecast_end: Optional[date] = None
    horizon: Optional[int] = 6

    doc_type: Optional[DocumentType] = None
    doc_start: Optional[date] = None
    doc_end: Optional[date] = None


def get_fallback_intent(user_message: str):
    return {
        "intent_type": "CHAT",
        "message": user_message
    }


def parse_intent(user_message: str):
    if not USE_LLM:
        return get_fallback_intent(user_message)

    try:
        structured_llm = llm.with_structured_output(UnifiedIntentParsing)

        system_prompt = (
            "너는 ERP 시스템 AI 비서다. 오늘 날짜는 {today}다.\n"
            "사용자 요청을 분석하여 의도를 하나로 분류해라.\n\n"

            "[FORECAST]\n"
            "- 수요, 예측, 향후, 미래, 몇 개월 등의 키워드가 명확할 때\n"
            "- SKU가 존재해야 함\n\n"

            "[DOCUMENT]\n"
            "- 입고, 출고, 내역, 엑셀, 파일, 다운로드\n"
            "- 기간이 명확하거나 암시됨\n\n"

            "[CHAT]\n"
            "- 이유 질문, 설명 요청, 의견, 잡담, 인사\n"
            "- 위 두 조건에 해당하지 않으면 무조건 CHAT\n"
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{text}"),
        ])

        chain = prompt | structured_llm
        result: UnifiedIntentParsing = chain.invoke({
            "today": date.today(),
            "text": user_message
        })

        today = date.today()

        if result.intent_category == "FORECAST":
            f_start = result.forecast_start or (today - timedelta(days=365))
            f_end = result.forecast_end or (today - timedelta(days=1))

            return ForecastIntent(
                intent_type="FORECAST",
                skuNo=result.sku_no or "UNKNOWN",
                start_date=f_start,
                end_date=f_end,
                horizon_months=result.horizon or 6
            )

        if result.intent_category == "DOCUMENT":
            return DocumentIntent(
                intent_type="DOCUMENT",
                document_type=result.doc_type or DocumentType.INBOUND,
                start_date=result.doc_start or today,
                end_date=result.doc_end or today,
                format="excel"
            )

        return {
            "intent_type": "CHAT",
            "message": user_message
        }

    except Exception:
        return get_fallback_intent(user_message)
