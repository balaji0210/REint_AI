"""Client and data fetching services for Elexon BMRS API.

Provides async access to:
- FUELHH outturn generation (filtered for WIND)
- WINDFOR generation forecasts
"""

import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Union

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"


class ElexonError(Exception):
    """Base exception for all Elexon BMRS API errors."""
    pass


class ElexonTimeoutError(ElexonError):
    """Raised when an API request to Elexon times out."""
    pass


class ElexonHTTPError(ElexonError):
    """Raised when Elexon returns an unexpected HTTP error."""

    def __init__(self, status_code: int, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(f"Elexon API HTTP {status_code}: {message}")
        self.status_code = status_code
        self.details = details or {}


class ElexonDataError(ElexonError):
    """Raised when Elexon response data is malformed or invalid."""
    pass


def _format_utc_iso(dt: Union[datetime, str]) -> str:
    """Format a datetime as ISO 8601 UTC string with trailing 'Z'."""
    if isinstance(dt, str):
        # Validate or parse if needed
        dt_parsed = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        return dt_parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    elif isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    raise ValueError(f"Expected datetime or ISO string, got {type(dt)}")


def _format_date_str(d: Union[date, str]) -> str:
    """Format date to YYYY-MM-DD string."""
    if isinstance(d, str):
        return d
    elif isinstance(d, (date, datetime)):
        return d.strftime("%Y-%m-%d")
    raise ValueError(f"Expected date or string, got {type(d)}")


def _parse_date(d: Union[date, str]) -> date:
    """Parse date or YYYY-MM-DD string to date object."""
    if isinstance(d, datetime):
        return d.date()
    elif isinstance(d, date):
        return d
    elif isinstance(d, str):
        return datetime.strptime(d[:10], "%Y-%m-%d").date()
    raise ValueError(f"Expected date or date string, got {type(d)}")


def _parse_datetime(dt: Union[datetime, str]) -> datetime:
    """Parse datetime or ISO string to timezone-aware UTC datetime."""
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    elif isinstance(dt, str):
        dt_clean = dt.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(dt_clean)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    raise ValueError(f"Expected datetime or ISO string, got {type(dt)}")


class ElexonClient:
    """Async client for querying Elexon BMRS REST stream endpoints."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.transport = transport

    def _create_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=self.transport,
            headers={"Accept": "application/json"},
        )

    async def _request_with_retry(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        params: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Execute GET request with exponential backoff retry on 5xx and timeouts."""
        url = endpoint
        for attempt in range(1, self.max_retries + 1):
            try:
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    try:
                        data = response.json()
                        if isinstance(data, list):
                            return data
                        elif isinstance(data, dict) and "data" in data:
                            return data["data"]
                        raise ElexonDataError(f"Unexpected JSON structure from {endpoint}")
                    except ValueError as json_err:
                        raise ElexonDataError(f"Failed to parse JSON from {endpoint}: {json_err}")

                elif 500 <= response.status_code < 600:
                    logger.warning(
                        f"Attempt {attempt}/{self.max_retries}: Server error {response.status_code} "
                        f"for {endpoint}. Retrying..."
                    )
                    if attempt == self.max_retries:
                        raise ElexonHTTPError(response.status_code, response.text)
                elif response.status_code == 400:
                    # Client error, do not retry
                    raise ElexonHTTPError(400, response.text)
                elif response.status_code == 404:
                    raise ElexonHTTPError(404, f"Resource not found: {endpoint}")
                else:
                    raise ElexonHTTPError(response.status_code, response.text)

            except httpx.TimeoutException as timeout_err:
                logger.warning(f"Attempt {attempt}/{self.max_retries}: Timeout requesting {endpoint}.")
                if attempt == self.max_retries:
                    raise ElexonTimeoutError(f"Request to {endpoint} timed out after {self.max_retries} attempts.") from timeout_err
            except httpx.NetworkError as net_err:
                logger.warning(f"Attempt {attempt}/{self.max_retries}: Network error requesting {endpoint}: {net_err}")
                if attempt == self.max_retries:
                    raise ElexonError(f"Network error communicating with {endpoint}: {net_err}") from net_err

            # Exponential backoff
            await asyncio.sleep(self.backoff_factor * (2 ** (attempt - 1)))

        raise ElexonError(f"Failed to fetch data from {endpoint} after {self.max_retries} attempts.")

    async def fetch_actuals(
        self,
        start_date: Union[date, str],
        end_date: Union[date, str],
        chunk_days: int = 14,
    ) -> pd.DataFrame:
        """Fetch FUELHH actual generation records for WIND only between start_date and end_date.

        Uses settlementDateFrom and settlementDateTo to ensure period 48 is included.
        Chunks date ranges into intervals of at most chunk_days.
        All timestamps are parsed to timezone-aware UTC.
        """
        parsed_start = _parse_date(start_date)
        parsed_end = _parse_date(end_date)

        if parsed_start > parsed_end:
            raise ValueError(f"start_date ({parsed_start}) cannot be after end_date ({parsed_end})")

        all_records: List[Dict[str, Any]] = []

        async with self._create_client() as client:
            current_start = parsed_start
            while current_start <= parsed_end:
                current_end = min(current_start + timedelta(days=chunk_days - 1), parsed_end)
                params = {
                    "settlementDateFrom": _format_date_str(current_start),
                    "settlementDateTo": _format_date_str(current_end),
                    "fuelType": "WIND",
                }

                chunk_records = await self._request_with_retry(
                    client=client,
                    endpoint="/datasets/FUELHH/stream",
                    params=params,
                )

                # Defensive client-side check to guarantee WIND-only
                wind_only = [r for r in chunk_records if r.get("fuelType") == "WIND"]
                all_records.extend(wind_only)

                current_start = current_end + timedelta(days=1)

        if not all_records:
            return pd.DataFrame(
                columns=[
                    "dataset",
                    "publishTime",
                    "startTime",
                    "settlementDate",
                    "settlementPeriod",
                    "fuelType",
                    "generation",
                ]
            )

        df = pd.DataFrame(all_records)

        # Parse timestamps to timezone-aware UTC
        df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)
        df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
        df["settlementPeriod"] = df["settlementPeriod"].astype(int)
        df["generation"] = pd.to_numeric(df["generation"], errors="coerce")

        return df

    async def fetch_forecasts(
        self,
        publish_from: Union[datetime, str],
        publish_to: Union[datetime, str],
        chunk_days: int = 14,
    ) -> pd.DataFrame:
        """Fetch WINDFOR forecast records with publishTime between publish_from and publish_to.

        Uses publishDateTimeFrom and publishDateTimeTo formatted as ISO 8601 UTC.
        Chunks date ranges into intervals of at most chunk_days.
        All timestamps are parsed to timezone-aware UTC.
        """
        dt_from = _parse_datetime(publish_from)
        dt_to = _parse_datetime(publish_to)

        if dt_from > dt_to:
            raise ValueError(f"publish_from ({dt_from}) cannot be after publish_to ({dt_to})")

        all_records: List[Dict[str, Any]] = []

        async with self._create_client() as client:
            current_from = dt_from
            while current_from <= dt_to:
                current_to = min(current_from + timedelta(days=chunk_days), dt_to)
                params = {
                    "publishDateTimeFrom": _format_utc_iso(current_from),
                    "publishDateTimeTo": _format_utc_iso(current_to),
                }

                chunk_records = await self._request_with_retry(
                    client=client,
                    endpoint="/datasets/WINDFOR/stream",
                    params=params,
                )
                all_records.extend(chunk_records)

                # Move to next chunk (avoiding overlapping endpoint second)
                current_from = current_to + timedelta(seconds=1)

        if not all_records:
            return pd.DataFrame(columns=["dataset", "publishTime", "startTime", "generation"])

        df = pd.DataFrame(all_records)

        # Parse timestamps to timezone-aware UTC
        df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)
        df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
        df["generation"] = pd.to_numeric(df["generation"], errors="coerce")

        return df
