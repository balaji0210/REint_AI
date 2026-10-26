"""Unit tests for forecast processing, cutoff selection, and matching."""

from datetime import date, datetime, time, timezone
import pandas as pd
import pytest

from backend.services.forecast import (
    aggregate_actuals,
    deduplicate_actuals,
    deduplicate_forecasts,
    get_forecast_fetch_window,
    match,
    select_forecasts,
)


def test_forecast_published_after_cutoff_is_excluded():
    """Verify that any forecast published after the cutoff is strictly excluded."""
    # Target delivery interval: 2026-01-02 12:00:00 UTC
    # Delivery date D = 2026-01-02.
    # Default Cutoff: D - 1 (2026-01-01) at 09:00:00 UTC.
    forecasts = pd.DataFrame(
        [
            {
                "dataset": "WINDFOR",
                "publishTime": "2026-01-01T07:30:00Z",  # Before cutoff (valid)
                "startTime": "2026-01-02T12:00:00Z",
                "generation": 500.0,
            },
            {
                "dataset": "WINDFOR",
                "publishTime": "2026-01-01T09:30:00Z",  # After cutoff (invalid!)
                "startTime": "2026-01-02T12:00:00Z",
                "generation": 999.0,
            },
        ]
    )

    selected = select_forecasts(forecasts, cutoff_time=time(9, 0), days_before=1)

    assert len(selected) == 1
    # Must pick the 07:30 forecast, NOT the 09:30 one
    assert selected.iloc[0]["generation"] == 500.0
    assert selected.iloc[0]["publishTime"] == pd.Timestamp("2026-01-01 07:30:00Z")


def test_multiple_forecasts_selects_latest_before_cutoff():
    """Verify that among multiple forecasts published before the cutoff, the latest is selected."""
    # Delivery: 2026-01-02 14:00:00 UTC
    # Cutoff: 2026-01-01 09:00:00 UTC
    forecasts = pd.DataFrame(
        [
            {
                "dataset": "WINDFOR",
                "publishTime": "2025-12-31T22:30:00Z",  # Early forecast
                "startTime": "2026-01-02T14:00:00Z",
                "generation": 300.0,
            },
            {
                "dataset": "WINDFOR",
                "publishTime": "2026-01-01T04:30:00Z",  # Intermediate forecast
                "startTime": "2026-01-02T14:00:00Z",
                "generation": 350.0,
            },
            {
                "dataset": "WINDFOR",
                "publishTime": "2026-01-01T07:30:00Z",  # Latest forecast before cutoff
                "startTime": "2026-01-02T14:00:00Z",
                "generation": 380.0,
            },
            {
                "dataset": "WINDFOR",
                "publishTime": "2026-01-01T11:30:00Z",  # After cutoff
                "startTime": "2026-01-02T14:00:00Z",
                "generation": 450.0,
            },
        ]
    )

    selected = select_forecasts(forecasts, cutoff_time=time(9, 0))

    assert len(selected) == 1
    assert selected.iloc[0]["generation"] == 380.0
    assert selected.iloc[0]["publishTime"] == pd.Timestamp("2026-01-01 07:30:00Z")
    # Lead time check: 2026-01-02 14:00 minus 2026-01-01 07:30 = 30.5 hours
    assert selected.iloc[0]["lead_time_hours"] == 30.5


def test_january_boundary_coverage():
    """Verify that 1 Jan delivery correctly uses a forecast published in Dec 2025."""
    # Target delivery: 2026-01-01 12:00:00 UTC
    # Cutoff: 2025-12-31 09:00:00 UTC
    forecasts = pd.DataFrame(
        [
            {
                "dataset": "WINDFOR",
                "publishTime": "2025-12-30T18:30:00Z",
                "startTime": "2026-01-01T12:00:00Z",
                "generation": 12000.0,
            },
            {
                "dataset": "WINDFOR",
                "publishTime": "2025-12-31T07:30:00Z",  # Published in Dec before 09:00 cutoff
                "startTime": "2026-01-01T12:00:00Z",
                "generation": 12500.0,
            },
            {
                "dataset": "WINDFOR",
                "publishTime": "2025-12-31T15:30:00Z",  # Published in Dec but after 09:00 cutoff
                "startTime": "2026-01-01T12:00:00Z",
                "generation": 13000.0,
            },
        ]
    )

    selected = select_forecasts(forecasts, cutoff_time=time(9, 0))

    assert len(selected) == 1
    assert selected.iloc[0]["generation"] == 12500.0
    assert selected.iloc[0]["publishTime"] == pd.Timestamp("2025-12-31 07:30:00Z")


def test_missing_values_not_zero_filled():
    """Verify that unmatched intervals are NOT zero-filled."""
    # 3 hourly forecasts
    forecasts = pd.DataFrame(
        [
            {"startTime": "2026-01-01T00:00:00Z", "generation": 100.0, "publishTime": "2025-12-31T07:30:00Z", "cutoff_time": "2025-12-31T09:00:00Z", "lead_time_hours": 16.5},
            {"startTime": "2026-01-01T01:00:00Z", "generation": 200.0, "publishTime": "2025-12-31T07:30:00Z", "cutoff_time": "2025-12-31T09:00:00Z", "lead_time_hours": 17.5},
            {"startTime": "2026-01-01T02:00:00Z", "generation": 300.0, "publishTime": "2025-12-31T07:30:00Z", "cutoff_time": "2025-12-31T09:00:00Z", "lead_time_hours": 18.5},
        ]
    )
    # Only 2 hourly actuals (hour 02:00 is missing from actuals)
    actuals = pd.DataFrame(
        [
            {"startTime": "2026-01-01T00:00:00Z", "settlementDate": "2026-01-01", "settlementPeriod": 1, "generation": 110.0},
            {"startTime": "2026-01-01T00:30:00Z", "settlementDate": "2026-01-01", "settlementPeriod": 2, "generation": 110.0},
            {"startTime": "2026-01-01T01:00:00Z", "settlementDate": "2026-01-01", "settlementPeriod": 3, "generation": 190.0},
            {"startTime": "2026-01-01T01:30:00Z", "settlementDate": "2026-01-01", "settlementPeriod": 4, "generation": 190.0},
        ]
    )

    matched, diag = match(forecasts, actuals, method="hourly_mean")

    # Only 2 rows matched
    assert len(matched) == 2
    assert diag["matched_count"] == 2
    assert diag["unmatched_forecasts_count"] == 1
    assert diag["unmatched_actuals_count"] == 0
    # Hour 02:00 is NOT present with zero actual
    assert "2026-01-01T02:00:00Z" not in matched["startTime"].astype(str).values
    assert not (matched["actual_generation"] == 0).any()


def test_deduplication():
    """Verify deduplication rules for forecasts and actuals."""
    # Duplicate forecast with different generations: last should be kept
    forecasts = pd.DataFrame(
        [
            {"publishTime": "2026-01-01T07:30:00Z", "startTime": "2026-01-02T12:00:00Z", "generation": 100.0},
            {"publishTime": "2026-01-01T07:30:00Z", "startTime": "2026-01-02T12:00:00Z", "generation": 200.0},
        ]
    )
    deduped_f = deduplicate_forecasts(forecasts)
    assert len(deduped_f) == 1
    assert deduped_f.iloc[0]["generation"] == 200.0

    # Duplicate actual with same settlement period: last should be kept
    actuals = pd.DataFrame(
        [
            {"settlementDate": "2026-01-01", "settlementPeriod": 1, "startTime": "2026-01-01T00:00:00Z", "generation": 500.0},
            {"settlementDate": "2026-01-01", "settlementPeriod": 1, "startTime": "2026-01-01T00:00:00Z", "generation": 550.0},
        ]
    )
    deduped_a = deduplicate_actuals(actuals)
    assert len(deduped_a) == 1
    assert deduped_a.iloc[0]["generation"] == 550.0


def test_actuals_aggregation_method_a_strictness():
    """Verify that Method A strictly requires both half-hours; drops incomplete hours."""
    actuals = pd.DataFrame(
        [
            # Hour 00:00 has both periods (1 and 2)
            {"startTime": "2026-01-01T00:00:00Z", "generation": 100.0},
            {"startTime": "2026-01-01T00:30:00Z", "generation": 200.0},
            # Hour 01:00 has only 1 period (missing 01:30)
            {"startTime": "2026-01-01T01:00:00Z", "generation": 300.0},
        ]
    )

    agg = aggregate_actuals(actuals, method="hourly_mean")

    assert len(agg) == 1
    assert agg.iloc[0]["startTime"] == pd.Timestamp("2026-01-01 00:00:00Z")
    assert agg.iloc[0]["generation"] == 150.0  # (100 + 200) / 2


def test_actuals_aggregation_method_b_point_match():
    """Verify that Method B point matches at :00."""
    actuals = pd.DataFrame(
        [
            {"startTime": "2026-01-01T00:00:00Z", "generation": 100.0},
            {"startTime": "2026-01-01T00:30:00Z", "generation": 200.0},
        ]
    )

    agg = aggregate_actuals(actuals, method="point_match")
    assert len(agg) == 1
    assert agg.iloc[0]["generation"] == 100.0


def test_get_forecast_fetch_window():
    """Verify that forecast window prepends buffer to cover delivery day."""
    p_from, p_to = get_forecast_fetch_window("2026-01-01", "2026-01-02", buffer_days=4)
    assert p_from == datetime(2025, 12, 28, 0, 0, 0, tzinfo=timezone.utc)
    assert p_to == datetime(2026, 1, 2, 23, 59, 59, tzinfo=timezone.utc)
