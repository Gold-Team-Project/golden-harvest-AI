# app/routers/forecast_router.py
from fastapi import APIRouter
from app.forecast.schemas.forecast import DemandForecastRequest, DemandForecastResponse
from app.forecast.services.demand_forecast_service import run_demand_forecast

router = APIRouter(prefix="/forecast", tags=["Forecast"])


@router.post("/demand", response_model=DemandForecastResponse)
def demand_forecast(req: DemandForecastRequest):
    loc = req.location.model_dump() if req.location else None
    result = run_demand_forecast(
        sku_no=req.skuNo,
        start_date=req.startDate,
        end_date=req.endDate,
        horizon_months=req.horizonMonths,
        location=loc
    )
    return result
