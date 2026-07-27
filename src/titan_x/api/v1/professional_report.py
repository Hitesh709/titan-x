from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.services.professional_report_service import ProfessionalReportService

router = APIRouter(prefix="/professional-report", tags=["professional_report"])


async def _get_service(
    session: AsyncSession = Depends(deps.get_session),
) -> ProfessionalReportService:
    return ProfessionalReportService(session)


@router.post("/generate/{symbol}", summary="Generate a professional report for a symbol")
async def generate_report(
    symbol: str,
    direction: str = Query("bullish"),
    service: ProfessionalReportService = Depends(_get_service),
    _=Depends(deps.get_current_active_superuser),
):
    report = await service.generate(symbol, direction=direction)
    return {
        "id": report.id,
        "symbol": report.symbol,
        "trade_date": report.trade_date.isoformat(),
        "direction": report.direction,
        "current_price": report.current_price,
    }


@router.get("/reports/{symbol}", summary="List professional reports for a symbol")
async def list_reports(
    symbol: str,
    limit: int = Query(20),
    offset: int = Query(0),
    service: ProfessionalReportService = Depends(_get_service),
):
    reports = await service.get_reports(symbol, limit=limit, offset=offset)
    return {
        "total": len(reports),
        "reports": [
            {
                "id": r.id,
                "symbol": r.symbol,
                "trade_date": r.trade_date.isoformat(),
                "direction": r.direction,
                "current_price": r.current_price,
            }
            for r in reports
        ],
    }


@router.get("/{report_id}", summary="Get a professional report by ID")
async def get_report(
    report_id: int,
    service: ProfessionalReportService = Depends(_get_service),
):
    report = await service.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return {
        "id": report.id,
        "symbol": report.symbol,
        "trade_date": report.trade_date.isoformat(),
        "direction": report.direction,
        "current_price": report.current_price,
        "summary": report.summary_json,
        "technical": report.technical_json,
        "fundamental": report.fundamental_json,
        "news": report.news_json,
        "risk": report.risk_json,
        "prediction": report.prediction_json,
    }


@router.get("/{report_id}/export", response_class=HTMLResponse, summary="Export a professional report as HTML (print-ready PDF)")
async def export_report(
    report_id: int,
    service: ProfessionalReportService = Depends(_get_service),
):
    report = await service.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return HTMLResponse(content=report.html_content)
