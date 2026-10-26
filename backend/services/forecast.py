"""Forecast processing, decision-cutoff selection, and actuals matching services.

Implements:
- Cutoff selection rule (default 09:00 UTC on D-1, configurable)
- Strict exclusion of forecasts published after cutoff
- Hourly actuals aggregation:
  * Method A (primary): Mean of periods 2k-1 and 2k (strictly requires both periods)
  * Method B (check): Point match at :00
- Safe inner join without zero-filling missing values
- Documented deduplication rules
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np
import pandas as pd


DEFAULT_CUTOFF_TIME = time(9, 0)  # 09:00 UTC (matches 09:00 GMT in January)
DEFAULT_DAYS_BEFORE = 1           # D-1 (day before delivery)


def get_forecast_fetch_window(
    delivery_start: Union[date, str],
    delivery_end: Union[date, str],
    buffer_days: int = 4,
) -> Tuple[datetime, datetime]:
    """Calculate the required WINDFOR publish window to cover all candidate forecasts.

    Because WINDFOR has up to ~66.5h maximum lead time, forecasts for delivery day D
    are published starting from at least D - 3 to D - 4 days prior.
    For 2026-01-01 delivery, fetching starts from at least 2025-12-28 to 2025-12-30.
    """
    if isinstance(delivery_start, str):
        delivery_start = datetime.strptime(delivery_start[:10], "%Y-%m-%d").date()
    if isinstance(delivery_end, str):
        delivery_end = datetime.strptime(delivery_end[:10], "%Y-%m-%d").date()

    fetch_start_date = delivery_start - timedelta(days=buffer_days)
    publish_from = datetime.combine(fetch_start_date, time(0, 0, 0), tzinfo=timezone.utc)
    publish_to = datetime.combine(delivery_end, time(23, 59, 59), tzinfo=timezone.utc)
    return publish_from, publish_to


def deduplicate_forecasts(df: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate WINDFOR forecast records.

    Deduplication Rule:
    - Primary composite key: ['publishTime', 'startTime'].
    - Keeps the last occurrence if duplicates exist.
    """
    if df.empty or "publishTime" not in df.columns or "startTime" not in df.columns:
        return df
    return df.drop_duplicates(subset=["publishTime", "startTime"], keep="last").copy()


def deduplicate_actuals(df: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate FUELHH actual records.

    Deduplication Rule:
    - Primary composite key: ['settlementDate', 'settlementPeriod'] if present,
      otherwise fallback to ['startTime'].
    - Keeps the last occurrence if duplicates exist.
    """
    if df.empty:
        return df

    if "settlementDate" in df.columns and "settlementPeriod" in df.columns:
        return df.drop_duplicates(subset=["settlementDate", "settlementPeriod"], keep="last").copy()
    elif "startTime" in df.columns:
        return df.drop_duplicates(subset=["startTime"], keep="last").copy()
    return df


def select_forecasts(
    forecasts_df: pd.DataFrame,
    cutoff_time: time = DEFAULT_CUTOFF_TIME,
    days_before: int = DEFAULT_DAYS_BEFORE,
) -> pd.DataFrame:
    """Select the definitive Day-Ahead forecast for each target delivery interval.

    Decision-Cutoff Rule:
    1. For each target startTime t on delivery date D:
       Cutoff Timestamp T_cutoff = (D - days_before) at cutoff_time UTC.
    2. Candidate forecasts:
       Must have publishTime <= T_cutoff AND publishTime < startTime (positive lead time).
       Any forecast published after T_cutoff is strictly excluded.
    3. Selection:
       For each target startTime, select the record with the maximum publishTime
       (the latest available intelligence before gate closure).
    4. Diagnostic metrics:
       Calculates lead_time_hours = (startTime - publishTime) in hours.
    """
    if forecasts_df.empty:
        return pd.DataFrame(
            columns=["dataset", "publishTime", "startTime", "generation", "cutoff_time", "lead_time_hours"]
        )

    df = deduplicate_forecasts(forecasts_df)
    df = df.copy()

    # Ensure timezone-aware UTC datetime
    if not pd.api.types.is_datetime64_any_dtype(df["startTime"]):
        df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    elif df["startTime"].dt.tz is None:
        df["startTime"] = df["startTime"].dt.tz_localize("UTC")

    if not pd.api.types.is_datetime64_any_dtype(df["publishTime"]):
        df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)
    elif df["publishTime"].dt.tz is None:
        df["publishTime"] = df["publishTime"].dt.tz_localize("UTC")

    # Determine delivery date D for each interval
    delivery_dates = df["startTime"].dt.floor("D")

    # Compute exact cutoff timestamp for each row: (D - days_before) + cutoff_time
    cutoff_dates = delivery_dates - pd.to_timedelta(days_before, unit="D")
    cutoff_timestamps = (
        cutoff_dates
        + pd.to_timedelta(cutoff_time.hour, unit="h")
        + pd.to_timedelta(cutoff_time.minute, unit="m")
        + pd.to_timedelta(cutoff_time.second, unit="s")
    )

    df["cutoff_time"] = cutoff_timestamps

    # Rule 1: Exclude any forecast published after cutoff (publishTime <= cutoff_time)
    # Rule 2: Exclude retrospective records (publishTime < startTime)
    valid_mask = (df["publishTime"] <= df["cutoff_time"]) & (df["publishTime"] < df["startTime"])
    candidates = df[valid_mask].copy()

    if candidates.empty:
        return pd.DataFrame(
            columns=["dataset", "publishTime", "startTime", "generation", "cutoff_time", "lead_time_hours"]
        )

    # Rule 3: For each target startTime, pick latest publishTime
    # idxmax returns the index of the first maximum publishTime per startTime group
    latest_indices = candidates.groupby("startTime")["publishTime"].idxmax()
    selected = candidates.loc[latest_indices].sort_values("startTime").reset_index(drop=True)

    # Diagnostic lead time in hours
    selected["lead_time_hours"] = (
        (selected["startTime"] - selected["publishTime"]).dt.total_seconds() / 3600.0
    ).round(2)

    return selected


def aggregate_actuals(
    actuals_df: pd.DataFrame,
    method: str = "hourly_mean",
) -> pd.DataFrame:
    """Aggregate half-hourly FUELHH actual records to hourly resolution.

    Methods:
    - 'hourly_mean' (Method A, primary):
      Takes the mean of the two half-hour settlement periods in that hour (periods 2k-1 and 2k).
      STRICT VALIDATION: Requires both periods to exist and be non-null. If only 1 period
      is present, the hour is omitted/marked invalid to prevent distortion.
    - 'point_match' (Method B, check):
      Takes the single actual record starting at :00 without aggregation.
    """
    if actuals_df.empty:
        return pd.DataFrame(columns=["startTime", "generation"])

    df = deduplicate_actuals(actuals_df)
    df = df.copy()

    if not pd.api.types.is_datetime64_any_dtype(df["startTime"]):
        df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    elif df["startTime"].dt.tz is None:
        df["startTime"] = df["startTime"].dt.tz_localize("UTC")

    df["generation"] = pd.to_numeric(df["generation"], errors="coerce")

    if method == "point_match":
        # Select records exactly at the top of the hour (:00)
        point_matched = df[df["startTime"].dt.minute == 0].copy()
        point_matched = point_matched.dropna(subset=["generation"])
        return point_matched[["startTime", "generation"]].sort_values("startTime").reset_index(drop=True)

    elif method == "hourly_mean":
        # Group by the top of the hour
        df["hour_start"] = df["startTime"].dt.floor("h")

        # Group and check completeness (must have exactly 2 periods per hour and no NaN)
        grouped = df.groupby("hour_start")

        valid_hours = []
        for hour_start, group in grouped:
            # Check period count and valid generation
            clean_gens = group["generation"].dropna()
            if len(group) == 2 and len(clean_gens) == 2:
                valid_hours.append(
                    {
                        "startTime": hour_start,
                        "generation": clean_gens.mean(),
                    }
                )

        if not valid_hours:
            return pd.DataFrame(columns=["startTime", "generation"])

        return pd.DataFrame(valid_hours).sort_values("startTime").reset_index(drop=True)

    else:
        raise ValueError(f"Unknown aggregation method: {method}. Use 'hourly_mean' or 'point_match'.")


def match(
    forecasts_df: pd.DataFrame,
    actuals_df: pd.DataFrame,
    method: str = "hourly_mean",
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Join selected forecasts with actuals on target startTime.

    Rules:
    - Never fills missing values with zero.
    - Uses an inner join on startTime.
    - Returns matched DataFrame and diagnostic summary counts.
    """
    if forecasts_df.empty or actuals_df.empty:
        matched_empty = pd.DataFrame(
            columns=[
                "startTime",
                "forecast_generation",
                "actual_generation",
                "publishTime",
                "cutoff_time",
                "lead_time_hours",
            ]
        )
        return matched_empty, {
            "matched_count": 0,
            "unmatched_actuals_count": len(actuals_df),
            "unmatched_forecasts_count": len(forecasts_df),
            "method": method,
        }

    agg_actuals = aggregate_actuals(actuals_df, method=method)

    # Ensure UTC timezone alignment
    if not pd.api.types.is_datetime64_any_dtype(forecasts_df["startTime"]):
        forecasts_clean = forecasts_df.copy()
        forecasts_clean["startTime"] = pd.to_datetime(forecasts_clean["startTime"], utc=True)
    else:
        forecasts_clean = forecasts_df.copy()

    # Inner join on startTime
    matched = pd.merge(
        forecasts_clean[["startTime", "generation", "publishTime", "cutoff_time", "lead_time_hours"]],
        agg_actuals[["startTime", "generation"]],
        on="startTime",
        how="inner",
        suffixes=("_forecast", "_actual"),
    )

    matched = matched.rename(
        columns={
            "generation_forecast": "forecast_generation",
            "generation_actual": "actual_generation",
        }
    )

    # Ensure numeric columns
    matched["forecast_generation"] = pd.to_numeric(matched["forecast_generation"])
    matched["actual_generation"] = pd.to_numeric(matched["actual_generation"])

    unmatched_actuals = len(agg_actuals) - len(matched)
    unmatched_forecasts = len(forecasts_clean) - len(matched)

    diagnostics = {
        "matched_count": len(matched),
        "unmatched_actuals_count": max(0, unmatched_actuals),
        "unmatched_forecasts_count": max(0, unmatched_forecasts),
        "method": method,
    }

    return matched.sort_values("startTime").reset_index(drop=True), diagnostics
