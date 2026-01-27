# app/services/forecast/feature_builder.py
import pandas as pd
from datetime import date
from typing import List, Dict


def outbounds_to_monthly_y(rows: List[Dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["ds", "y"])

    df = pd.DataFrame(rows)
    df["outboundDate"] = pd.to_datetime(df["outboundDate"])
    df["ds"] = df["outboundDate"].dt.to_period("M").dt.to_timestamp()
    df["y"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)

    monthly = df.groupby("ds")["y"].sum().reset_index()
    monthly = monthly.sort_values("ds")
    return monthly


def merge_y_with_weather(monthly_y: pd.DataFrame, monthly_weather: pd.DataFrame) -> pd.DataFrame:

    merged = pd.merge(monthly_y, monthly_weather, on="ds", how="left")
    # 결측은 주변 값으로 채움
    merged = merged.ffill().bfill()
    return merged
