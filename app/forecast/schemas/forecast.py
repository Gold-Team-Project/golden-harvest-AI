# app/schemas/forecast.py
from pydantic import BaseModel, Field
from datetime import date
from typing import Optional, List, Dict


class Location(BaseModel):
    lat: float
    lon: float
    timezone: str = "Asia/Seoul"


class DemandForecastRequest(BaseModel):
    skuNo: str = Field(..., description="SKU 번호")
    startDate: date = Field(..., description="학습 시작일 (출고 기준)")
    endDate: date = Field(..., description="학습 종료일 (출고 기준)")
    horizonMonths: int = Field(6, ge=1, le=24, description="미래 예측 개월 수")
    location: Optional[Location] = None


class ForecastPoint(BaseModel):
    ds: date
    yhat: float
    yhat_lower: float
    yhat_upper: float


class DemandForecastResponse(BaseModel):
    skuNo: str
    status: str
    model: str
    horizonMonths: int
    peakMonth: int
    peakValue: float
    featuresUsed: List[str]
    forecast: List[ForecastPoint]
    monthlyPattern: Dict[int, float]  # month -> avg forecast yhat
