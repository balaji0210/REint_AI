"""Forecast accuracy, error evaluation, and benchmark metrics services.

Computes:
- Error: (Forecast - Actual)
- MAE: Mean Absolute Error (MW)
- RMSE: Root Mean Squared Error (MW)
- Mean Error / Bias: Mean of (Forecast - Actual) in MW
- MAPE: Mean Absolute Percentage Error (%), strictly excluding Actual == 0 (with excluded count reported)
- WAPE: Weighted Absolute Percentage Error (%)
- Comparison between Method A (hourly mean) and Method B (point match)
"""

from typing import Any, Dict, Optional
import numpy as np
import pandas as pd


def compute_interval_errors(
    matched_df: pd.DataFrame,
    actual_col: str = "actual_generation",
    forecast_col: str = "forecast_generation",
) -> pd.DataFrame:
    """Add row-level error diagnostic columns to matched DataFrame.

    Columns added:
    - error: (Forecast - Actual) in MW
    - abs_error: |Forecast - Actual| in MW
    - squared_error: (Forecast - Actual)^2
    - pct_error: |Forecast - Actual| / Actual * 100 (NaN when Actual == 0)
    """
    if matched_df.empty:
        df = matched_df.copy()
        df["error"] = pd.Series(dtype=float)
        df["abs_error"] = pd.Series(dtype=float)
        df["squared_error"] = pd.Series(dtype=float)
        df["pct_error"] = pd.Series(dtype=float)
        return df

    df = matched_df.copy()
    f = df[forecast_col].astype(float)
    a = df[actual_col].astype(float)

    df["error"] = f - a
    df["abs_error"] = df["error"].abs()
    df["squared_error"] = df["error"] ** 2

    # Avoid zero division: place np.nan where Actual == 0
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = (df["abs_error"] / a) * 100.0
        pct = pct.where(a != 0, np.nan)
    df["pct_error"] = pct

    return df


def calculate_metrics(
    matched_df: pd.DataFrame,
    actual_col: str = "actual_generation",
    forecast_col: str = "forecast_generation",
) -> Dict[str, Any]:
    """Calculate overall accuracy metrics across all matched intervals.

    Returns:
    - n_matched: Number of valid matched delivery intervals (N)
    - mae: Mean Absolute Error (MW)
    - rmse: Root Mean Squared Error (MW)
    - mean_error: Mean Bias (MW). Positive = over-forecasting, Negative = under-forecasting
    - mape: Mean Absolute Percentage Error (%), strictly excluding Actual == 0
    - excluded_zero_actuals: Number of intervals where Actual == 0 was excluded from MAPE
    - wape: Weighted Absolute Percentage Error (%)
    """
    n = len(matched_df)
    if n == 0:
        return {
            "n_matched": 0,
            "mae": None,
            "rmse": None,
            "mean_error": None,
            "mape": None,
            "excluded_zero_actuals": 0,
            "wape": None,
        }

    df_err = compute_interval_errors(matched_df, actual_col=actual_col, forecast_col=forecast_col)

    errors = df_err["error"]
    abs_errors = df_err["abs_error"]
    squared_errors = df_err["squared_error"]

    mae = float(abs_errors.mean())
    rmse = float(np.sqrt(squared_errors.mean()))
    mean_error = float(errors.mean())

    # Handle MAPE excluding Actual == 0
    actuals = matched_df[actual_col].astype(float)
    zero_actuals_mask = (actuals == 0)
    excluded_zero_count = int(zero_actuals_mask.sum())

    valid_mape_series = df_err["pct_error"].dropna()
    if len(valid_mape_series) > 0:
        mape = float(valid_mape_series.mean())
    else:
        mape = None

    # WAPE = sum(|F - A|) / sum(A) * 100
    sum_actuals = float(actuals.sum())
    if sum_actuals > 0:
        wape = float((abs_errors.sum() / sum_actuals) * 100.0)
    else:
        wape = None

    return {
        "n_matched": n,
        "mae": round(mae, 2),
        "rmse": round(rmse, 2),
        "mean_error": round(mean_error, 2),
        "mape": round(mape, 2) if mape is not None else None,
        "excluded_zero_actuals": excluded_zero_count,
        "wape": round(wape, 2) if wape is not None else None,
    }
