from enum import Enum
from datetime import date
from pydantic import BaseModel, Field

class DocumentType(str, Enum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"
    PURCHASE_ORDER = "PURCHASE_ORDER"
    ORDER_SHEET = "ORDER_SHEET"

class DocumentIntent(BaseModel):
    document_type: DocumentType = Field(description="문서 종류 (INBOUND, OUTBOUND, PURCHASE_ORDER, ORDER_SHEET)")
    start_date: date = Field(description="시작 날짜 (YYYY-MM-DD)")
    end_date: date = Field(description="종료 날짜 (YYYY-MM-DD)")
    format: str = Field(description="파일 포맷 (excel 또는 pdf)")