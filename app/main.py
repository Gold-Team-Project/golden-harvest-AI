# main.py
import os
import urllib.parse
import json
import redis
import tempfile
import glob
import logging
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel

# LangChain 메시지 객체
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# 에이전트 및 스키마
from app.agents.intent_agent import parse_intent
from app.agents.wording_agent import generate_description
from app.document.schemas.documents import ForecastIntent, DocumentIntent

# 서비스
from app.document.services.document_service import create_document
from app.forecast.services.demand_forecast_service import run_demand_forecast
from app.forecast.routers.forecast_router import router as forecast_router
from app.rag.service import get_expert_insight, search_general_reports
from app.rag.ingest import ingest_pdf_report
from app.config import llm

# -----------------------------
# 로깅 설정 (초기 데이터 적재 과정 확인용)
# -----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------
# Redis 클라이언트 설정
# -----------------------------
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    decode_responses=True
)

DOCUMENT_STORE = {}


# -----------------------------
# Lifespan (수명 주기) 설정: Method B - 초기 데이터 자동 적재
# -----------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # [시작 시 실행] seeds 폴더 확인 및 학습
    seed_dir = "./seeds"  # Docker 내부 경로 기준 (/app/seeds)

    if os.path.exists(seed_dir):
        pdf_files = glob.glob(os.path.join(seed_dir, "*.pdf"))

        if pdf_files:
            logger.info(f"🌱 [초기 데이터] {len(pdf_files)}개의 시드 파일을 발견했습니다. 학습을 시작합니다...")

            for pdf_path in pdf_files:
                filename = os.path.basename(pdf_path)
                try:
                    logger.info(f"   Targeting: {filename}")

                    # 동기 함수인 경우 직접 호출 (비동기라면 await 필요)
                    ingest_pdf_report(
                        file_path=pdf_path,
                        category="기본자료",  # 필요에 따라 카테고리 지정
                        report_date=None,
                        source="System_Seed",  # 출처를 시스템 시드로 명시
                        force=True  # 강제로 덮어쓰기/갱신
                    )
                    logger.info(f"   ✅ 완료: {filename}")
                except Exception as e:
                    logger.error(f"   ❌ 실패: {filename} - {str(e)}")

            logger.info("✨ [초기 데이터] 모든 시드 데이터 학습 완료!")
        else:
            logger.info("ℹ️ seeds 폴더가 비어있습니다. 초기 학습을 건너뜁니다.")
    else:
        logger.warning(f"⚠️ {seed_dir} 폴더를 찾을 수 없습니다. (apps/ai/seeds 폴더를 만들어주세요)")

    yield  # 애플리케이션 실행

    # [종료 시 실행]
    pass


# -----------------------------
# FastAPI 앱 초기화
# -----------------------------
app = FastAPI(lifespan=lifespan)
app.include_router(forecast_router)


# CORS Middleware는 게이트웨이가 앞단에 있으므로 제거됨


class ChatRequest(BaseModel):
    session_id: str
    message: str


# -----------------------------
# Redis Helper 함수들
# -----------------------------
def get_chat_history(session_id: str, limit: int = 10) -> List:
    key = f"chat_history:{session_id}"
    items = redis_client.lrange(key, -limit, -1)

    messages = []
    for item in items:
        try:
            data = json.loads(item)
            if data.get("role") == "user":
                messages.append(HumanMessage(content=data.get("content", "")))
            elif data.get("role") == "assistant":
                messages.append(AIMessage(content=data.get("content", "")))
        except Exception:
            continue
    return messages


def save_chat_to_redis(session_id: str, user_msg: str, ai_msg: str):
    key = f"chat_history:{session_id}"
    redis_client.rpush(key, json.dumps({"role": "user", "content": user_msg}, ensure_ascii=False))
    redis_client.rpush(key, json.dumps({"role": "assistant", "content": ai_msg}, ensure_ascii=False))
    redis_client.expire(key, 3600 * 24)


def save_last_forecast(session_id: str, sku: str, data: dict):
    key = f"last_forecast:{session_id}"
    payload = {"sku": sku, "data": data}
    redis_client.set(key, json.dumps(payload, default=str, ensure_ascii=False))
    redis_client.expire(key, 3600 * 24)


def get_last_forecast(session_id: str) -> Optional[dict]:
    key = f"last_forecast:{session_id}"
    data = redis_client.get(key)
    if data:
        try:
            return json.loads(data)
        except Exception:
            return None
    return None


# -----------------------------
# API Endpoints
# -----------------------------

# RAG 적재 API
@app.post("/rag/ingest/pdf")
async def rag_ingest_pdf(
        file: UploadFile = File(...),
        category: Optional[str] = Form(None),
        report_date: Optional[str] = Form(None),
        source: str = Form("KREI_관측월보"),
        force: bool = Query(False),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드 가능합니다.")

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 저장 실패: {str(e)}")

    try:
        result = ingest_pdf_report(
            file_path=tmp_path,
            category=category,
            report_date=report_date,
            source=source,
            force=force,
        )
        return result
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


# 채팅 API
@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    session_id = request.session_id
    user_message = request.message

    intent = parse_intent(user_message)

    if isinstance(intent, ForecastIntent):
        forecast_result = run_demand_forecast(
            sku_no=intent.skuNo,
            start_date=intent.start_date,
            end_date=intent.end_date,
            horizon_months=intent.horizon_months
        )

        save_last_forecast(session_id, intent.skuNo, forecast_result)

        monthly = [
            {"month": row["ds"].month, "quantity": int(round(row["yhat"]))}
            for row in forecast_result.get("forecast", [])
        ]

        query_month = None
        try:
            if intent.start_date:
                query_month = int(str(intent.start_date)[5:7])
        except Exception:
            query_month = None

        rag_context = await get_expert_insight(
            sku_no=intent.skuNo,
            query_month=query_month,
            query_period=None
        )

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

    else:
        rag_context = search_general_reports(user_message, k=3)

        history_messages = get_chat_history(session_id)
        current_msg_obj = HumanMessage(content=user_message)

        if rag_context:
            system_prompt = f"다음 문서를 바탕으로 답변하세요:\n{rag_context}"
            messages_to_send = [SystemMessage(content=system_prompt)] + history_messages + [current_msg_obj]
            ai_response = llm.invoke(messages_to_send)
            ai_response_message = ai_response.content
        else:
            last_forecast_info = get_last_forecast(session_id)
            is_followup = any(k in user_message for k in ["왜", "이유", "근거", "설명"])

            if is_followup and last_forecast_info:
                last_sku = last_forecast_info.get("sku")
                last_data = last_forecast_info.get("data")

                context_msg = SystemMessage(
                    content=(
                        f"참고: 사용자는 방금 '{last_sku}' 상품의 예측 결과 데이터를 조회했습니다.\n"
                        f"데이터: {last_data}\n"
                        f"이 데이터를 기반으로 사용자의 질문에 답변하세요."
                    )
                )
                messages_to_send = history_messages + [context_msg, current_msg_obj]
            else:
                messages_to_send = history_messages + [current_msg_obj]

            ai_response = llm.invoke(messages_to_send)
            ai_response_message = ai_response.content

        response_data = {
            "type": "CHAT",
            "message": ai_response_message
        }

    if ai_response_message:
        save_chat_to_redis(session_id, user_message, ai_response_message)

    return response_data


@app.get("/documents/{doc_id}/download")
def download_document(doc_id: str):
    file_data = DOCUMENT_STORE.get(doc_id)
    if not file_data:
        raise HTTPException(status_code=404, detail="document not found")

    return Response(
        content=file_data["content"],
        media_type=file_data["mime_type"],
        headers={
            "Content-Disposition":
                f"attachment; filename*=UTF-8''{urllib.parse.quote(file_data['filename'])}"
        }
    )