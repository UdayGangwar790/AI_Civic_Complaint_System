from typing import Any, Optional
from pydantic import BaseModel, Field


class AnalyticsSummary(BaseModel):
    total_cases: int = 0
    open_cases: int = 0
    resolved_cases: int = 0
    assigned_cases: int = 0
    unassigned_cases: int = 0
    average_priority_score: float = 0.0


class DistributionItem(BaseModel):
    key: str
    label: str
    count: int = 0
    percentage: float = 0.0


class TimeSeriesItem(BaseModel):
    date: str
    count: int = 0


class ConcentrationItem(BaseModel):
    road: str
    city: str
    count: int = 0


class ResolutionMetrics(BaseModel):
    resolved_count: int = 0
    closed_count: int = 0
    open_count: int = 0
    resolution_rate_pct: float = 0.0


class OperationalAnalyticsResponse(BaseModel):
    summary: AnalyticsSummary
    issue_distribution: list[DistributionItem] = Field(default_factory=list)
    priority_distribution: list[DistributionItem] = Field(default_factory=list)
    status_distribution: list[DistributionItem] = Field(default_factory=list)
    time_series: list[TimeSeriesItem] = Field(default_factory=list)
    city_distribution: list[DistributionItem] = Field(default_factory=list)
    duplicate_distribution: list[DistributionItem] = Field(default_factory=list)
    authority_distribution: list[DistributionItem] = Field(default_factory=list)
    geographic_concentration: list[ConcentrationItem] = Field(default_factory=list)
    resolution_metrics: ResolutionMetrics
    disclaimer: str = (
        "This is an explainable engineering prioritization baseline and operational summary, "
        "not emergency outcome prediction."
    )
