import urllib.parse
from fastapi import FastAPI, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.agents.intent_agent import parse_intent
from app.agents.wording_agent import generate_description
from app.document.schemas.documents import ForecastIntent, DocumentIntent
from app.document.services.document_service import create_document
from app.forecast.routers.forecast_router import router as forecast_router
from app.forecast.services.demand_forecast_service import run_demand_forecast
from app.config import llm

app = FastAPI()
app.include_router(forecast_router)

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


@app.post("/chat")
def chat_endpoint(request: ChatRequest):
    intent = parse_intent(request.message)

    if isinstance(intent, ForecastIntent):
        forecast_result = run_demand_forecast(
            sku_no=intent.skuNo,
            start_date=intent.start_date,
            end_date=intent.end_date,
            horizon_months=intent.horizon_months
        )

        LAST_FORECAST[intent.skuNo] = forecast_result

        monthly = [
            {"month": row["ds"].month, "quantity": int(round(row["yhat"]))}
            for row in forecast_result.get("forecast", [])
        ]

        message = generate_description(
            intent=intent,
            forecast_data={
                "sku": intent.skuNo,
                "monthly_forecast": monthly
            }
        )

        return {
            "type": "FORECAST",
            "message": message,
            "data": forecast_result
        }

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

    msg = request.message

    if any(k in msg for k in ["왜", "이유", "근거", "설명"]):
        if LAST_FORECAST:
            last = list(LAST_FORECAST.values())[-1]

            explanation = llm.invoke(
                f"""
너는 ERP 시스템의 수요 예측 설명 AI다.
모델 이름이나 알고리즘은 언급하지 마라.
과거 출고 패턴과 계절성 관점에서
아래 예측 결과가 왜 이렇게 나왔는지 설명해라.

[예측 결과]
{last}
"""
            ).content

            return {
                "type": "CHAT",
                "message": explanation
            }

    response = llm.invoke(msg)

    return {
        "type": "CHAT",
        "message": response.content
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
