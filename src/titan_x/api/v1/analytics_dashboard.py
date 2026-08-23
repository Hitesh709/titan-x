from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from titan_x.services.analytics_dashboard_service import AnalyticsDashboardService

router = APIRouter(prefix="/analytics", tags=["Analytics"])


class AnalyticsRequest(BaseModel):
    equity: list[float] = Field(min_length=1)
    trades: list[float] = Field(default_factory=list)
    benchmark_return_pct: float | None = None


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
