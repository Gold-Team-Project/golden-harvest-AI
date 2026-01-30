import pandas as pd
from datetime import date
from typing import Dict, Any, List
from dateutil.relativedelta import relativedelta

from app.config import (
    WEATHER_LAT, WEATHER_LON, WEATHER_TIMEZONE,
    FORECAST_DEFAULT_HORIZON_MONTHS
)
from app.forecast.services.outbound_history import fetch_outbound_history_by_sku
from app.forecast.services.weather_open_meteo import (
    fetch_daily_weather, to_monthly_features, build_future_weather_by_climatology
)
from app.forecast.services.feature_builder import outbounds_to_monthly_y, merge_y_with_weather
from app.forecast.services.prophet_model import fit_and_predict, REGRESSORS


def _make_future_months(last_ds: pd.Timestamp, months: int) -> pd.DataFrame:
    future_ds = pd.date_range(start=last_ds, periods=months + 1, freq="MS")[1:]
    return pd.DataFrame({"ds": future_ds})


def _monthly_pattern_from_forecast(forecast: pd.DataFrame) -> Dict[int, float]:
    df = forecast.copy()
    df["month"] = pd.to_datetime(df["ds"]).dt.month
    pat = df.groupby("month")["yhat"].mean().round(2).to_dict()
    return {int(k): float(v) for k, v in pat.items()}


def run_demand_forecast(
        sku_no: str,
        start_date: date,
        end_date: date,
        horizon_months: int = FORECAST_DEFAULT_HORIZON_MONTHS,
        location: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    history_end = start_date - relativedelta(days=1)
    history_start = start_date - relativedelta(years=10)


    print(f">>> [Forecast] Target: {start_date}~{end_date}")
    print(f">>> [Forecast] Training with: {history_start}~{history_end}")
    # =========================================================

    rows = fetch_outbound_history_by_sku(sku_no, history_start, history_end)

    monthly_y = outbounds_to_monthly_y(rows)

    if len(monthly_y) < 12:
        print(f">>> [Warning] 데이터 부족! 조회된 월 개수: {len(monthly_y)}")
        return {
            "skuNo": sku_no,
            "status": "INSUFFICIENT_DATA",
            "model": "Prophet+Weather",
            "horizonMonths": horizon_months,
            "peakMonth": 0,
            "peakValue": 0.0,
            "featuresUsed": REGRESSORS,
            "forecast": [],
            "monthlyPattern": {}
        }
    # 2) 날씨 (학습 구간)
    lat = (location or {}).get("lat", WEATHER_LAT)
    lon = (location or {}).get("lon", WEATHER_LON)
    tz = (location or {}).get("timezone", WEATHER_TIMEZONE)

    daily_weather = fetch_daily_weather(lat, lon, history_start, history_end, tz)
    monthly_weather = to_monthly_features(daily_weather)

    train_df = merge_y_with_weather(monthly_y, monthly_weather)

    train_df = train_df[["ds", "y"] + REGRESSORS].copy()

    last_ds = pd.to_datetime(train_df["ds"]).max()

    future_months = _make_future_months(last_ds, horizon_months)
    future_weather = build_future_weather_by_climatology(monthly_weather, future_months)

    future_df = pd.concat(
        [train_df[["ds"] + REGRESSORS], future_weather],
        axis=0,
        ignore_index=True
    )
    future_df = future_df.drop_duplicates(subset=["ds"], keep="last").sort_values("ds")

    forecast = fit_and_predict(train_df, future_df)

    fc = forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].copy()
    fc["ds"] = pd.to_datetime(fc["ds"]).dt.date

    future_start_date = (last_ds + pd.offsets.MonthBegin(1)).date()
    future_end_date = (last_ds + pd.offsets.MonthBegin(horizon_months)).date()
    fc_future = fc[(fc["ds"] >= future_start_date) & (fc["ds"] <= future_end_date)].copy()

    if not fc_future.empty:
        peak_row = fc_future.loc[fc_future["yhat"].idxmax()]
        peak_month = pd.to_datetime(peak_row["ds"]).month
        peak_value = float(round(peak_row["yhat"], 2))
    else:
        peak_month = 0
        peak_value = 0.0

    monthly_pattern = _monthly_pattern_from_forecast(fc_future.assign(ds=pd.to_datetime(fc_future["ds"])))

    return {
        "skuNo": sku_no,
        "status": "OK",
        "model": "Prophet+Weather(Open-Meteo)",
        "horizonMonths": horizon_months,
        "peakMonth": int(peak_month),
        "peakValue": peak_value,
        "featuresUsed": REGRESSORS,
        "forecast": [
            {
                "ds": row["ds"],
                "yhat": float(round(row["yhat"], 2)),
                "yhat_lower": float(round(row["yhat_lower"], 2)),
                "yhat_upper": float(round(row["yhat_upper"], 2)),
            }
            for _, row in fc_future.iterrows()
        ],
        "monthlyPattern": monthly_pattern
    }