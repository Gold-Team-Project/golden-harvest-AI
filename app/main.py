import urllib.parse
import json
import redis
from typing import List, Optional

from fastapi import FastAPI, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# LangChain 메시지 객체
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# 에이전트 및 스키마
from app.agents.intent_agent import parse_intent
from app.agents.wording_agent import generate_description, generate_rag_chat
from app.document.schemas.documents import ForecastIntent, DocumentIntent

# 서비스
from app.document.services.document_service import create_document
from app.forecast.services.demand_forecast_service import run_demand_forecast
from app.forecast.routers.forecast_router import router as forecast_router
from app.rag.service import get_expert_insight, search_general_reports
from app.config import llm

app = FastAPI()
app.include_router(forecast_router)

# Redis 클라이언트 설정
redis_client = redis.Redis(
    host= 'localhost',
    port=6379,
    db=0,
    decode_responses=True)

DOCUMENT_STORE = {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    session_id: str
    message: str


# Redis Helper 함수들 (대화 내역 + 예측 데이터)

# 1. 대화 내역 관리
def get_chat_history(session_id: str, limit: int = 10) -> List:
    key = f"chat_history:{session_id}"
    items = redis_client.lrange(key, -limit, -1)

    messages = []
    for item in items:
        data = json.loads(item)
        if data["role"] == "user":
            messages.append(HumanMessage(content=data["content"]))
        elif data["role"] == "assistant":
            messages.append(AIMessage(content=data["content"]))
    return messages


def save_chat_to_redis(session_id: str, user_msg: str, ai_msg: str):
    key = f"chat_history:{session_id}"
    redis_client.rpush(key, json.dumps({"role": "user", "content": user_msg}))
    redis_client.rpush(key, json.dumps({"role": "assistant", "content": ai_msg}))
    redis_client.expire(key, 3600 * 24)  # 24시간 보관


def save_last_forecast(session_id: str, sku: str, data: dict):
    """최근 수행한 예측 데이터를 사용자 세션별로 저장"""
    key = f"last_forecast:{session_id}"
    payload = {
        "sku": sku,
        "data": data
    }
    redis_client.set(key, json.dumps(payload, default=str))
    redis_client.expire(key, 3600 * 24)


def get_last_forecast(session_id: str) -> Optional[dict]:
    """저장된 최근 예측 데이터 불러오기"""
    key = f"last_forecast:{session_id}"
    data = redis_client.get(key)
    if data:
        return json.loads(data)
    return None


def get_search_keyword(sku_no: str) -> str:
    sku_map = {
        "411-05-05": "사과 후지 과일 전망",
        "SKU-01-01": "배 신고 생산량",
        "SKU-02-02": "샤인머스캣 포도 전망",
        "SKU-03-03": "감귤 노지 관측"
    }
    return sku_map.get(sku_no, sku_no)


@app.post("/chat")
def chat_endpoint(request: ChatRequest):
    session_id = request.session_id
    user_message = request.message

    intent = parse_intent(user_message)

    ai_response_message = ""
    response_data = {}

    # 수요 예측
    if isinstance(intent, ForecastIntent):
        print(f"🔮 [Step 1] Prophet 예측 실행: {intent.skuNo}")

        forecast_result = run_demand_forecast(
            sku_no=intent.skuNo,
            start_date=intent.start_date,
            end_date=intent.end_date,
            horizon_months=intent.horizon_months
        )

        # [수정됨] 전역 변수 대신 Redis에 저장
        save_last_forecast(session_id, intent.skuNo, forecast_result)

        monthly = [
            {"month": row["ds"].month, "quantity": int(round(row["yhat"]))}
            for row in forecast_result.get("forecast", [])
        ]

        search_keyword = get_search_keyword(intent.skuNo)
        rag_context = search_general_reports(search_keyword)

        if not rag_context:
            rag_context = "관련된 시장 리포트가 발견되지 않았습니다."

        ai_response_message = generate_description(
            intent=intent,
            forecast_data={
                "sku": intent.skuNo,
                "monthly_forecast_summary": monthly
            },
            market_context=rag_context
        )

        response_data = {
            "type": "FORECAST",
            "message": ai_response_message,
            "data": forecast_result,
            "risk_analysis": rag_context
        }

    # CASE 2: 문서 생성
    elif isinstance(intent, DocumentIntent):
        doc = create_document(intent)
        DOCUMENT_STORE[doc["document_id"]] = doc

        ai_response_message = generate_description(intent)

        response_data = {
            "type": "DOCUMENT",
            "message": ai_response_message,
            "document_id": doc["document_id"],
            "download_url": doc["download_url"],
            "mime_type": doc["mime_type"]
        }

    # CASE 3: 일반 대화 (Context + Last Forecast)
    else:
        rag_context = search_general_reports(user_message)
        history_messages = get_chat_history(session_id)
        current_msg_obj = HumanMessage(content=user_message)

        if rag_context:
            # RAG 모드
            system_prompt = f"다음 문서를 바탕으로 답변하세요:\n{rag_context}"
            messages_to_send = [SystemMessage(content=system_prompt)] + history_messages + [current_msg_obj]
            ai_response = llm.invoke(messages_to_send)
            ai_response_message = ai_response.content
        else:
            # 일반 대화 모드

            # [수정됨] Redis에서 최근 예측 데이터 확인
            last_forecast_info = get_last_forecast(session_id)

            # 꼬리 질문 ("왜?", "이유") 이면서 + 최근 예측 데이터가 있을 때
            is_followup = any(k in user_message for k in ["왜", "이유", "근거", "설명"])

            if is_followup and last_forecast_info:
                last_sku = last_forecast_info['sku']
                last_data = last_forecast_info['data']

                print(f"💬 예측 결과({last_sku})에 대한 꼬리 질문 감지")

                # 예측 데이터를 컨텍스트로 주입
                context_msg = SystemMessage(
                    content=f"참고: 사용자는 방금 '{last_sku}' 상품의 예측 결과 데이터를 조회했습니다.\n"
                            f"데이터: {last_data}\n"
                            f"이 데이터를 기반으로 사용자의 질문에 답변하세요."
                )
                messages_to_send = history_messages + [context_msg, current_msg_obj]
            else:
                # 그 외 일반 대화
                messages_to_send = history_messages + [current_msg_obj]

            ai_response = llm.invoke(messages_to_send)
            ai_response_message = ai_response.content

        response_data = {
            "type": "CHAT",
            "message": ai_response_message
        }

    # [공통] 대화 내용 저장
    if ai_response_message:
        save_chat_to_redis(session_id, user_message, ai_response_message)

    return response_data


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