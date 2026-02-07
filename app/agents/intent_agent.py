from datetime import date, timedelta
from typing import Optional, Literal
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from pydantic import BaseModel, Field

from app.config import llm, USE_LLM
from app.document.schemas.documents import DocumentIntent, ForecastIntent, DocumentType


# 1. 의도 파악 (Intent Parsing) 섹션

class UnifiedIntentParsing(BaseModel):
    intent_category: Literal["FORECAST", "DOCUMENT", "CHAT"]
    sku_no: Optional[str] = Field(description="제품 코드 (예: SKU-05-04). 없으면 None")
    forecast_horizon: Optional[int] = Field(description="예측 기간(개월 단위)", default=6)
    doc_type: Optional[DocumentType] = None
    doc_start: Optional[date] = None
    doc_end: Optional[date] = None


def get_fallback_intent(user_message: str):
    return {"intent_type": "CHAT", "message": user_message}


def parse_intent(user_message: str):
    if not USE_LLM:
        return get_fallback_intent(user_message)

    try:
        structured_llm = llm.with_structured_output(UnifiedIntentParsing)

        system_prompt = (
            "너는 농산물 유통 및 수요 예측 시스템의 AI 전략가다. 오늘 날짜는 {today}다.\n"
            "사용자의 요청이 '단순 수치 생성'인지, '논리적 설명 및 비판'인지 엄격히 구분하라.\n\n"

            "[분류 가이드라인]\n"
            "1. FORECAST: 2026년 전체 수요 등 '미래 수치'를 새롭게 뽑아야 할 때.\n"
            "2. CHAT: '왜 이 숫자가 나왔어?', '12월 데이터만 쓰는 거 아냐?' 등 논리적 근거를 묻거나 비판할 때.\n"
            "   - 특히 리포트의 '장기 전망(재배 면적 등)'을 확인하려는 의도는 CHAT(RAG)으로 분류하라.\n"
            "3. DOCUMENT: 과거의 입/출고 내역이나 엑셀 파일을 요청할 때.\n"
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{text}"),
        ])

        result: UnifiedIntentParsing = (prompt | structured_llm).invoke({
            "today": date.today(),
            "text": user_message
        })

        today = date.today()

        if result.intent_category == "FORECAST":
            horizon = result.forecast_horizon or 6
            if "2026" in user_message: horizon = 12
            return ForecastIntent(
                intent_type="FORECAST", skuNo=result.sku_no or "ALL",
                start_date=today, end_date=today + timedelta(days=30 * horizon),
                horizon_months=horizon
            )

        if result.intent_category == "DOCUMENT":
            return DocumentIntent(
                intent_type="DOCUMENT", document_type=result.doc_type or DocumentType.INBOUND,
                start_date=result.doc_start or (today - timedelta(days=30)),
                end_date=result.doc_end or today, format="excel",
                sku_no=result.sku_no
            )

        return {"intent_type": "CHAT", "message": user_message, "sku_no": result.sku_no}

    except Exception as e:
        print(f"Intent Parsing Error: {e}")
        return get_fallback_intent(user_message)


# 2. 결과 생성 및 보정 (Generation & Calibration) 섹션
def generate_description(intent, forecast_data: dict | None = None, market_context: str = "") -> str:
    if not USE_LLM:
        return "요청하신 작업을 완료했습니다."

    try:
        if isinstance(intent, DocumentIntent):
            target = f"(SKU: {intent.sku_no})" if intent.sku_no else "(전체 품목)"
            return f"""
✅ **문서 생성 완료**
- 기간: {intent.start_date} ~ {intent.end_date}
- 대상: {target}
- 유형: {intent.document_type.name}

요청하신 문서를 생성했습니다. 아래 버튼을 클릭하여 다운로드하세요.
"""

        if isinstance(intent, ForecastIntent):
            # [단기 편향 제거 프롬프트 핵심 보강]
            prompt = ChatPromptTemplate.from_template(
                """
너는 **수석 수요 예측 분석가(Senior Demand Planner)**다. 
2026년 연간 예측을 수행함에 있어, 리포트에 포함된 '일시적 현상'과 '구조적 변화'를 엄격히 분리하여 보정하라.

### 1. 단기 편향(Recency Bias) 방지 지침
- **현상 파악**: 시장 정보({market_context})에서 '현재 달(예: 12월)'에 대한 언급은 해당 월 및 직후 월(익월)에만 제한적으로 반영하라.
- **거시 지표 우선**: 2026년 전체를 관통하는 보정 근거는 리포트의 **'재배 의향 면적'**, **'연간 생산 전망'**, **'평년 가격 추이'** 데이터를 최우선순위로 둔다.
- **Prophet 계절성 존중**: 리포트에 내년 전체에 대한 명확한 반대 근거가 없다면, Prophet의 계절성 패턴(통계치)을 훼손하지 마라. 특정 달의 이슈를 12개월 전체에 복사/붙여넣기 하는 것은 중대한 분석 오류다.

### 2. 입력 데이터
- (A) Prophet 예측치: {forecast}
- (B) 시장 정보(RAG): {market_context}

### 3. 답변 양식

**📊 수요 예측 보고서**

**[1) 요약]**
- 핵심 트렌드와 총 예측량을 요약.

**[2) 월별 상세 예측 데이터]**
- **필수**: 예측된 모든 달(1월~6월 등)의 수치를 아래 형식으로 빠짐없이 나열하세요.
  - YYYY-MM: 000개
  (예: 2026-01: 290개, 2026-02: 310개 ...)
- 합계, 평균, 최소/최대값 요약.

**[3) 리포트/시장 근거 기반 해석]**
- 시장 리포트 내용이 있다면 구체적으로 인용하여 예측의 타당성을 뒷받침하세요. 
- (문서 내용이 없으면 솔직히 없다고 명시하되, 일반적인 계절성이나 추세를 설명)

**[4) 리스크 & 제언]**
- 데이터 불확실성이나 시장 변수에 따른 리스크와 대응 방안.
"""
            )
            return (prompt | llm | StrOutputParser()).invoke({
                "forecast": str(forecast_data),
                "market_context": market_context if market_context else "2026년 장기 전망 데이터 위주 참고 요망"
            })

        # CHAT 모드 (질문 및 비판 대응)
        if isinstance(intent, dict) and intent.get("intent_type") == "CHAT":
            prompt = ChatPromptTemplate.from_template(
                """
너는 농산물 데이터 전문가다. 사용자의 비판이나 질문에 대해 리포트의 '장기적 사실'을 근거로 답변하라.
사용자 질문: {question}
참고 내용: {context}

답변 규칙:
1. 사용자가 '왜 12월 데이터만 쓰냐'고 지적하면, 리포트에서 2026년 전체 재배 면적이나 연간 전망 부분을 찾아 그 차이점을 설명하라.
2. 단기적 가격 변동과 장기적 수급 전망을 구분하여 논리적으로 설명하라.
"""
            )
            return (prompt | llm | StrOutputParser()).invoke({
                "question": intent["message"], "context": market_context
            })

    except Exception as e:
        print(f"Error: {e}");
        return "분석 중 오류가 발생했습니다."