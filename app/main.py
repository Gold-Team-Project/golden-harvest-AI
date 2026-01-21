import urllib.parse
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.agents.intent_agent import parse_intent
from app.agents.wording_agent import generate_description
from app.services.document_service import create_document

app = FastAPI()
DOCUMENT_STORE = {}

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
    print(f"DEBUG Intent: {intent}")

    doc_result = create_document(intent)

    # 메모리 저장 (실무에선 DB/S3 사용 권장)
    DOCUMENT_STORE[doc_result["document_id"]] = doc_result

    description = generate_description(intent)

    return {
        "message": description,
        "document_id": doc_result["document_id"],
        "download_url": doc_result["download_url"],
        "mime_type": doc_result["mime_type"]
    }


@app.get("/documents/{doc_id}/download")
def download_document(doc_id: str):
    file_data = DOCUMENT_STORE.get(doc_id)
    if not file_data:
        return JSONResponse(status_code=404, content={"error": "File not found"})

    encoded_name = urllib.parse.quote(file_data["filename"])
    return Response(
        content=file_data["file_content"],
        media_type=file_data["mime_type"],
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"}
    )