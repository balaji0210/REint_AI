"""Unit tests for Elexon async client, retry logic, and filtering."""

import asyncio
from datetime import date, timezone
import httpx
import pytest

from backend.services.elexon import (
    ElexonClient,
    ElexonError,
    ElexonHTTPError,
    ElexonTimeoutError,
)


def test_fetch_actuals_filters_wind_only():
    """Verify that only fuelType == 'WIND' records are retained, and timestamps are UTC."""
    raw_response = [
        {
            "dataset": "FUELHH",
            "publishTime": "2026-01-01T00:30:00Z",
            "startTime": "2026-01-01T00:00:00Z",
            "settlementDate": "2026-01-01",
            "settlementPeriod": 1,
            "fuelType": "CCGT",
            "generation": 5000,
        },
        {
            "dataset": "FUELHH",
            "publishTime": "2026-01-01T00:30:00Z",
            "startTime": "2026-01-01T00:00:00Z",
            "settlementDate": "2026-01-01",
            "settlementPeriod": 1,
            "fuelType": "WIND",
            "generation": 12500,
        },
        {
            "dataset": "FUELHH",
            "publishTime": "2026-01-01T00:30:00Z",
            "startTime": "2026-01-01T00:00:00Z",
            "settlementDate": "2026-01-01",
            "settlementPeriod": 1,
            "fuelType": "NUCLEAR",
            "generation": 6000,
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=raw_response)

    transport = httpx.MockTransport(handler)
    client = ElexonClient(transport=transport)

    df = asyncio.run(client.fetch_actuals(date(2026, 1, 1), date(2026, 1, 1)))

    assert len(df) == 1
    assert df.iloc[0]["fuelType"] == "WIND"
    assert df.iloc[0]["generation"] == 12500
    # Timezone check
    assert df["startTime"].dt.tz == timezone.utc
    assert df["publishTime"].dt.tz == timezone.utc


def test_fetch_forecasts_utc_timestamps():
    """Verify that WINDFOR forecasts are parsed into UTC timestamps."""
    raw_response = [
        {
            "dataset": "WINDFOR",
            "publishTime": "2025-12-31T07:30:00Z",
            "startTime": "2026-01-01T12:00:00Z",
            "generation": 14000,
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=raw_response)

    transport = httpx.MockTransport(handler)
    client = ElexonClient(transport=transport)

    df = asyncio.run(client.fetch_forecasts("2025-12-31T00:00:00Z", "2025-12-31T23:59:59Z"))

    assert len(df) == 1
    assert df.iloc[0]["generation"] == 14000
    assert df["startTime"].dt.tz == timezone.utc
    assert df["publishTime"].dt.tz == timezone.utc


def test_retry_on_500_server_error():
    """Verify that client retries on 500 and succeeds when server recovers."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(500, text="Internal Server Error")
        return httpx.Response(
            200,
            json=[
                {
                    "fuelType": "WIND",
                    "generation": 1000,
                    "startTime": "2026-01-01T00:00:00Z",
                    "publishTime": "2026-01-01T00:30:00Z",
                    "settlementDate": "2026-01-01",
                    "settlementPeriod": 1,
                }
            ],
        )

    transport = httpx.MockTransport(handler)
    client = ElexonClient(transport=transport, max_retries=3, backoff_factor=0.01)

    df = asyncio.run(client.fetch_actuals(date(2026, 1, 1), date(2026, 1, 1)))

    assert attempts == 3
    assert len(df) == 1
    assert df.iloc[0]["generation"] == 1000


def test_timeout_raises_custom_exception():
    """Verify that timeout raises ElexonTimeoutError."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Request timed out", request=request)

    transport = httpx.MockTransport(handler)
    client = ElexonClient(transport=transport, max_retries=2, backoff_factor=0.01)

    with pytest.raises(ElexonTimeoutError):
        asyncio.run(client.fetch_actuals(date(2026, 1, 1), date(2026, 1, 1)))


def test_400_raises_elexon_http_error_without_retry():
    """Verify that HTTP 400 immediately raises ElexonHTTPError without useless retries."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(400, text="Validation Error: Invalid date format")

    transport = httpx.MockTransport(handler)
    client = ElexonClient(transport=transport, max_retries=3, backoff_factor=0.01)

    with pytest.raises(ElexonHTTPError) as exc_info:
        asyncio.run(client.fetch_actuals(date(2026, 1, 1), date(2026, 1, 1)))

    assert attempts == 1  # Did not retry on 400
    assert exc_info.value.status_code == 400


def test_chunking_across_dates():
    """Verify that date ranges exceeding chunk_days are split into multiple requests."""
    requested_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    client = ElexonClient(transport=transport)

    # 10 days total with chunk_days=3 -> 4 chunks: [1-3, 4-6, 7-9, 10-10]
    asyncio.run(client.fetch_actuals(date(2026, 1, 1), date(2026, 1, 10), chunk_days=3))

    assert len(requested_urls) == 4
    assert "settlementDateFrom=2026-01-01&settlementDateTo=2026-01-03" in requested_urls[0]
    assert "settlementDateFrom=2026-01-04&settlementDateTo=2026-01-06" in requested_urls[1]
    assert "settlementDateFrom=2026-01-07&settlementDateTo=2026-01-09" in requested_urls[2]
    assert "settlementDateFrom=2026-01-10&settlementDateTo=2026-01-10" in requested_urls[3]
