# tests/unit/test_forecast_service.py
import pandas as pd
from datetime import date
from app.forecast.services.demand_forecast_service import(
    _make_future_months,
    _monthly_pattern_from_forecast,
    run_demand_forecast
)

def test_make_future_months():
    last_ds = pd.Timestamp("2024-01-01")
    df = _make_future_months(last_ds, 3)

    assert len(df) == 3
    assert df["ds"].iloc[0].month == 2

def test_monthly_pattern_from_forecast():
    forecast = pd.DataFrame({
        "ds": pd.to_datetime(["2024-01-01", "2024-02-01"]),
        "yhat": [100, 200]
    })
    pat = _monthly_pattern_from_forecast(forecast)

    assert pat == {1: 100.0, 2: 200.0}

def test_run_forecast_insufficient_data(monkeypatch):
    monkeypatch.setattr(
        "app.forecast.services.demand_forecast_service.fetch_outbound_history_by_sku",
        lambda *args, **kwargs: []
    )

    result = run_demand_forecast(
        sku_no="SKU-1",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 6, 1)
    )

    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["forecast"] == []
