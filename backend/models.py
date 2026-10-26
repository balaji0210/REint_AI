"""Pydantic schemas and response models for the wind forecast API."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    timestamp: datetime
    cache_dir: str
    cached_files_count: int


class ActualRecord(BaseModel):
    startTime: datetime = Field(..., description="Target hour or settlement period start (UTC)")
    generation: float = Field(..., description="Outturn generation in MW")
    settlementDate: Optional[str] = Field(None, description="Settlement calendar date (YYYY-MM-DD)")
    settlementPeriod: Optional[int] = Field(None, description="Half-hour settlement period (1-48)")


class ActualsResponse(BaseModel):
    start_date: str
    end_date: str
    aggregation_method: str
    count: int
    data: List[ActualRecord]


class ForecastRecord(BaseModel):
    startTime: datetime = Field(..., description="Target delivery hour (UTC)")
    publishTime: datetime = Field(..., description="NESO publication timestamp (UTC)")
    generation: float = Field(..., description="Forecasted wind generation in MW")
    cutoff_time: Optional[datetime] = Field(None, description="Cutoff deadline applied")
    lead_time_hours: Optional[float] = Field(None, description="Lead time (startTime - publishTime) in hours")


class ForecastsResponse(BaseModel):
    start_date: str
    end_date: str
    cutoff_time: str
    cutoff_days_before: int
    count: int
    data: List[ForecastRecord]


class ComparisonRecord(BaseModel):
    startTime: datetime = Field(..., description="Target delivery hour (UTC)")
    forecast_generation: float = Field(..., description="Day-ahead forecast in MW")
    actual_generation: float = Field(..., description="Outturn generation in MW")
    error: float = Field(..., description="Forecast error (F - A) in MW")
    absolute_error: float = Field(..., description="Absolute error |F - A| in MW")
    publishTime: datetime = Field(..., description="Forecast publication timestamp (UTC)")
    cutoff_time: datetime = Field(..., description="Day-ahead cutoff timestamp (UTC)")
    lead_time_hours: float = Field(..., description="Lead time (startTime - publishTime) in hours")


class ComparisonResponse(BaseModel):
    start_date: str
    end_date: str
    cutoff_time: str
    cutoff_days_before: int
    count: int
    data: List[ComparisonRecord]


class AccuracyResponse(BaseModel):
    n_matched: int = Field(..., description="Total matched hourly intervals (N)")
    mae: Optional[float] = Field(None, description="Mean Absolute Error in MW")
    rmse: Optional[float] = Field(None, description="Root Mean Squared Error in MW")
    mean_error: Optional[float] = Field(None, description="Mean Error / Bias in MW (F - A)")
    mape: Optional[float] = Field(None, description="Mean Absolute Percentage Error (%), excluding actual == 0")
    wape: Optional[float] = Field(None, description="Weighted Absolute Percentage Error (%)")
    excluded_zero_actuals: int = Field(..., description="Number of intervals with actual=0 excluded from MAPE")
    unmatched_actuals: int = Field(..., description="Actual intervals with no valid forecast")
    unmatched_forecasts: int = Field(..., description="Forecast intervals with no valid actual")
    cutoff_time: str = Field(..., description="Configured cutoff clock time (UTC)")
    cutoff_days_before: int = Field(..., description="Configured days before delivery cutoff")
    method: str = Field(..., description="Actuals aggregation method used")


class DailyAccuracyRecord(BaseModel):
    date: str = Field(..., description="Delivery date (YYYY-MM-DD)")
    n_matched: int = Field(..., description="Number of matched hourly intervals on this date")
    mae: Optional[float] = Field(None, description="Daily MAE in MW")
    rmse: Optional[float] = Field(None, description="Daily RMSE in MW")
    mean_error: Optional[float] = Field(None, description="Daily Mean Bias in MW")
    mape: Optional[float] = Field(None, description="Daily MAPE (%) excluding actual == 0")
    wape: Optional[float] = Field(None, description="Daily WAPE (%)")


class DailyAccuracyResponse(BaseModel):
    start_date: str
    end_date: str
    cutoff_time: str
    cutoff_days_before: int
    daily_metrics: List[DailyAccuracyRecord]
    overall: AccuracyResponse


class ForecastExplorerItem(BaseModel):
    publishTime: datetime = Field(..., description="Forecast publication timestamp (UTC)")
    generation: float = Field(..., description="Forecasted generation in MW")
    lead_time_hours: float = Field(..., description="Lead time (startTime - publishTime) in hours")
    is_selected: bool = Field(..., description="Whether this forecast was chosen by the cutoff rule")
    is_before_cutoff: bool = Field(..., description="Whether published on or before the cutoff deadline")


class ForecastExplorerResponse(BaseModel):
    target_startTime: datetime = Field(..., description="Target delivery interval (UTC)")
    actual_generation: Optional[float] = Field(None, description="Actual generation in MW (if available)")
    selected_forecast: Optional[float] = Field(None, description="Selected day-ahead forecast in MW")
    cutoff_time: datetime = Field(..., description="Applicable cutoff timestamp (UTC)")
    total_forecasts: int = Field(..., description="Total forecasts published for this target interval")
    forecasts: List[ForecastExplorerItem]


class MethodologyResponse(BaseModel):
    decision_cutoff_rule: Dict[str, Any]
    aggregation_methods: Dict[str, Any]
    metric_definitions: Dict[str, Any]
    data_coverage: Dict[str, Any]
