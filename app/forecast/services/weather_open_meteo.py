# app/services/forecast/weather_open_meteo.py
import requests
import pandas as pd
from datetime import date


OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


def fetch_daily_weather(
    lat: float,
    lon: float,
    start_date: date,
    end_date: date,
    timezone: str
) -> pd.DataFrame:
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": str(start_date),
        "end_date": str(end_date),
        "daily": "temperature_2m_mean,apparent_temperature_mean,precipitation_sum",
        "timezone": timezone
    }

    r = requests.get(OPEN_METEO_ARCHIVE_URL, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()

    daily = data.get("daily", {})
    times = daily.get("time", [])
    temps = daily.get("temperature_2m_mean", [])
    feels = daily.get("apparent_temperature_mean", [])
    prec = daily.get("precipitation_sum", [])

    df = pd.DataFrame({
        "ds": pd.to_datetime(times),
        "temp": temps,
        "feels_like": feels,
        "precipitation": prec
    })

    return df


def to_monthly_features(daily_df: pd.DataFrame) -> pd.DataFrame:
    df = daily_df.copy()
    df["ds"] = df["ds"].dt.to_period("M").dt.to_timestamp()  # 월 시작일

    monthly = df.groupby("ds").agg(
        temp=("temp", "mean"),
        feels_like=("feels_like", "mean"),
        precipitation=("precipitation", "sum"),
    ).reset_index()

    monthly = monthly.fillna(method="ffill").fillna(method="bfill")
    return monthly


def build_future_weather_by_climatology(
    monthly_history: pd.DataFrame,
    future_months: pd.DataFrame
) -> pd.DataFrame:

    hist = monthly_history.copy()
    hist["month"] = pd.to_datetime(hist["ds"]).dt.month

    normals = hist.groupby("month").agg(
        temp=("temp", "mean"),
        feels_like=("feels_like", "mean"),
        precipitation=("precipitation", "mean"),
    ).reset_index()

    fut = future_months.copy()
    fut["month"] = pd.to_datetime(fut["ds"]).dt.month

    fut = fut.merge(normals, on="month", how="left").drop(columns=["month"])
    fut = fut.fillna(method="ffill").fillna(method="bfill")
    return fut
