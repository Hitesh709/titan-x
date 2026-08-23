from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/live-signals", tags=["Live Signals"])


@router.get("/health")
def health() -> dict[str, Any]:
    return {"status": "healthy", "service": "live-signal-pipeline"}
