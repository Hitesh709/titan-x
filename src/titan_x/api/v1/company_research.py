from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.services.company_research_service import CompanyResearchService

router = APIRouter(prefix="/company-research", tags=["company_research"])


async def _get_service(
    session: AsyncSession = Depends(deps.get_session),
) -> CompanyResearchService:
    return CompanyResearchService(session)


@router.post("/generate/{symbol}", summary="Generate company research for a symbol")
async def generate_research(
    symbol: str,
    service: CompanyResearchService = Depends(_get_service),
    _=Depends(deps.get_current_active_superuser),
):
    research = await service.generate(symbol)
    return {
        "id": research.id,
        "symbol": research.symbol,
        "as_of_date": research.as_of_date.isoformat(),
    }


@router.get("/{symbol}", summary="Get latest company research for a symbol")
async def get_latest_research(
    symbol: str,
    service: CompanyResearchService = Depends(_get_service),
):
    research = await service.get_research_by_symbol(symbol)
    if not research:
        raise HTTPException(status_code=404, detail="No research found for symbol")
    return {
        "id": research.id,
        "symbol": research.symbol,
        "as_of_date": research.as_of_date.isoformat(),
        "business": research.business_json,
        "financials": research.financials_json,
        "risks": research.risks_json,
        "growth": research.growth_json,
        "competition": research.competition_json,
        "ai_summary": research.ai_summary,
    }


@router.get("/{research_id}/export", response_class=HTMLResponse, summary="Export company research as HTML")
async def export_research(
    research_id: int,
    service: CompanyResearchService = Depends(_get_service),
):
    research = await service.get_research(research_id)
    if not research:
        raise HTTPException(status_code=404, detail="Research not found")
    return HTMLResponse(content=research.html_content)


@router.get("/list/{symbol}", summary="List company research history for a symbol")
async def list_research(
    symbol: str,
    limit: int = Query(10),
    offset: int = Query(0),
    service: CompanyResearchService = Depends(_get_service),
):
    records = await service.list_research(symbol, limit=limit, offset=offset)
    return {
        "total": await service.count_research(symbol),
        "records": [
            {
                "id": r.id,
                "symbol": r.symbol,
                "as_of_date": r.as_of_date.isoformat(),
            }
            for r in records
        ],
    }
