from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.config import llm, USE_LLM
from app.document.schemas.documents import DocumentIntent, ForecastIntent


# -----------------------------
# RAG Chat
# -----------------------------
def generate_rag_chat(user_message: str, context: str) -> str:
    """
    RAG 검색 결과가 있을 때 사용하는 채팅 프롬프트.
    - context가 없으면 일반 LLM 응답.
    - context가 있으면, 관련 질문일 때만 근거로 사용.
    """
    if not USE_LLM:
        return "요청하신 내용을 처리했습니다."

    # context 없으면 일반 대화
    if not context or not context.strip():
        # llm.invoke는 문자열을 받을 수도 있지만, 체인 일관성을 위해 prompt 기반으로 처리
        prompt = ChatPromptTemplate.from_template(
            """
너는 농산물 데이터 및 ERP 전문가 AI다.
사용자 질문에 자연스럽게 답하라.

[사용자 질문]
{question}
"""
        )
        chain = prompt | llm | StrOutputParser()
        return chain.invoke({"question": user_message})

    # context 있으면 RAG 프롬프트
    prompt = ChatPromptTemplate.from_template(
        """
너는 농산물 데이터 및 ERP 전문가 AI다.
사용자의 질문에 대해 아래 [검색된 문서 내용]을 참고해 답변하라.

[검색된 문서 내용]
{context}

[사용자 질문]
{question}

[답변 규칙]
1) 질문이 문서 내용과 관련 있으면, 문서에서 근거(기간/품목/출처/핵심 문장)를 짧게 요약하며 답변하라.
2) 질문이 문서와 무관(인사/농담/일상)하면 문서를 무시하고 자연스럽게 대화하라.
3) 문서 근거가 부족하면 "문서에 근거가 부족합니다"를 명확히 말한 뒤, 일반적인 관점에서만 답하라.
4) 문서에 [기간|품목|출처]가 표시되어 있으면 답변에 포함하라.
5) 사실을 단정할 때는 반드시 문서 근거가 있어야 한다. 근거 없으면 가능성/일반론으로 표현한다.
"""
    )
    chain = prompt | llm | StrOutputParser()
    return chain.invoke({"context": context, "question": user_message})


# -----------------------------
# Forecast / Document Description
# -----------------------------
def _has_valid_monthly_forecast(forecast_data: Optional[dict]) -> bool:
    """
    forecast_data가 월별 예측 리스트를 포함하는지 검증.
    기대 형태(예):
    {
      "sku": "...",
      "monthly_forecast_summary": [{"month": 1, "quantity": 120}, ...]
    }
    """
    if not forecast_data or not isinstance(forecast_data, dict):
        return False

    rows = forecast_data.get("monthly_forecast_summary")
    if not rows or not isinstance(rows, list):
        return False

    for r in rows:
        if not isinstance(r, dict):
            return False
        if "month" not in r or "quantity" not in r:
            return False
        try:
            int(r["month"])
            int(r["quantity"])
        except Exception:
            return False

    return True


def _calc_forecast_stats(forecast_data: Dict[str, Any]) -> Dict[str, Any]:
    rows = forecast_data["monthly_forecast_summary"]
    quantities = [int(r["quantity"]) for r in rows]
    total = sum(quantities)
    avg = round(total / len(quantities), 2) if quantities else 0
    q_min = min(quantities) if quantities else 0
    q_max = max(quantities) if quantities else 0

    # 상/하반기 단순 요약도 시스템 계산으로 제공(LLM이 임의 숫자 생성 못 하게)
    first_half = quantities[:6] if len(quantities) >= 6 else quantities
    second_half = quantities[6:] if len(quantities) >= 12 else quantities[6:]
    fh_avg = round(sum(first_half) / len(first_half), 2) if first_half else None
    sh_avg = round(sum(second_half) / len(second_half), 2) if second_half else None

    return {
        "rows": rows,
        "total": total,
        "avg": avg,
        "min": q_min,
        "max": q_max,
        "first_half_avg": fh_avg,
        "second_half_avg": sh_avg,
    }


def generate_description(intent, forecast_data: dict | None = None, market_context: str = "") -> str:
    """
    - ForecastIntent: 숫자는 파이썬에서 계산해 주입하고, LLM은 설명/근거 정리만 수행.
    - DocumentIntent: 문서 생성 안내 메시지 생성.
    """
    if not USE_LLM:
        return _fallback_message(intent, forecast_data)

    try:
        # -------------------------
        # FORECAST
        # -------------------------
        if isinstance(intent, ForecastIntent):
            # ✅ 데이터 없으면 숫자 생성 못하게 즉시 차단
            if not _has_valid_monthly_forecast(forecast_data):
                return (
                    "예측 결과 데이터가 비어 있어 보고서를 생성할 수 없습니다.\n"
                    "- monthly_forecast_summary가 없거나 비어 있습니다.\n"
                    "- run_demand_forecast 결과를 확인하고 월별 예측 리스트를 생성해 다시 요청해주세요."
                )

            stats = _calc_forecast_stats(forecast_data)
            sku = forecast_data.get("sku") or getattr(intent, "skuNo", None) or "미지정"

            # ✅ 프롬프트에서 '보정 수치/변동 범위' 같은 임의 숫자 요구를 제거
            # ✅ 절대 규칙으로 '입력 숫자 외 새로운 숫자 생성 금지' 고정
            prompt = ChatPromptTemplate.from_template(
                """
너는 **수석 수요 예측 분석가(Senior Demand Planner)**다.
목표: 시스템이 제공한 예측 수치(Prophet 결과 요약)를 바탕으로, 리포트 근거(RAG)가 있으면 검증/해석하고 없으면 한계를 명확히 말한다.

[절대 규칙]
- 아래에 제공된 숫자 외에 새로운 수치(예: 임의의 보정값, 임의의 ±범위)를 만들어내지 마라.
- "보정"은 수치 변경이 아니라, 해석/검증/주의사항 정리로 수행한다.
- 리포트 근거가 없으면 "근거 부족"을 명확히 표기하라.

[시스템 제공 입력(수정 금지)]
- SKU: {sku}
- 월별 예측치: {monthly_rows}
- 합계: {total}
- 평균: {avg}
- 최소/최대: {min_val} / {max_val}
- 상반기 평균(가능 시): {first_half_avg}
- 하반기 평균(가능 시): {second_half_avg}

[리포트 발췌(RAG)]
{market_context}

[출력 형식]
## 📊 예측 해석 보고서

**[1) 요약]**
- SKU: {sku}
- 핵심 결론: 2~3문장 (리포트 근거 있으면 반영, 없으면 한계 명시)

**[2) 수치 요약(시스템 숫자 기반)]**
- 합계: {total}
- 평균: {avg}
- 최소/최대: {min_val} ~ {max_val}
- 패턴 코멘트: (예: 성수기/비수기, 변곡 구간을 '월별 예측치'를 보고 서술)

**[3) 리포트 근거로 검증/해석]**
- 리포트에서 구조적 변화(재배면적/생산량/수급기조/평년 가격 패턴)가 있으면 우선적으로 요약
- 단기 이슈는 해당 월/익월 범위로만 제한
- 리포트 근거가 부족하면 "근거 부족"을 먼저 말하고, 일반론으로만 설명

**[4) 리스크 & 실행 제안 3가지]**
- 리스크 2개(근거 기반)
- 실행 제안 1개(재고/발주/프로모션 중 택1)
"""
            )

            chain = prompt | llm | StrOutputParser()
            return chain.invoke({
                "sku": sku,
                "monthly_rows": stats["rows"],
                "total": stats["total"],
                "avg": stats["avg"],
                "min_val": stats["min"],
                "max_val": stats["max"],
                "first_half_avg": stats["first_half_avg"] if stats["first_half_avg"] is not None else "N/A",
                "second_half_avg": stats["second_half_avg"] if stats["second_half_avg"] is not None else "N/A",
                "market_context": market_context.strip() if market_context and market_context.strip() else "문서 근거가 부족합니다.",
            })

        # -------------------------
        # DOCUMENT / others
        # -------------------------
        prompt = ChatPromptTemplate.from_template(
            """
너는 ERP 시스템의 업무 보조 AI다.
사용자가 요청한 문서({intent})가 생성되었음을 알리는 정중한 메시지를 1문장으로 작성해라.
"""
        )
        chain = prompt | llm | StrOutputParser()
        return chain.invoke({"intent": str(intent)})

    except Exception as e:
        print(f"Wording Error: {e}")
        return _fallback_message(intent, forecast_data)


def _fallback_message(intent, forecast_data: dict | None = None) -> str:
    if isinstance(intent, ForecastIntent) and forecast_data:
        sku = forecast_data.get("sku") if isinstance(forecast_data, dict) else None
        sku = sku or getattr(intent, "skuNo", None) or "해당 SKU"
        return f"예측 완료. {sku} 결과 데이터를 확인하세요."
    return "요청하신 작업을 완료했습니다."
