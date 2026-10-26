"""Unit tests for metrics calculation."""

import numpy as np
import pandas as pd
import pytest

from backend.services.metrics import calculate_metrics, compute_interval_errors


def test_metrics_required_example():
    """Verify that forecasts [100, 200] vs actuals [120, 180] gives MAE 20 and RMSE 20."""
    matched_df = pd.DataFrame(
        {
            "startTime": pd.date_range("2026-01-01 00:00:00Z", periods=2, freq="h"),
            "forecast_generation": [100.0, 200.0],
            "actual_generation": [120.0, 180.0],
        }
    )

    metrics = calculate_metrics(matched_df)

    assert metrics["n_matched"] == 2
    # Errors: [100-120=-20, 200-180=+20] -> abs errors: [20, 20] -> MAE = 20.0
    assert metrics["mae"] == 20.0
    # Squared errors: [400, 400] -> mean = 400 -> sqrt = 20.0
    assert metrics["rmse"] == 20.0
    # Mean error (bias): (-20 + 20) / 2 = 0.0
    assert metrics["mean_error"] == 0.0
    # MAPE: (|100-120|/120 + |200-180|/180) / 2 = (1/6 + 1/9) / 2 = 0.13888... -> 13.89%
    assert metrics["mape"] == round((20 / 120 + 20 / 180) / 2 * 100, 2)
    assert metrics["excluded_zero_actuals"] == 0


def test_mape_with_zero_actuals():
    """Verify that intervals with actual == 0 are excluded from MAPE, counted, and avoid ZeroDivisionError."""
    matched_df = pd.DataFrame(
        {
            "startTime": pd.date_range("2026-01-01 00:00:00Z", periods=3, freq="h"),
            "forecast_generation": [10.0, 120.0, 50.0],
            "actual_generation": [0.0, 100.0, 50.0],  # First actual is zero
        }
    )

    metrics = calculate_metrics(matched_df)

    assert metrics["n_matched"] == 3
    # Excluded count must be 1
    assert metrics["excluded_zero_actuals"] == 1
    # MAE and RMSE include all 3 rows:
    # abs errors: [10, 20, 0] -> MAE = 30 / 3 = 10.0
    assert metrics["mae"] == 10.0
    # MAPE should only compute on valid actuals:
    # row 2: |120-100|/100 = 20%
    # row 3: |50-50|/50 = 0%
    # Mean MAPE: (20% + 0%) / 2 = 10.0%
    assert metrics["mape"] == 10.0


def test_mape_all_zero_actuals():
    """Verify that when all actuals are zero, MAPE returns None gracefully."""
    matched_df = pd.DataFrame(
        {
            "startTime": pd.date_range("2026-01-01 00:00:00Z", periods=2, freq="h"),
            "forecast_generation": [10.0, 20.0],
            "actual_generation": [0.0, 0.0],
        }
    )

    metrics = calculate_metrics(matched_df)
    assert metrics["n_matched"] == 2
    assert metrics["excluded_zero_actuals"] == 2
    assert metrics["mape"] is None
    assert metrics["mae"] == 15.0


def test_metrics_empty_dataframe():
    """Verify that an empty matched dataframe returns safe null/zero metrics."""
    empty_df = pd.DataFrame(columns=["startTime", "forecast_generation", "actual_generation"])
    metrics = calculate_metrics(empty_df)

    assert metrics["n_matched"] == 0
    assert metrics["mae"] is None
    assert metrics["rmse"] is None
    assert metrics["mean_error"] is None
    assert metrics["mape"] is None
    assert metrics["excluded_zero_actuals"] == 0


def test_compute_interval_errors():
    """Verify detailed interval error column additions."""
    matched_df = pd.DataFrame(
        {
            "startTime": pd.date_range("2026-01-01 00:00:00Z", periods=2, freq="h"),
            "forecast_generation": [150.0, 80.0],
            "actual_generation": [100.0, 100.0],
        }
    )

    df_err = compute_interval_errors(matched_df)

    assert "error" in df_err.columns
    assert "abs_error" in df_err.columns
    assert "pct_error" in df_err.columns
    assert list(df_err["error"]) == [50.0, -20.0]
    assert list(df_err["abs_error"]) == [50.0, 20.0]
    assert list(df_err["pct_error"]) == [50.0, 20.0]
