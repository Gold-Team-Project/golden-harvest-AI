# app/main.py
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

# LangChain
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# Agent & Schema
from app.agents.intent_agent import parse_intent
from app.agents.wording_agent import generate_description
from app.document.schemas.documents import ForecastIntent, DocumentIntent

# Service
from app.document.services.document_service import create_document
from app.forecast.services.demand_forecast_service import run_demand_forecast
from app.forecast.routers.forecast_router import router as forecast_router
from app.rag.service import get_expert_insight, search_general_reports

# ✅ [추가] init_registry_table import 확인
from app.rag.ingest import ingest_pdf_report, init_registry_table
from app.config import llm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
# Lifespan
# -----------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ✅ [1단계] 서버 시작 시 테이블 자동 생성 (동기 함수지만 1회성이라 바로 호출)
    try:
        init_registry_table()
        logger.info("✅ [DB Init] RAG 레지스트리 테이블 확인/생성 완료.")
    except Exception as e:
        logger.error(f"❌ [DB Init] 테이블 생성 실패: {e}")

    # [2단계] seeds 데이터 학습
    current_dir = os.path.dirname(os.path.abspath(__file__))
    seed_dir_candidate_1 = "/app/seeds"
    seed_dir_candidate_2 = os.path.join(current_dir, "seeds")
    seed_dir = seed_dir_candidate_1 if os.path.exists(seed_dir_candidate_1) else seed_dir_candidate_2

    if os.path.exists(seed_dir):
        pdf_files = glob.glob(os.path.join(seed_dir, "*.pdf"))

        if pdf_files:
            logger.info(f"🌱 [초기 데이터] {len(pdf_files)}개의 파일을 발견했습니다. 학습을 시작합니다...")

            for pdf_path in pdf_files:
                filename = os.path.basename(pdf_path)
                try:
                    logger.info(f"   Targeting: {filename}")

                    await ingest_pdf_report(
                        file_path=pdf_path,
                        category="기본자료",
                        report_date=None,
                        source="System_Seed",
                        force=True
                    )

                    logger.info(f"   ✅ 완료: {filename}")
                except Exception as e:
                    logger.error(f"   ❌ 실패: {filename} - {str(e)}")

            logger.info("✨ [초기 데이터] 모든 시드 데이터 학습 완료!")
        else:
            logger.info(f"ℹ️ '{seed_dir}' 폴더가 비어있습니다. 초기 학습을 건너뜁니다.")
    else:
        logger.warning(f"⚠️ seeds 폴더를 찾을 수 없습니다.")

    yield
    pass


app = FastAPI(lifespan=lifespan)
app.include_router(forecast_router)


class ChatRequest(BaseModel):
    session_id: str
    message: str


# -----------------------------
# Redis Helper
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
        result = await ingest_pdf_report(
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
        # [RAG 검색 개선]
        # 1. 사용자 질문에서 품목명 추출 시도 (간이 로직)
        target_item = None
        for fruit in ["사과", "배", "포도", "감귤", "딸기", "샤인머스캣", "복숭아"]:
            if fruit in user_message:
                target_item = fruit
                break
        
        rag_context = ""
        
        # 2. 품목명이 있으면 해당 품목 태그로 우선 검색
        if target_item:
            print(f"🔍 품목 감지됨: {target_item} -> 태그 필터 검색 시도")
            # 2-1. 태그 필터 검색
            rag_context = search_general_reports(f"{target_item} 전망 생산량 가격", k=5, item_tag=target_item)
            
            # 2-2. 태그로 안 나오면, 쿼리에 품목명 넣어서 태그 없이 검색 (본문 검색 유도)
            if not rag_context:
                print(f"⚠️ 태그 검색 실패 -> 텍스트 검색 시도(확장): {target_item}")
                # k값을 8로 늘려 더 많은 문서를 탐색
                rag_context = search_general_reports(f"{target_item} 농업관측 전망 수급 동향", k=8)
        
        # 3. 품목명이 없거나 검색 실패 시, 기존 방식(쿼리 확장) 사용
        if not rag_context:
            search_query = f"{user_message} 농업관측 전망 생산량 가격 수급"
            rag_context = search_general_reports(search_query, k=5)

        # 4. 최후의 보루: 전체 리포트 검색
        if not rag_context:
             rag_context = search_general_reports("농업관측 월보 전망", k=5)

        history_messages = get_chat_history(session_id)
        current_msg_obj = HumanMessage(content=user_message)
        
        # 5. 시스템 프롬프트 강화
        if rag_context:
            system_prompt = (
                f"당신은 농산물 시장 분석 전문가입니다. 아래 [참고 문서]를 철저히 분석하여 답변하세요.\n"
                f"사용자가 특정 품목(예: {target_item or '과일'})을 물어봤다면, 문서 내 해당 품목 관련 내용을 모두 찾아 상세히 설명해야 합니다.\n"
                f"문서에 있는 수치(생산량, 면적 등)를 인용할 때는 '문서에 따르면...'이라고 언급하세요.\n\n"
                f"만약 문서에 해당 품목에 대한 직접적인 언급이 부족하더라도, 과일 전체의 동향이나 연관 품목의 정보를 바탕으로 합리적인 추론을 제공하세요.\n\n"
                f"[참고 문서]\n{rag_context}\n\n"
                f"답변 시 주의사항:\n"
                f"- 문서 내용을 최우선으로 하되, 내용이 부족하면 '문서에 직접적인 내용은 없으나...'라고 밝히고 연관 정보를 설명하세요.\n"
                f"- 추측성 답변보다는 문서에 근거한 사실 위주로 답변하세요."
            )
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