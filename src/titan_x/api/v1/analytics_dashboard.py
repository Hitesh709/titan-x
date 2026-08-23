from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from titan_x.services.analytics_dashboard_service import AnalyticsDashboardService

router = APIRouter(prefix="/analytics", tags=["Analytics"])


class AnalyticsRequest(BaseModel):
    equity: list[float] = Field(min_length=1, max_length=10000)
    trades: list[float] = Field(default_factory=list, max_length=10000)
    benchmark_return_pct: float | None = None

    @field_validator("equity", "trades")
    @classmethod
    def finite_values(cls, values: list[float]) -> list[float]:
        if any(value != value or value in (float("inf"), float("-inf")) for value in values):
            raise ValueError("equity/trade values must be finite")
        return values


@router.post("/dashboard")
def dashboard(payload: AnalyticsRequest) -> dict[str, Any]:
    try:
        return AnalyticsDashboardService().build(
            payload.equity,
            payload.trades,
            payload.benchmark_return_pct,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
