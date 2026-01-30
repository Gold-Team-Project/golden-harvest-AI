import urllib.parse
from fastapi import FastAPI, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 에이전트 및 스키마
from app.agents.intent_agent import parse_intent
from app.agents.wording_agent import generate_description, generate_rag_chat
from app.document.schemas.documents import ForecastIntent, DocumentIntent

# 서비스 (문서, 예측, RAG)
from app.document.services.document_service import create_document
from app.forecast.services.demand_forecast_service import run_demand_forecast
from app.forecast.routers.forecast_router import router as forecast_router
from app.rag.service import get_expert_insight, search_general_reports
from app.config import llm

app = FastAPI()
app.include_router(forecast_router)

# 메모리 저장소 (간이용)
DOCUMENT_STORE = {}
LAST_FORECAST = {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str


def get_search_keyword(sku_no: str) -> str:
    """
    SKU 번호를 입력받아, PDF 검색에 유리한 '한글 상품명'을 반환합니다.
    (PDF에는 SKU 코드가 없고 '사과', '배' 같은 단어만 있기 때문입니다.)
    """
    sku_map = {
        # PDF 파일 내용과 잘 매칭되도록 키워드를 풍부하게 설정
        "SKU-05-04": "사과 후지 과일 전망",
        "SKU-01-01": "배 신고 생산량",
        "SKU-02-02": "샤인머스캣 포도 전망",
        "SKU-03-03": "감귤 노지 관측"
    }
    # 매핑된 게 없으면 기본적으로 SKU 번호나 '농산물' 키워드 반환
    return sku_map.get(sku_no, sku_no)


@app.post("/chat")
def chat_endpoint(request: ChatRequest):
    # 1. 의도 파악 (Forecast vs Document vs Chat)
    intent = parse_intent(request.message)

    # ====================================================
    # CASE 1: 수요 예측 (Forecast + Prophet + RAG)
    # ====================================================
    if isinstance(intent, ForecastIntent):
        print(f"🔮 [Step 1] Prophet 예측 실행: {intent.skuNo}")

        # 1. Prophet 예측 (수학적 통계 계산)
        forecast_result = run_demand_forecast(
            sku_no=intent.skuNo,
            start_date=intent.start_date,
            end_date=intent.end_date,
            horizon_months=intent.horizon_months
        )
        LAST_FORECAST[intent.skuNo] = forecast_result

        # 2. 데이터 요약 (월별 합계만 추려서 LLM에게 전달할 준비)
        monthly = [
            {"month": row["ds"].month, "quantity": int(round(row["yhat"]))}
            for row in forecast_result.get("forecast", [])
        ]

        # 3. RAG 검색 (시장 상황 리포트 검색) ⭐️ 핵심 수정 부분 ⭐️
        # SKU 코드(SKU-05-04) 대신 '사과 후지...'로 검색어 변경
        search_keyword = get_search_keyword(intent.skuNo)
        print(f"🔎 [Step 2] RAG 검색어 변경: {intent.skuNo} -> '{search_keyword}'")

        # 검색 실행 (관련된 문서를 벡터 DB에서 찾아옴)
        rag_context = search_general_reports(search_keyword)

        if not rag_context:
            print(f"⚠️ 경고: '{search_keyword}'에 대한 검색 결과가 없습니다.")
            rag_context = "관련된 시장 리포트가 발견되지 않았습니다. (통계 데이터만 참고하세요)"
        else:
            print(f"📝 문서 발견됨! (길이: {len(rag_context)})")

        # 4. LLM 말 만들기 (Prophet 데이터 + RAG 정보로 보정된 답변 생성)
        # 이제 Wording Agent가 '사과 생산량 감소' 정보를 읽고 예측값을 보정합니다.
        message = generate_description(
            intent=intent,
            forecast_data={
                "sku": intent.skuNo,
                "monthly_forecast_summary": monthly
            },
            market_context=rag_context
        )

        return {
            "type": "FORECAST",
            "message": message,
            "data": forecast_result,
            "risk_analysis": rag_context
        }

    # ====================================================
    # CASE 2: 문서 생성 (입고/출고 내역서)
    # ====================================================
    if isinstance(intent, DocumentIntent):
        doc = create_document(intent)
        DOCUMENT_STORE[doc["document_id"]] = doc

        return {
            "type": "DOCUMENT",
            "message": generate_description(intent),
            "document_id": doc["document_id"],
            "download_url": doc["download_url"],
            "mime_type": doc["mime_type"]
        }

    # ====================================================
    # CASE 3: 일반 대화 (Chat + Optional RAG)
    # ====================================================
    msg = request.message

    # RAG 검색 시도 (일반 대화에서도 문서를 참고하도록)
    rag_context = search_general_reports(msg)

    # 검색된 문서가 있으면 RAG 챗 모드
    if rag_context:
        print(f"📝 RAG 문서 발견 (길이: {len(rag_context)}) -> RAG 챗 모드")
        response_text = generate_rag_chat(msg, rag_context)

    # 검색된 문서가 없으면 일반 챗 모드
    else:
        print("💬 관련 문서 없음 -> 일반 LLM 챗 모드")

        # 만약 이전 예측 결과에 대해 꼬리 질문을 한 경우 ("왜 그렇게 나왔어?")
        if any(k in msg for k in ["왜", "이유", "근거", "설명"]) and LAST_FORECAST:
            last_key = list(LAST_FORECAST.keys())[-1]
            last_data = LAST_FORECAST[last_key]
            explanation = llm.invoke(
                f"사용자가 방금 예측 결과({last_key})에 대해 '{msg}'라고 물었어. "
                f"예측 데이터({last_data})를 보고 이유를 친절하게 설명해줘."
            ).content
            response_text = explanation
        else:
            # 완전 일반 대화
            response_text = llm.invoke(msg).content

    return {
        "type": "CHAT",
        "message": response_text
    }


@app.get("/documents/{doc_id}/download")
def download_document(doc_id: str):
    file_data = DOCUMENT_STORE.get(doc_id)
    if not file_data:
        raise HTTPException(status_code=404)

    return Response(
        content=file_data["content"],
        media_type=file_data["mime_type"],
        headers={
            "Content-Disposition":
                f"attachment; filename*=UTF-8''{urllib.parse.quote(file_data['filename'])}"
        }
    )