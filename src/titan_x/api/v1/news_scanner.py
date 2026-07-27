"""News Scanner API.

Scan news across Company, Sector, Macro, Government, and Global
dimensions. Generate AI tags from NLP analysis data.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.services.news_scanner_service import NewsScannerService

router = APIRouter(prefix="/news-scanner", tags=["news_scanner"])


async def _get_service(
    session: AsyncSession = Depends(deps.get_session),
) -> NewsScannerService:
    return NewsScannerService(session)


@router.get("/scan")
async def scan_all(
    days: int = Query(7, ge=1, le=365),
    min_confidence: float = Query(0.0, ge=0, le=1),
    service: NewsScannerService = Depends(_get_service),
) -> dict:
    return await service.scan(days, min_confidence)


@router.get("/scan/{category}")
async def scan_category(
    category: str,
    days: int = Query(7, ge=1, le=365),
    min_confidence: float = Query(0.0, ge=0, le=1),
    service: NewsScannerService = Depends(_get_service),
) -> dict:
    return await service.scan_category(category, days, min_confidence)
