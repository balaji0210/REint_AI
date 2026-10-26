"""Unit tests for FastAPI REST endpoints using TestClient and mocked Elexon responses."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.elexon import ElexonHTTPError, ElexonTimeoutError

client = TestClient(app)

SAMPLE_ACTUALS = pd.DataFrame(
    [
        {
            "dataset": "FUELHH",
            "publishTime": pd.Timestamp("2026-01-01 00:30:00Z"),
            "startTime": pd.Timestamp("2026-01-01 00:00:00Z"),
            "settlementDate": "2026-01-01",
            "settlementPeriod": 1,
            "fuelType": "WIND",
            "generation": 100.0,
        },
        {
            "dataset": "FUELHH",
            "publishTime": pd.Timestamp("2026-01-01 01:00:00Z"),
            "startTime": pd.Timestamp("2026-01-01 00:30:00Z"),
            "settlementDate": "2026-01-01",
            "settlementPeriod": 2,
            "fuelType": "WIND",
            "generation": 140.0,
        },
        {
            "dataset": "FUELHH",
            "publishTime": pd.Timestamp("2026-01-01 01:30:00Z"),
            "startTime": pd.Timestamp("2026-01-01 01:00:00Z"),
            "settlementDate": "2026-01-01",
            "settlementPeriod": 3,
            "fuelType": "WIND",
            "generation": 180.0,
        },
        {
            "dataset": "FUELHH",
            "publishTime": pd.Timestamp("2026-01-01 02:00:00Z"),
            "startTime": pd.Timestamp("2026-01-01 01:30:00Z"),
            "settlementDate": "2026-01-01",
            "settlementPeriod": 4,
            "fuelType": "WIND",
            "generation": 180.0,
        },
    ]
)

SAMPLE_FORECASTS = pd.DataFrame(
    [
        {
            "dataset": "WINDFOR",
            "publishTime": pd.Timestamp("2025-12-31 07:30:00Z"),
            "startTime": pd.Timestamp("2026-01-01 00:00:00Z"),
            "generation": 100.0,
        },
        {
            "dataset": "WINDFOR",
            "publishTime": pd.Timestamp("2025-12-31 07:30:00Z"),
            "startTime": pd.Timestamp("2026-01-01 01:00:00Z"),
            "generation": 200.0,
        },
        {
            "dataset": "WINDFOR",
            "publishTime": pd.Timestamp("2025-12-31 15:30:00Z"),  # After 09:00 cutoff
            "startTime": pd.Timestamp("2026-01-01 01:00:00Z"),
            "generation": 250.0,
        },
    ]
)


def test_root_endpoint():
    """Verify GET / returns root service information and healthy status."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "REint AI backend is running"
    assert data["status"] == "healthy"
    assert "/api/health" in data["endpoints"]


def test_health_endpoint():
    """Verify GET /api/health and GET /health."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "cache_dir" in data

    shortcut = client.get("/health")
    assert shortcut.status_code == 200
    assert shortcut.json()["status"] == "ok"


@patch("backend.main.get_cached_actuals", new_callable=AsyncMock)
def test_actuals_endpoint(mock_get_actuals):
    """Verify GET /api/actuals returns aggregated hourly records."""
    mock_get_actuals.return_value = SAMPLE_ACTUALS

    response = client.get("/api/actuals?start=2026-01-01&end=2026-01-01&method=hourly_mean")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    # Hour 00:00 is (100 + 140)/2 = 120.0
    assert data["data"][0]["generation"] == 120.0
    # Hour 01:00 is (180 + 180)/2 = 180.0
    assert data["data"][1]["generation"] == 180.0


@patch("backend.main.get_cached_forecasts", new_callable=AsyncMock)
def test_forecasts_endpoint(mock_get_forecasts):
    """Verify GET /api/forecasts returns forecasts matching the cutoff rule."""
    mock_get_forecasts.return_value = SAMPLE_FORECASTS

    response = client.get("/api/forecasts?start=2026-01-01&end=2026-01-01&cutoff_time=09:00")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    # The 15:30 forecast must be excluded; 01:00 must use 200.0 (from 07:30)
    assert data["data"][1]["generation"] == 200.0


@patch("backend.main.get_cached_actuals", new_callable=AsyncMock)
@patch("backend.main.get_cached_forecasts", new_callable=AsyncMock)
def test_comparison_endpoint(mock_get_forecasts, mock_get_actuals):
    """Verify GET /api/comparison pairs forecasts and actuals correctly."""
    mock_get_actuals.return_value = SAMPLE_ACTUALS
    mock_get_forecasts.return_value = SAMPLE_FORECASTS

    response = client.get("/api/comparison?start=2026-01-01&end=2026-01-01&cutoff_time=09:00")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    # Hour 0: F=100, A=120 -> error = -20, abs_error = 20
    assert data["data"][0]["forecast_generation"] == 100.0
    assert data["data"][0]["actual_generation"] == 120.0
    assert data["data"][0]["error"] == -20.0
    assert data["data"][0]["absolute_error"] == 20.0


@patch("backend.main.get_cached_actuals", new_callable=AsyncMock)
@patch("backend.main.get_cached_forecasts", new_callable=AsyncMock)
def test_accuracy_endpoint(mock_get_forecasts, mock_get_actuals):
    """Verify GET /api/accuracy computes required [100, 200] vs [120, 180] -> MAE=20, RMSE=20."""
    mock_get_actuals.return_value = SAMPLE_ACTUALS
    mock_get_forecasts.return_value = SAMPLE_FORECASTS

    response = client.get("/api/accuracy?start=2026-01-01&end=2026-01-01")
    assert response.status_code == 200
    data = response.json()
    assert data["n_matched"] == 2
    assert data["mae"] == 20.0
    assert data["rmse"] == 20.0
    assert data["mean_error"] == 0.0
    assert data["excluded_zero_actuals"] == 0


@patch("backend.main.get_cached_actuals", new_callable=AsyncMock)
@patch("backend.main.get_cached_forecasts", new_callable=AsyncMock)
def test_daily_accuracy_endpoint(mock_get_forecasts, mock_get_actuals):
    """Verify GET /api/daily-accuracy returns per-day records."""
    mock_get_actuals.return_value = SAMPLE_ACTUALS
    mock_get_forecasts.return_value = SAMPLE_FORECASTS

    response = client.get("/api/daily-accuracy?start=2026-01-01&end=2026-01-01")
    assert response.status_code == 200
    data = response.json()
    assert len(data["daily_metrics"]) == 1
    assert data["daily_metrics"][0]["date"] == "2026-01-01"
    assert data["daily_metrics"][0]["mae"] == 20.0
    assert data["overall"]["mae"] == 20.0


@patch("backend.main.get_cached_actuals", new_callable=AsyncMock)
@patch("backend.main.get_cached_forecasts", new_callable=AsyncMock)
def test_forecast_explorer_endpoint(mock_get_forecasts, mock_get_actuals):
    """Verify GET /api/forecast-explorer highlights selected forecast."""
    mock_get_actuals.return_value = SAMPLE_ACTUALS
    mock_get_forecasts.return_value = SAMPLE_FORECASTS

    response = client.get("/api/forecast-explorer?target=2026-01-01T01:00:00Z&cutoff_time=09:00")
    assert response.status_code == 200
    data = response.json()
    assert data["total_forecasts"] == 2
    assert data["selected_forecast"] == 200.0
    assert data["actual_generation"] == 180.0

    # Verify is_selected flag
    f0730 = next(f for f in data["forecasts"] if "07:30" in f["publishTime"])
    f1530 = next(f for f in data["forecasts"] if "15:30" in f["publishTime"])
    assert f0730["is_selected"] is True
    assert f0730["is_before_cutoff"] is True
    assert f1530["is_selected"] is False
    assert f1530["is_before_cutoff"] is False


def test_methodology_endpoint():
    """Verify GET /api/methodology returns rich documentation."""
    response = client.get("/api/methodology")
    assert response.status_code == 200
    data = response.json()
    assert "09:00 UTC on D-1" in data["decision_cutoff_rule"]["default_cutoff"]
    assert "hourly_mean" in data["aggregation_methods"]["method_a_primary"]["name"]
    assert "mae" in data["metric_definitions"]


def test_invalid_date_range_returns_400():
    """Verify that start date after end date returns 400 Bad Request."""
    response = client.get("/api/actuals?start=2026-01-10&end=2026-01-05")
    assert response.status_code == 400
    assert "cannot be after end date" in response.json()["detail"]


@patch("backend.services.elexon.ElexonClient.fetch_actuals", new_callable=AsyncMock)
def test_upstream_elexon_failure_returns_502(mock_fetch):
    """Verify that upstream Elexon failure returns HTTP 502 Bad Gateway with message."""
    mock_fetch.side_effect = ElexonTimeoutError("Connection timed out to BMRS")

    # Clear memory / force cache miss by testing a unique range
    response = client.get("/api/actuals?start=2026-03-01&end=2026-03-02")
    assert response.status_code == 502
    assert "Upstream Elexon BMRS API failure" in response.json()["detail"]
