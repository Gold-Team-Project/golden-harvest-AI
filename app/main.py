import os
import urllib.parse
import json
import redis
import tempfile
import glob
import logging
import base64
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

# ✅ init_registry_table import 확인
from app.rag.ingest import ingest_pdf_report, init_registry_table
from app.config import llm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redis 설정
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    decode_responses=True
)

# -----------------------------
# Lifespan
# -----------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_registry_table()
        logger.info("✅ [DB Init] RAG 레지스트리 테이블 확인/생성 완료.")
    except Exception as e:
        logger.error(f"❌ [DB Init] 테이블 생성 실패: {e}")

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
    yield
    pass


app = FastAPI(lifespan=lifespan)
app.include_router(forecast_router)


class ChatRequest(BaseModel):
    session_id: str
    message: str


# -----------------------------
# Redis Helpers
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

# [신규] 파일 데이터를 Redis에 임시 저장 (중앙 저장소 활용)
def save_doc_to_redis(doc_id: str, doc_data: dict):
    key = f"doc_store:{doc_id}"
    # bytes 데이터는 base64 인코딩 처리
    serializable_data = {
        "filename": doc_data["filename"],
        "mime_type": doc_data["mime_type"],
        "content": base64.b64encode(doc_data["content"]).decode('utf-8')
    }
    redis_client.set(key, json.dumps(serializable_data))
    redis_client.expire(key, 1800)  # 30분 후 자동 파기


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

        from app.rag.service import resolve_sku_to_item_and_variety
        item_name, variety_name, _, _ = await resolve_sku_to_item_and_variety(intent.skuNo)

        query_month = None
        try:
            if intent.start_date:
                query_month = int(str(intent.start_date)[5:7])
        except Exception:
            query_month = None

        rag_context = await get_expert_insight(sku_no=intent.skuNo, query_month=query_month, query_period=None)
        if not rag_context:
            rag_context = "관련된 시장 리포트가 발견되지 않았습니다."

        ai_response_message = generate_description(
            intent=intent,
            forecast_data={
                "sku": intent.skuNo,
                "item_name": item_name or "알 수 없음",
                "variety_name": variety_name or "전체",
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

        # [수정] 메모리(DOCUMENT_STORE) 대신 Redis에 저장 (서버 분산 환경 대응)
        save_doc_to_redis(doc["document_id"], doc)

        ai_response_message = generate_description(intent)

        # [중요 수정] Gateway의 Prefix 규칙(api/ai)에 맞춰 경로를 설정합니다.
        # 프론트 baseURL(/api) + 여기서 준 경로(ai/...) = /api/ai/documents/... 가 최종 호출됩니다.
        relative_url = f"ai/documents/{doc['document_id']}/download"

        response_data = {
            "type": "DOCUMENT",
            "message": ai_response_message,
            "document_id": doc["document_id"],
            "download_url": relative_url, # ai/ 접두사 추가
            "mime_type": doc["mime_type"]
        }

    else:
        # RAG 검색 로직 (기존 유지)
        target_item = None
        for fruit in ["사과", "배", "포도", "감귤", "딸기", "샤인머스캣", "복숭아"]:
            if fruit in user_message:
                target_item = fruit
                break

        rag_context = ""
        if target_item:
            rag_context = search_general_reports(f"{target_item} 전망 생산량 가격", k=5, item_tag=target_item)
            if not rag_context:
                rag_context = search_general_reports(f"{target_item} 농업관측 전망 수급 동향", k=8)
        if not rag_context:
            search_query = f"{user_message} 농업관측 전망 생산량 가격 수급"
            rag_context = search_general_reports(search_query, k=5)
        if not rag_context:
            rag_context = search_general_reports("농업관측 월보 전망", k=5)

        history_messages = get_chat_history(session_id)
        current_msg_obj = HumanMessage(content=user_message)

        if rag_context:
            system_prompt = (
                f"당신은 농산물 시장 분석 전문가입니다. 아래 [참고 문서]를 분석하여 답변하세요.\n"
                f"[참고 문서]\n{rag_context}\n"
            )
            messages_to_send = [SystemMessage(content=system_prompt)] + history_messages + [current_msg_obj]
        else:
            messages_to_send = history_messages + [current_msg_obj]

        ai_response = llm.invoke(messages_to_send)
        ai_response_message = ai_response.content
        response_data = {"type": "CHAT", "message": ai_response_message}

    if ai_response_message:
        save_chat_to_redis(session_id, user_message, ai_response_message)
    return response_data

# [주의] Gateway가 /api/ai/documents를 /documents로 Rewrite하므로 백엔드 경로는 /documents를 유지합니다.
@app.get("/documents/{doc_id}/download")
def download_document(doc_id: str):
    # [수정] Redis에서 데이터를 조회 (서버 인스턴스가 달라도 공유됨)
    key = f"doc_store:{doc_id}"
    raw_data = redis_client.get(key)

    if not raw_data:
        raise HTTPException(status_code=404, detail="파일이 존재하지 않거나 만료되었습니다.")

    file_data = json.loads(raw_data)
    # base64 문자열을 다시 바이너리(bytes)로 복원
    content = base64.b64decode(file_data["content"])

    return Response(
        content=content,
        media_type=file_data["mime_type"],
        headers={
            "Content-Disposition":
                f"attachment; filename*=UTF-8''{urllib.parse.quote(file_data['filename'])}"
        }
    )