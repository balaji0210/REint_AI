"""FastAPI application entry point for the UK Wind Power Forecasting Dashboard.

Provides REST endpoints for:
- Health check
- Actual wind generation (FUELHH)
- Day-ahead wind forecasts (WINDFOR)
- Selected forecast vs actual comparison
- Overall accuracy metrics
- Daily accuracy breakdowns for charts
- Single interval forecast explorer
- Methodology and rule documentation
"""

from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta, timezone
import os
from pathlib import Path
import sys
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
import numpy as np
import pandas as pd

# Ensure current directory and parent directory are on sys.path
# so imports work whether invoked from root (uvicorn backend.main:app)
# or directly inside the backend directory (e.g. Vercel serverless deployment)
CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent
for p in (str(CURRENT_DIR), str(PARENT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from backend.models import (
        AccuracyResponse,
        ActualRecord,
        ActualsResponse,
        ComparisonRecord,
        ComparisonResponse,
        DailyAccuracyRecord,
        DailyAccuracyResponse,
        ForecastExplorerItem,
        ForecastExplorerResponse,
        ForecastRecord,
        ForecastsResponse,
        HealthResponse,
        MethodologyResponse,
    )
    from backend.services.cache import FileCache
    from backend.services.elexon import ElexonClient, ElexonError
    from backend.services.forecast import (
        DEFAULT_CUTOFF_TIME,
        DEFAULT_DAYS_BEFORE,
        aggregate_actuals,
        get_forecast_fetch_window,
        match,
        select_forecasts,
    )
    from backend.services.metrics import calculate_metrics, compute_interval_errors
except (ImportError, ModuleNotFoundError):
    from models import (
        AccuracyResponse,
        ActualRecord,
        ActualsResponse,
        ComparisonRecord,
        ComparisonResponse,
        DailyAccuracyRecord,
        DailyAccuracyResponse,
        ForecastExplorerItem,
        ForecastExplorerResponse,
        ForecastRecord,
        ForecastsResponse,
        HealthResponse,
        MethodologyResponse,
    )
    from services.cache import FileCache
    from services.elexon import ElexonClient, ElexonError
    from services.forecast import (
        DEFAULT_CUTOFF_TIME,
        DEFAULT_DAYS_BEFORE,
        aggregate_actuals,
        get_forecast_fetch_window,
        match,
        select_forecasts,
    )
    from services.metrics import calculate_metrics, compute_interval_errors

# Initialize cache and Elexon client
file_cache = FileCache()
elexon_client = ElexonClient()

app = FastAPI(
    title="UK Wind Power Forecasting & Accuracy API",
    description="Operational day-ahead wind power purchasing and forecasting analytics for Great Britain.",
    version="1.0.0",
)

# CORS configuration
raw_cors = os.environ.get("CORS_ORIGINS", "*")
if raw_cors == "*" or not raw_cors:
    origins = [
        "https://r-eint-ai-m3z1.vercel.app",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]
    # Allow any Vercel domain (previews, production) and local development ports
    origin_regex = r"^https:\/\/.*\.vercel\.app$|^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$"
else:
    origins = [orig.strip() for orig in raw_cors.split(",") if orig.strip()]
    origin_regex = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def fix_vercel_path_routing(request: Request, call_next):
    """Restore original client request path from Vercel rewrite proxy headers."""
    matched_path = (
        request.headers.get("x-matched-path")
        or request.headers.get("x-vercel-matched-path")
        or request.headers.get("x-invoke-path")
        or request.headers.get("x-forwarded-uri")
        or request.headers.get("x-original-uri")
        or request.headers.get("x-rewrite-url")
    )
    if matched_path:
        clean_path = matched_path.split("?")[0]
        if request.scope.get("path") in ("/api/index.py", "/api/index", "/main.py", "/index.py", "/api"):
            request.scope["path"] = clean_path
    elif request.scope.get("path") in ("/api/index.py", "/api/index", "/main.py", "/index.py"):
        request.scope["path"] = "/"

    return await call_next(request)


@app.get("/")
@app.get("/api/index.py")
@app.get("/api/index")
@app.get("/main.py")
def home():
    """Root verification endpoint confirming backend status and route catalog."""
    return {
        "message": "REint AI backend is running",
        "status": "healthy",
        "service": "UK Wind Power Forecasting & Accuracy API",
        "docs_url": "/docs",
        "health_check": "/api/health",
        "endpoints": [
            "/api/health",
            "/api/comparison",
            "/api/accuracy",
            "/api/daily-accuracy",
            "/api/actuals",
            "/api/forecasts",
            "/api/forecast-explorer",
            "/api/methodology",
        ],
    }


@app.get("/health", response_model=HealthResponse)
async def health_shortcut():
    """Top-level health check shortcut."""
    return await health_check()


def parse_cutoff_time(cutoff_str: str) -> time:
    """Parse 'HH:MM' string to time object."""
    try:
        parts = cutoff_str.strip().split(":")
        return time(int(parts[0]), int(parts[1]))
    except Exception:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid cutoff_time format: '{cutoff_str}'. Expected 'HH:MM' (e.g. '09:00').",
        )


def validate_date_range(start: date, end: date):
    """Validate that start date is not after end date."""
    if start > end:
        raise HTTPException(
            status_code=400,
            detail=f"Start date ({start}) cannot be after end date ({end}).",
        )


async def get_cached_actuals(start: date, end: date) -> pd.DataFrame:
    """Fetch FUELHH actuals from cache or upstream Elexon API."""
    cache_key = f"actuals_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}"
    cached_df = file_cache.get(cache_key)
    if cached_df is not None:
        return cached_df

    try:
        df = await elexon_client.fetch_actuals(start, end)
        file_cache.set(cache_key, df)
        return df
    except ElexonError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream Elexon BMRS API failure while fetching actuals: {str(e)}",
        )


async def get_cached_forecasts(publish_from: datetime, publish_to: datetime) -> pd.DataFrame:
    """Fetch WINDFOR forecasts from cache or upstream Elexon API."""
    cache_key = f"forecasts_{publish_from.strftime('%Y%m%d%H%M')}_{publish_to.strftime('%Y%m%d%H%M')}"
    cached_df = file_cache.get(cache_key)
    if cached_df is not None:
        return cached_df

    try:
        df = await elexon_client.fetch_forecasts(publish_from, publish_to)
        file_cache.set(cache_key, df)
        return df
    except ElexonError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream Elexon BMRS API failure while fetching forecasts: {str(e)}",
        )


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint with cache diagnostics."""
    cached_files = []
    for d in file_cache.candidate_dirs:
        if d.exists():
            cached_files.extend(list(d.glob("*.json")))
    unique_file_names = {f.name for f in cached_files}
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc),
        cache_dir=str(file_cache.cache_dir),
        cached_files_count=len(unique_file_names),
    )


@app.get("/api/actuals", response_model=ActualsResponse)
async def get_actuals(
    start: date = Query(default=date(2026, 1, 1), description="Start date (YYYY-MM-DD)"),
    end: date = Query(default=date(2026, 1, 31), description="End date (YYYY-MM-DD)"),
    method: str = Query(
        default="hourly_mean",
        pattern="^(hourly_mean|point_match)$",
        description="Hourly aggregation method: 'hourly_mean' (Method A) or 'point_match' (Method B)",
    ),
):
    """Retrieve outturn wind generation (FUELHH) aggregated to hourly resolution."""
    validate_date_range(start, end)
    df_raw = await get_cached_actuals(start, end)
    if df_raw.empty:
        return ActualsResponse(
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            aggregation_method=method,
            count=0,
            data=[],
        )

    df_agg = aggregate_actuals(df_raw, method=method)
    records = [
        ActualRecord(
            startTime=row["startTime"].to_pydatetime(),
            generation=float(row["generation"]),
        )
        for _, row in df_agg.iterrows()
    ]

    return ActualsResponse(
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        aggregation_method=method,
        count=len(records),
        data=records,
    )


@app.get("/api/forecasts", response_model=ForecastsResponse)
async def get_forecasts(
    start: date = Query(default=date(2026, 1, 1), description="Delivery start date (YYYY-MM-DD)"),
    end: date = Query(default=date(2026, 1, 31), description="Delivery end date (YYYY-MM-DD)"),
    cutoff_time: str = Query(default="09:00", description="Cutoff time (HH:MM UTC on D-1)"),
    cutoff_days_before: int = Query(default=1, ge=0, le=7, description="Cutoff days before delivery"),
):
    """Retrieve selected Day-Ahead forecasts under the configured cutoff rule."""
    validate_date_range(start, end)
    cutoff_t = parse_cutoff_time(cutoff_time)

    pub_from, pub_to = get_forecast_fetch_window(start, end)
    df_forecasts = await get_cached_forecasts(pub_from, pub_to)

    selected = select_forecasts(df_forecasts, cutoff_time=cutoff_t, days_before=cutoff_days_before)

    # Filter to requested delivery date window
    start_ts = pd.Timestamp(start).tz_localize("UTC")
    end_ts = pd.Timestamp(end).tz_localize("UTC") + pd.Timedelta(days=1)
    mask = (selected["startTime"] >= start_ts) & (selected["startTime"] < end_ts)
    filtered = selected[mask].sort_values("startTime")

    records = [
        ForecastRecord(
            startTime=row["startTime"].to_pydatetime(),
            publishTime=row["publishTime"].to_pydatetime(),
            generation=float(row["generation"]),
            cutoff_time=row["cutoff_time"].to_pydatetime() if pd.notnull(row["cutoff_time"]) else None,
            lead_time_hours=float(row["lead_time_hours"]) if pd.notnull(row["lead_time_hours"]) else None,
        )
        for _, row in filtered.iterrows()
    ]

    return ForecastsResponse(
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        cutoff_time=cutoff_time,
        cutoff_days_before=cutoff_days_before,
        count=len(records),
        data=records,
    )


@app.get("/api/comparison", response_model=ComparisonResponse)
async def get_comparison(
    start: date = Query(default=date(2026, 1, 1), description="Start date (YYYY-MM-DD)"),
    end: date = Query(default=date(2026, 1, 31), description="End date (YYYY-MM-DD)"),
    cutoff_time: str = Query(default="09:00", description="Cutoff time (HH:MM UTC on D-1)"),
    cutoff_days_before: int = Query(default=1, ge=0, le=7, description="Cutoff days before delivery"),
    method: str = Query(default="hourly_mean", pattern="^(hourly_mean|point_match)$"),
):
    """Retrieve paired day-ahead forecast vs actual generation, error (F - A), and lead time."""
    validate_date_range(start, end)
    cutoff_t = parse_cutoff_time(cutoff_time)

    pub_from, pub_to = get_forecast_fetch_window(start, end)
    df_raw_forecasts = await get_cached_forecasts(pub_from, pub_to)
    df_raw_actuals = await get_cached_actuals(start, end)

    selected_f = select_forecasts(df_raw_forecasts, cutoff_time=cutoff_t, days_before=cutoff_days_before)
    matched_df, _ = match(selected_f, df_raw_actuals, method=method)

    if matched_df.empty:
        return ComparisonResponse(
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            cutoff_time=cutoff_time,
            cutoff_days_before=cutoff_days_before,
            count=0,
            data=[],
        )

    # Filter strictly to delivery range
    start_ts = pd.Timestamp(start).tz_localize("UTC")
    end_ts = pd.Timestamp(end).tz_localize("UTC") + pd.Timedelta(days=1)
    matched_df = matched_df[
        (matched_df["startTime"] >= start_ts) & (matched_df["startTime"] < end_ts)
    ].copy()

    df_err = compute_interval_errors(matched_df)

    records = [
        ComparisonRecord(
            startTime=row["startTime"].to_pydatetime(),
            forecast_generation=float(row["forecast_generation"]),
            actual_generation=float(row["actual_generation"]),
            error=round(float(row["error"]), 2),
            absolute_error=round(float(row["abs_error"]), 2),
            publishTime=row["publishTime"].to_pydatetime(),
            cutoff_time=row["cutoff_time"].to_pydatetime(),
            lead_time_hours=round(float(row["lead_time_hours"]), 2),
        )
        for _, row in df_err.iterrows()
    ]

    return ComparisonResponse(
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        cutoff_time=cutoff_time,
        cutoff_days_before=cutoff_days_before,
        count=len(records),
        data=records,
    )


@app.get("/api/accuracy", response_model=AccuracyResponse)
async def get_accuracy(
    start: date = Query(default=date(2026, 1, 1), description="Start date (YYYY-MM-DD)"),
    end: date = Query(default=date(2026, 1, 31), description="End date (YYYY-MM-DD)"),
    cutoff_time: str = Query(default="09:00", description="Cutoff time (HH:MM UTC on D-1)"),
    cutoff_days_before: int = Query(default=1, ge=0, le=7, description="Cutoff days before delivery"),
    method: str = Query(default="hourly_mean", pattern="^(hourly_mean|point_match)$"),
):
    """Calculate overall accuracy metrics (MAE, RMSE, ME, MAPE, WAPE, N, exclusions)."""
    validate_date_range(start, end)
    cutoff_t = parse_cutoff_time(cutoff_time)

    pub_from, pub_to = get_forecast_fetch_window(start, end)
    df_raw_forecasts = await get_cached_forecasts(pub_from, pub_to)
    df_raw_actuals = await get_cached_actuals(start, end)

    selected_f = select_forecasts(df_raw_forecasts, cutoff_time=cutoff_t, days_before=cutoff_days_before)
    matched_df, diag = match(selected_f, df_raw_actuals, method=method)

    # Filter strictly to delivery range
    start_ts = pd.Timestamp(start).tz_localize("UTC")
    end_ts = pd.Timestamp(end).tz_localize("UTC") + pd.Timedelta(days=1)
    if not matched_df.empty:
        matched_df = matched_df[
            (matched_df["startTime"] >= start_ts) & (matched_df["startTime"] < end_ts)
        ].copy()

    metrics = calculate_metrics(matched_df)

    return AccuracyResponse(
        n_matched=metrics["n_matched"],
        mae=metrics["mae"],
        rmse=metrics["rmse"],
        mean_error=metrics["mean_error"],
        mape=metrics["mape"],
        wape=metrics["wape"],
        excluded_zero_actuals=metrics["excluded_zero_actuals"],
        unmatched_actuals=diag["unmatched_actuals_count"],
        unmatched_forecasts=diag["unmatched_forecasts_count"],
        cutoff_time=cutoff_time,
        cutoff_days_before=cutoff_days_before,
        method=method,
    )


@app.get("/api/daily-accuracy", response_model=DailyAccuracyResponse)
async def get_daily_accuracy(
    start: date = Query(default=date(2026, 1, 1), description="Start date (YYYY-MM-DD)"),
    end: date = Query(default=date(2026, 1, 31), description="End date (YYYY-MM-DD)"),
    cutoff_time: str = Query(default="09:00", description="Cutoff time (HH:MM UTC on D-1)"),
    cutoff_days_before: int = Query(default=1, ge=0, le=7, description="Cutoff days before delivery"),
    method: str = Query(default="hourly_mean", pattern="^(hourly_mean|point_match)$"),
):
    """Retrieve per-day accuracy metrics for trend charting and daily performance evaluation."""
    validate_date_range(start, end)
    cutoff_t = parse_cutoff_time(cutoff_time)

    pub_from, pub_to = get_forecast_fetch_window(start, end)
    df_raw_forecasts = await get_cached_forecasts(pub_from, pub_to)
    df_raw_actuals = await get_cached_actuals(start, end)

    selected_f = select_forecasts(df_raw_forecasts, cutoff_time=cutoff_t, days_before=cutoff_days_before)
    matched_df, diag = match(selected_f, df_raw_actuals, method=method)

    # Filter strictly to delivery range
    start_ts = pd.Timestamp(start).tz_localize("UTC")
    end_ts = pd.Timestamp(end).tz_localize("UTC") + pd.Timedelta(days=1)
    if not matched_df.empty:
        matched_df = matched_df[
            (matched_df["startTime"] >= start_ts) & (matched_df["startTime"] < end_ts)
        ].copy()

    overall_metrics = calculate_metrics(matched_df)
    overall_response = AccuracyResponse(
        n_matched=overall_metrics["n_matched"],
        mae=overall_metrics["mae"],
        rmse=overall_metrics["rmse"],
        mean_error=overall_metrics["mean_error"],
        mape=overall_metrics["mape"],
        wape=overall_metrics["wape"],
        excluded_zero_actuals=overall_metrics["excluded_zero_actuals"],
        unmatched_actuals=diag["unmatched_actuals_count"],
        unmatched_forecasts=diag["unmatched_forecasts_count"],
        cutoff_time=cutoff_time,
        cutoff_days_before=cutoff_days_before,
        method=method,
    )

    daily_records: List[DailyAccuracyRecord] = []
    if not matched_df.empty:
        matched_df["date_str"] = matched_df["startTime"].dt.strftime("%Y-%m-%d")
        for date_str, group in matched_df.groupby("date_str"):
            day_m = calculate_metrics(group)
            daily_records.append(
                DailyAccuracyRecord(
                    date=date_str,
                    n_matched=day_m["n_matched"],
                    mae=day_m["mae"],
                    rmse=day_m["rmse"],
                    mean_error=day_m["mean_error"],
                    mape=day_m["mape"],
                    wape=day_m["wape"],
                )
            )

    return DailyAccuracyResponse(
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        cutoff_time=cutoff_time,
        cutoff_days_before=cutoff_days_before,
        daily_metrics=daily_records,
        overall=overall_response,
    )


@app.get("/api/forecast-explorer", response_model=ForecastExplorerResponse)
async def get_forecast_explorer(
    target: str = Query(
        ...,
        description="Target delivery ISO datetime (e.g. '2026-01-01T12:00:00Z')",
    ),
    cutoff_time: str = Query(default="09:00", description="Cutoff time (HH:MM UTC on D-1)"),
    cutoff_days_before: int = Query(default=1, ge=0, le=7, description="Cutoff days before delivery"),
):
    """Explore all forecasts published for a single delivery interval and see which was selected."""
    try:
        clean_target = target.replace("Z", "+00:00")
        target_dt = datetime.fromisoformat(clean_target)
        if target_dt.tzinfo is None:
            target_dt = target_dt.replace(tzinfo=timezone.utc)
        else:
            target_dt = target_dt.astimezone(timezone.utc)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid target ISO datetime: '{target}'. Expected e.g. '2026-01-01T12:00:00Z'.",
        )

    cutoff_t = parse_cutoff_time(cutoff_time)
    delivery_date = target_dt.date()
    cutoff_dt = datetime.combine(
        delivery_date - timedelta(days=cutoff_days_before),
        cutoff_t,
        tzinfo=timezone.utc,
    )

    # Fetch forecasts with buffer around target date
    pub_from = target_dt - timedelta(days=5)
    pub_to = target_dt + timedelta(days=1)
    df_raw_forecasts = await get_cached_forecasts(pub_from, pub_to)

    target_ts = pd.Timestamp(target_dt)
    target_forecasts = df_raw_forecasts[df_raw_forecasts["startTime"] == target_ts].copy()

    if target_forecasts.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No forecasts found for target interval {target_dt.isoformat()}.",
        )

    # Sort chronologically by publishTime
    target_forecasts = target_forecasts.sort_values("publishTime").reset_index(drop=True)

    # Determine which forecast is selected by the cutoff rule
    valid_candidates = target_forecasts[
        (target_forecasts["publishTime"] <= pd.Timestamp(cutoff_dt))
        & (target_forecasts["publishTime"] < target_ts)
    ]

    selected_publish_time = None
    selected_gen = None
    if not valid_candidates.empty:
        best_row = valid_candidates.loc[valid_candidates["publishTime"].idxmax()]
        selected_publish_time = best_row["publishTime"]
        selected_gen = float(best_row["generation"])

    items = []
    for _, row in target_forecasts.iterrows():
        pt = row["publishTime"]
        lead = round((target_ts - pt).total_seconds() / 3600.0, 2)
        is_before = pt <= pd.Timestamp(cutoff_dt)
        is_sel = pt == selected_publish_time

        items.append(
            ForecastExplorerItem(
                publishTime=pt.to_pydatetime(),
                generation=float(row["generation"]),
                lead_time_hours=lead,
                is_selected=is_sel,
                is_before_cutoff=is_before,
            )
        )

    # Fetch actual if available
    actual_val = None
    try:
        df_actuals = await get_cached_actuals(delivery_date, delivery_date)
        if not df_actuals.empty:
            df_agg = aggregate_actuals(df_actuals, method="hourly_mean")
            match_act = df_agg[df_agg["startTime"] == target_ts]
            if not match_act.empty:
                actual_val = float(match_act.iloc[0]["generation"])
    except Exception:
        actual_val = None

    return ForecastExplorerResponse(
        target_startTime=target_dt,
        actual_generation=actual_val,
        selected_forecast=selected_gen,
        cutoff_time=cutoff_dt,
        total_forecasts=len(items),
        forecasts=items,
    )


@app.get("/api/methodology", response_model=MethodologyResponse)
async def get_methodology():
    """Retrieve full documentation on the decision cutoff rule, aggregation methods, and error metrics."""
    return MethodologyResponse(
        decision_cutoff_rule={
            "default_cutoff": "09:00 UTC on D-1",
            "justification": (
                "In the Great Britain electricity market, EPEX SPOT GB Day-Ahead auction order books close at "
                "09:20 UK local time (N2EX closes at 09:50/11:00). A purchasing team must lock physical wind "
                "positions by 09:00 UTC on D-1 (GMT in January) to determine net trade requirements prior to gate closure."
            ),
            "selection_logic": (
                "For each delivery hour t on day D, select the latest forecast published at or before T_cutoff. "
                "Forecasts published after cutoff are strictly excluded. Retrospective records (lead time <= 0) "
                "are eliminated."
            ),
            "lead_time_definition": "Lead time = (startTime - publishTime) in hours. Under 09:00 D-1 cutoff, lead times range from 15h to 38h.",
        },
        aggregation_methods={
            "method_a_primary": {
                "name": "hourly_mean",
                "description": "Mean of the two 30-minute settlement periods (2k-1 and 2k) comprising the hour.",
                "validation": "Strictly requires both half-hour intervals to be present and non-null; otherwise the hour is omitted.",
            },
            "method_b_check": {
                "name": "point_match",
                "description": "Uses the single outturn record starting at :00 without aggregation.",
            },
        },
        metric_definitions={
            "mae": "Mean Absolute Error: (1/N) * sum(|Forecast - Actual|) in MW.",
            "rmse": "Root Mean Squared Error: sqrt((1/N) * sum((Forecast - Actual)^2)) in MW. Penalizes large errors.",
            "mean_error_bias": "Mean Error: (1/N) * sum(Forecast - Actual) in MW. Positive indicates over-forecasting.",
            "mape": "Mean Absolute Percentage Error (%): strictly excludes intervals where Actual == 0 to prevent division by zero.",
            "wape": "Weighted Absolute Percentage Error (%): sum(|Forecast - Actual|) / sum(Actual) * 100.",
        },
        data_coverage={
            "analysis_window": "2026-01-01 to 2026-01-31 (full month of January 2026)",
            "january_boundary_handling": (
                "WINDFOR has a ~66.5h maximum forecast horizon. Forecasts for 2026-01-01 delivery are published "
                "beginning in late December 2025. The backend automatically fetches from 2025-12-28 onward."
            ),
            "caching": "All raw API responses are persisted to data/cache with a 24-hour TTL.",
        },
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=False)

