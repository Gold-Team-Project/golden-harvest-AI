# wording_agent.py
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.config import llm, USE_LLM
from app.document.schemas.documents import DocumentIntent, ForecastIntent


def generate_description(intent, forecast_data: dict | None = None) -> str:
    if not USE_LLM:
        return _fallback_message(intent, forecast_data)

    try:
        if isinstance(intent, ForecastIntent):
            prompt = ChatPromptTemplate.from_template(
                """
너는 ERP 시스템의 수요 예측 AI 비서다.

아래 수요 예측 결과를 사용자에게 설명해라.
반드시 다음 규칙을 지켜라.

[규칙]
1. 예측 대상 상품과 기간을 명확히 언급할 것
2. 월별 예측 수치는 줄 단위 리스트로 표현할 것
3. 제공된 숫자만 사용하고 임의로 변경하지 말 것
4. 문장 설명은 마지막 요약 1문장만 작성할 것
5. 2~4문장 이내로 작성할 것
6. 줄바꿈을 적극 활용하여 가독성 있게 잘 정리해서 말할 것   
7. 출력에는 *, -, • 등의 불릿 문자나 마크다운 리스트를 절대 사용하지 말 것

[수요 예측 데이터]
{forecast}
"""
            )

            chain = prompt | llm | StrOutputParser()
            return chain.invoke({"forecast": str(forecast_data)})

        prompt = ChatPromptTemplate.from_template(
            """
너는 ERP 시스템의 업무 보조 AI다.

아래 의도를 바탕으로
사용자에게 문서 생성 완료 메시지를 정중하게 작성해라.

[규칙]
1. 문서 종류와 기간을 명확히 언급할 것
2. 엑셀 또는 PDF 생성이 완료되었음을 알릴 것
3. 2문장 이내로 작성할 것

[의도]
{intent}
"""
        )

        chain = prompt | llm | StrOutputParser()
        return chain.invoke({"intent": str(intent)})

    except Exception as e:
        print(f" Wording Error: {e}")
        return _fallback_message(intent, forecast_data)


def _fallback_message(intent, forecast_data: dict | None = None) -> str:
    if isinstance(intent, ForecastIntent) and forecast_data:
        months = [
            f"{row['month']}월 {row['quantity']}개"
            for row in forecast_data.get("monthly_forecast", [])
        ]
        month_text = ", ".join(months)

        return (
            f"{intent.skuNo}의 수요 예측 결과입니다. "
            f"{month_text}로 예상됩니다."
        )

    return (
        f"{intent.start_date}~{intent.end_date} "
        f"{intent.document_type.value} 문서를 생성했습니다."
    )
def generate_forecast_message(intent, forecast_data):
    monthly = forecast_data["monthly_forecast"]

    lines = [
        f"{row['month']}월  {row['quantity']:.2f}"
        for row in monthly
    ]

    peak = max(monthly, key=lambda x: x["quantity"])

    return (
        f"📦 {intent.skuNo} · 2026년 월별 수요 예측\n\n"
        + "\n".join(lines)
        + (
            f"\n\n📈 요약\n"
            f"- 여름철 수요 집중\n"
            f"- 최고 수요: {peak['month']}월 ({peak['quantity']:.2f})"
        )
    )