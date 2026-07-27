from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from titan_x.api.dependencies import (
    get_institutional_analysis_service,
    require_api_key,
)
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.services.institutional_analysis_service import InstitutionalAnalysisService

inst_router = APIRouter(
    prefix="/institutional",
    tags=["institutional"],
    dependencies=[Depends(require_api_key)],
)


# --- FII ---

@inst_router.post("/fii", status_code=status.HTTP_201_CREATED)
async def create_fii_holding(
    service: Annotated[InstitutionalAnalysisService, Depends(get_institutional_analysis_service)],
    company_id: int = Query(...),
    fii_name: str = Query(..., min_length=1, max_length=256),
    category: str = Query("FII", max_length=16),
    shares_held: int | None = Query(None),
    percentage: float = Query(..., ge=0, le=100),
    change_percentage: float | None = Query(None),
    value_crores: float | None = Query(None),
    quarter: int = Query(..., ge=1, le=4),
    year: int = Query(..., ge=2000, le=2100),
    filing_date: date = Query(...),
) -> dict:
    result = await service.create_fii_holding(
        company_id=company_id, fii_name=fii_name, category=category,
        shares_held=shares_held, percentage=percentage, change_percentage=change_percentage,
        value_crores=value_crores, quarter=quarter, year=year, filing_date=filing_date,
    )
    return {"id": result.id, "company_id": result.company_id, "fii_name": result.fii_name,
            "percentage": result.percentage, "quarter": result.quarter, "year": result.year}

@inst_router.get("/fii")
async def list_fii_holdings(
    service: Annotated[InstitutionalAnalysisService, Depends(get_institutional_analysis_service)],
    company_id: int | None = Query(None),
    fii_name: str | None = Query(None, max_length=256),
    year: int | None = Query(None, ge=2000, le=2100),
    quarter: int | None = Query(None, ge=1, le=4),
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[dict]:
    rows, total = await service.list_fii_holdings(company_id=company_id, fii_name=fii_name, year=year, quarter=quarter, skip=skip, limit=limit)
    items = [{"id": r.id, "company_id": r.company_id, "fii_name": r.fii_name, "percentage": r.percentage,
              "change_percentage": r.change_percentage, "quarter": r.quarter, "year": r.year,
              "filing_date": r.filing_date.isoformat()} for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)

@inst_router.delete("/fii/{holding_id}")
async def delete_fii_holding(
    holding_id: int,
    service: Annotated[InstitutionalAnalysisService, Depends(get_institutional_analysis_service)],
) -> MessageResponse:
    deleted = await service.delete_fii_holding(holding_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FII holding not found")
    return MessageResponse(message="FII holding deleted")


# --- DII ---

@inst_router.post("/dii", status_code=status.HTTP_201_CREATED)
async def create_dii_holding(
    service: Annotated[InstitutionalAnalysisService, Depends(get_institutional_analysis_service)],
    company_id: int = Query(...),
    dii_name: str = Query(..., min_length=1, max_length=256),
    category: str = Query("DII", max_length=32),
    shares_held: int | None = Query(None),
    percentage: float = Query(..., ge=0, le=100),
    change_percentage: float | None = Query(None),
    value_crores: float | None = Query(None),
    quarter: int = Query(..., ge=1, le=4),
    year: int = Query(..., ge=2000, le=2100),
    filing_date: date = Query(...),
) -> dict:
    result = await service.create_dii_holding(
        company_id=company_id, dii_name=dii_name, category=category,
        shares_held=shares_held, percentage=percentage, change_percentage=change_percentage,
        value_crores=value_crores, quarter=quarter, year=year, filing_date=filing_date,
    )
    return {"id": result.id, "company_id": result.company_id, "dii_name": result.dii_name,
            "percentage": result.percentage, "quarter": result.quarter, "year": result.year}

@inst_router.get("/dii")
async def list_dii_holdings(
    service: Annotated[InstitutionalAnalysisService, Depends(get_institutional_analysis_service)],
    company_id: int | None = Query(None),
    dii_name: str | None = Query(None, max_length=256),
    year: int | None = Query(None, ge=2000, le=2100),
    quarter: int | None = Query(None, ge=1, le=4),
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[dict]:
    rows, total = await service.list_dii_holdings(company_id=company_id, dii_name=dii_name, year=year, quarter=quarter, skip=skip, limit=limit)
    items = [{"id": r.id, "company_id": r.company_id, "dii_name": r.dii_name, "percentage": r.percentage,
              "change_percentage": r.change_percentage, "quarter": r.quarter, "year": r.year,
              "filing_date": r.filing_date.isoformat()} for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)

@inst_router.delete("/dii/{holding_id}")
async def delete_dii_holding(
    holding_id: int,
    service: Annotated[InstitutionalAnalysisService, Depends(get_institutional_analysis_service)],
) -> MessageResponse:
    deleted = await service.delete_dii_holding(holding_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DII holding not found")
    return MessageResponse(message="DII holding deleted")


# --- MF ---

@inst_router.post("/mf", status_code=status.HTTP_201_CREATED)
async def create_mf_holding(
    service: Annotated[InstitutionalAnalysisService, Depends(get_institutional_analysis_service)],
    company_id: int = Query(...),
    amc: str = Query(..., min_length=1, max_length=128),
    scheme_name: str = Query(..., min_length=1, max_length=256),
    fund_type: str | None = Query(None, max_length=64),
    shares_held: int | None = Query(None),
    percentage: float = Query(..., ge=0, le=100),
    change_percentage: float | None = Query(None),
    value_crores: float | None = Query(None),
    quarter: int = Query(..., ge=1, le=4),
    year: int = Query(..., ge=2000, le=2100),
    filing_date: date = Query(...),
) -> dict:
    result = await service.create_mf_holding(
        company_id=company_id, amc=amc, scheme_name=scheme_name, fund_type=fund_type,
        shares_held=shares_held, percentage=percentage, change_percentage=change_percentage,
        value_crores=value_crores, quarter=quarter, year=year, filing_date=filing_date,
    )
    return {"id": result.id, "company_id": result.company_id, "scheme_name": result.scheme_name,
            "amc": result.amc, "percentage": result.percentage, "quarter": result.quarter, "year": result.year}

@inst_router.get("/mf")
async def list_mf_holdings(
    service: Annotated[InstitutionalAnalysisService, Depends(get_institutional_analysis_service)],
    company_id: int | None = Query(None),
    scheme_name: str | None = Query(None, max_length=256),
    amc: str | None = Query(None, max_length=128),
    year: int | None = Query(None, ge=2000, le=2100),
    quarter: int | None = Query(None, ge=1, le=4),
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[dict]:
    rows, total = await service.list_mf_holdings(company_id=company_id, scheme_name=scheme_name, amc=amc, year=year, quarter=quarter, skip=skip, limit=limit)
    items = [{"id": r.id, "company_id": r.company_id, "scheme_name": r.scheme_name, "amc": r.amc,
              "percentage": r.percentage, "change_percentage": r.change_percentage,
              "quarter": r.quarter, "year": r.year, "filing_date": r.filing_date.isoformat()} for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)

@inst_router.delete("/mf/{holding_id}")
async def delete_mf_holding(
    holding_id: int,
    service: Annotated[InstitutionalAnalysisService, Depends(get_institutional_analysis_service)],
) -> MessageResponse:
    deleted = await service.delete_mf_holding(holding_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MF holding not found")
    return MessageResponse(message="MF holding deleted")


# --- ETF ---

@inst_router.post("/etf", status_code=status.HTTP_201_CREATED)
async def create_etf_holding(
    service: Annotated[InstitutionalAnalysisService, Depends(get_institutional_analysis_service)],
    company_id: int = Query(...),
    etf_name: str = Query(..., min_length=1, max_length=256),
    issuer: str = Query(..., min_length=1, max_length=128),
    shares_held: int | None = Query(None),
    percentage: float = Query(..., ge=0, le=100),
    change_percentage: float | None = Query(None),
    value_crores: float | None = Query(None),
    quarter: int = Query(..., ge=1, le=4),
    year: int = Query(..., ge=2000, le=2100),
    filing_date: date = Query(...),
) -> dict:
    result = await service.create_etf_holding(
        company_id=company_id, etf_name=etf_name, issuer=issuer,
        shares_held=shares_held, percentage=percentage, change_percentage=change_percentage,
        value_crores=value_crores, quarter=quarter, year=year, filing_date=filing_date,
    )
    return {"id": result.id, "company_id": result.company_id, "etf_name": result.etf_name,
            "issuer": result.issuer, "percentage": result.percentage, "quarter": result.quarter, "year": result.year}

@inst_router.get("/etf")
async def list_etf_holdings(
    service: Annotated[InstitutionalAnalysisService, Depends(get_institutional_analysis_service)],
    company_id: int | None = Query(None),
    etf_name: str | None = Query(None, max_length=256),
    year: int | None = Query(None, ge=2000, le=2100),
    quarter: int | None = Query(None, ge=1, le=4),
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[dict]:
    rows, total = await service.list_etf_holdings(company_id=company_id, etf_name=etf_name, year=year, quarter=quarter, skip=skip, limit=limit)
    items = [{"id": r.id, "company_id": r.company_id, "etf_name": r.etf_name, "issuer": r.issuer,
              "percentage": r.percentage, "change_percentage": r.change_percentage,
              "quarter": r.quarter, "year": r.year, "filing_date": r.filing_date.isoformat()} for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)

@inst_router.delete("/etf/{holding_id}")
async def delete_etf_holding(
    holding_id: int,
    service: Annotated[InstitutionalAnalysisService, Depends(get_institutional_analysis_service)],
) -> MessageResponse:
    deleted = await service.delete_etf_holding(holding_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ETF holding not found")
    return MessageResponse(message="ETF holding deleted")


# --- SCORING / ANALYSIS ---

@inst_router.get("/score/fii/{company_id}")
async def score_fii(
    company_id: int,
    service: Annotated[InstitutionalAnalysisService, Depends(get_institutional_analysis_service)],
) -> dict:
    return await service.analyze_fii(company_id)

@inst_router.get("/score/dii/{company_id}")
async def score_dii(
    company_id: int,
    service: Annotated[InstitutionalAnalysisService, Depends(get_institutional_analysis_service)],
) -> dict:
    return await service.analyze_dii(company_id)

@inst_router.get("/score/mf/{company_id}")
async def score_mf(
    company_id: int,
    service: Annotated[InstitutionalAnalysisService, Depends(get_institutional_analysis_service)],
) -> dict:
    return await service.analyze_mf(company_id)

@inst_router.get("/score/etf/{company_id}")
async def score_etf(
    company_id: int,
    service: Annotated[InstitutionalAnalysisService, Depends(get_institutional_analysis_service)],
) -> dict:
    return await service.analyze_etf(company_id)

@inst_router.get("/score/trends/{company_id}")
async def score_institutional_trends(
    company_id: int,
    service: Annotated[InstitutionalAnalysisService, Depends(get_institutional_analysis_service)],
) -> dict:
    return await service.analyze_institutional_trends(company_id)

@inst_router.post("/score/{company_id}", status_code=status.HTTP_201_CREATED)
async def generate_institutional_analysis(
    company_id: int,
    service: Annotated[InstitutionalAnalysisService, Depends(get_institutional_analysis_service)],
) -> dict:
    result = await service.generate_analysis(company_id)
    import json
    return {
        "id": result.id, "company_id": result.company_id,
        "analysis_date": result.analysis_date.isoformat(),
        "fii_score": result.fii_score, "dii_score": result.dii_score,
        "mf_score": result.mf_score, "etf_score": result.etf_score,
        "institutional_trend_score": result.institutional_trend_score,
        "fii_dii_divergence": result.fii_dii_divergence,
        "composite_score": result.composite_score,
        "signal": result.signal, "confidence": result.confidence,
        "insights_json": json.loads(result.insights_json),
        "generated_at": result.generated_at.isoformat() if result.generated_at else None,
    }

@inst_router.get("/score")
async def list_institutional_analyses(
    service: Annotated[InstitutionalAnalysisService, Depends(get_institutional_analysis_service)],
    company_id: int | None = Query(None),
    signal: str | None = Query(None, pattern="^(strong_buy|buy|hold|sell|strong_sell)$"),
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[dict]:
    rows, total = await service.list_analyses(company_id=company_id, signal=signal, skip=skip, limit=limit)
    items = [{
        "id": r.id, "company_id": r.company_id,
        "analysis_date": r.analysis_date.isoformat(),
        "fii_score": r.fii_score, "dii_score": r.dii_score,
        "mf_score": r.mf_score, "etf_score": r.etf_score,
        "composite_score": r.composite_score,
        "signal": r.signal, "confidence": r.confidence,
        "generated_at": r.generated_at.isoformat() if r.generated_at else None,
    } for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)

@inst_router.get("/score/latest/{company_id}")
async def get_latest_institutional_analysis(
    company_id: int,
    service: Annotated[InstitutionalAnalysisService, Depends(get_institutional_analysis_service)],
) -> dict:
    result = await service.get_latest_analysis(company_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No institutional analysis found")
    import json
    return {
        "id": result.id, "company_id": result.company_id,
        "analysis_date": result.analysis_date.isoformat(),
        "fii_score": result.fii_score, "dii_score": result.dii_score,
        "mf_score": result.mf_score, "etf_score": result.etf_score,
        "institutional_trend_score": result.institutional_trend_score,
        "fii_dii_divergence": result.fii_dii_divergence,
        "composite_score": result.composite_score,
        "signal": result.signal, "confidence": result.confidence,
        "insights_json": json.loads(result.insights_json),
        "generated_at": result.generated_at.isoformat() if result.generated_at else None,
    }

@inst_router.delete("/score/{analysis_id}")
async def delete_institutional_analysis(
    analysis_id: int,
    service: Annotated[InstitutionalAnalysisService, Depends(get_institutional_analysis_service)],
) -> MessageResponse:
    deleted = await service.delete_analysis(analysis_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    return MessageResponse(message="Institutional analysis deleted")
