# app/services/forecast/prophet_model.py
from prophet import Prophet
import pandas as pd


REGRESSORS = ["temp", "feels_like", "precipitation"]


def fit_and_predict(
    train_df: pd.DataFrame,
    future_df: pd.DataFrame
) -> pd.DataFrame:
    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
        changepoint_prior_scale=0.01,
        seasonality_prior_scale=10.0,
        seasonality_mode='multiplicative'
    )

    for r in REGRESSORS:
        model.add_regressor(r, standardize=True)

    model.fit(train_df)

    forecast = model.predict(future_df)
    return forecast
