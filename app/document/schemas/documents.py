from enum import Enum
from datetime import date
from typing import Literal, Optional
from pydantic import BaseModel, Field

class DocumentType(str, Enum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"
    PURCHASE_ORDER = "PURCHASE_ORDER"
    ORDER_SHEET = "ORDER_SHEET"

class DocumentIntent(BaseModel):
    intent_type: Literal["DOCUMENT"] = Field("DOCUMENT", description="의도 타입 (문서 생성)")
    document_type: DocumentType = Field(..., description="문서 종류")
    start_date: date = Field(..., description="조회 시작 날짜")
    end_date: date = Field(..., description="조회 종료 날짜")
    format: str = Field("excel", description="파일 포맷 (excel 또는 pdf)")

class ForecastIntent(BaseModel):
    intent_type: Literal["FORECAST"] = Field("FORECAST", description="의도 타입 (수요 예측)")
    skuNo: str = Field(..., description="예측할 상품의 SKU 번호")
    start_date: date = Field(..., description="학습 데이터 시작일")
    end_date: date = Field(..., description="학습 데이터 종료일")
    horizon_months: int = Field(6, description="미래 예측 개월 수")

class ChatIntent(BaseModel):
    intent_type: Literal["CHAT"]
    message: str
    sku_no: Optional[str] = None