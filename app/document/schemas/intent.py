from pydantic import BaseModel
from datetime import date
from app.document.schemas.documents import DocumentType

class DocumentIntent(BaseModel):
    document_type: DocumentType
    start_date : date
    end_date : date
    format: str
