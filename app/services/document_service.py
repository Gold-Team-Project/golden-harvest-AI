import uuid
from app.schemas.intent import DocumentIntent
from app.services.data_service import get_data_for_intent
from app.renderers.excel_renderer import generate_excel
from app.renderers.pdf_renderer import generate_pdf


def create_document(intent: DocumentIntent) -> dict:
    data = get_data_for_intent(intent)

    if intent.format == "pdf":
        content, ext, mime = generate_pdf(data), "pdf", "application/pdf"
    else:
        content, ext, mime = generate_excel(
            data), "xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    doc_id = str(uuid.uuid4())
    filename = f"{intent.document_type.lower()}_{doc_id}.{ext}"

    return {
        "document_id": doc_id,
        "filename": filename,
        "mime_type": mime,
        "file_content": content,
        "download_url": f"/documents/{doc_id}/download"
    }