import uuid
from app.document.schemas.documents import DocumentIntent
from app.document.services.data_service import get_data_for_intent
from app.document.renderers.excel_renderer import generate_excel

BASE_URL = "http://localhost:8000"

def create_document(intent: DocumentIntent) -> dict:
    data = get_data_for_intent(intent)

    content, ext, mime = generate_excel(data)

    doc_id = str(uuid.uuid4())
    doc_type_str = getattr(intent.document_type, 'name', str(intent.document_type))
    filename = f"{doc_type_str.lower()}_{doc_id[:8]}.{ext}"

    return {
        "document_id": doc_id,
        "filename": filename,
        "mime_type": mime,
        "content": content,
        "download_url": f"{BASE_URL}/documents/{doc_id}/download"

    }