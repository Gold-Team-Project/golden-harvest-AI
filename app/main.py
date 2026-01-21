# app/main.py
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import uuid
from app.agents.intent_agent import parse_intent
from app.agents.wording_agent import generate_description
from app.renderers.excel_renderer import render_excel
from app.services.data_service import get_inbound_data
from app.services.document_service import build_inbound_document
from app.templates.inbound_excel import INBOUND_COLUMNS
from fastapi.responses import FileResponse
app = FastAPI()

# 아주 단순한 메모리 저장 (지금 단계에서는 충분)
DOCUMENT_STORE = {}


@app.post("/documents")
def create_document(user_message: str):
    intent = parse_intent(user_message)

    if not intent or not intent.start_date or not intent.end_date:
        raise HTTPException(422, "기간 정보를 해석하지 못했습니다.")

    data = get_inbound_data(intent.start_date, intent.end_date)
    rows = build_inbound_document(data)

    file_name = f"inbound_{intent.start_date}_{intent.end_date}.xlsx"
    file_path = render_excel(INBOUND_COLUMNS, rows, file_name)

    doc_id = str(uuid.uuid4())
    DOCUMENT_STORE[doc_id] = file_path

    description = generate_description(intent)

    return {
        "message": description,
        "document_id": doc_id,
        "download_url": f"/documents/{doc_id}/file"
    }


@app.get("/documents/{doc_id}/file")
def download_document(doc_id: str):
    file_path = DOCUMENT_STORE.get(doc_id)

    if not file_path:
        raise HTTPException(404, "문서를 찾을 수 없습니다.")

    return FileResponse(
        path=file_path,
        filename=file_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
