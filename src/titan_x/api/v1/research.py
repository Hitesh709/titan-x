"""Company research endpoints.

Lists the full universe joined with the latest live recommendation for each
symbol and the number of trading days of data actually used, so the Research
tab can sort by "most data first" and let users search any company.
"""
from datetime import date
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.api.schemas import PaginatedResponse
from titan_x.models.company import Company
from titan_x.models.recommendation import Recommendation
from titan_x.models.user import User

router = APIRouter(prefix="/research", tags=["research"])

SORTABLE_COLUMNS = {
    "symbol",
    "company_name",
    "days",
    "score",
    "signal",
    "confidence",
    "predicted_return_pct",
}

# signal ordering: strongest buy -> strongest sell (used by list sort)
_SIGNAL_RANK = {
    "strong_buy": 5,
    "buy": 4,
    "hold": 3,
    "sell": 2,
    "strong_sell": 1,
}


def _meta(recommendation: Recommendation) -> dict:
    try:
        raw = recommendation.metadata_json
        if not raw:
            return {}
        if isinstance(raw, dict):
            return dict(raw)
        parsed = json.loads(raw)
        return dict(parsed) if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def _rec_fields(r: Recommendation) -> dict:
    return {
        "direction": r.direction,
        "signal": r.signal,
        "score": r.score,
        "confidence": r.confidence,
        "predicted_return_pct": r.predicted_return_pct,
        "price_target": r.price_target,
        "current_price": r.current_price,
        "risk_level": r.risk_level,
        "timeframe": r.timeframe,
        "reasoning": r.reasoning,
        "generated_at": r.generated_at.isoformat() if r.generated_at else None,
    }


async def _price_days(session: AsyncSession) -> dict[str, int]:
    rows = (await session.execute(
        text("SELECT symbol, COUNT(*) FROM daily_prices GROUP BY symbol")
    )).all()
    return {r[0]: int(r[1]) for r in rows}


@router.get("/companies")
async def list_research_companies(
    session: Annotated[AsyncSession, Depends(deps.get_session)],
    _: Annotated[User, Depends(deps.get_current_active_user)],
    search: str | None = Query(None, min_length=1, max_length=100),
    sort_by: str = Query("days", pattern="^([A-Za-z_]+)$"),
    sort_desc: bool = Query(True),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> PaginatedResponse:
    if sort_by not in SORTABLE_COLUMNS:
        raise HTTPException(422, f"Unsupported sort_by '{sort_by}'")

    companies = (await session.execute(
        select(
            Company.symbol, Company.company_name, Company.sector,
            Company.industry, Company.market_cap, Company.listing_date,
        )
    )).all()
    recs = (await session.execute(
        select(Recommendation)
        .where(Recommendation.status == "active")
        .order_by(desc(Recommendation.generated_at))
    )).scalars().all()
    latest: dict[str, Recommendation] = {}
    for r in recs:
        latest.setdefault(r.symbol, r)
    price_days = await _price_days(session)

    items = []
    for sym, name, sector, industry, mcap, listing_date in companies:
        r = latest.get(sym)
        meta = _meta(r) if r else {}
        days = int(meta.get("data_points") or price_days.get(sym, 0))
        row = {
            "symbol": sym,
            "company_name": name,
            "sector": sector,
            "industry": industry,
            "market_cap": mcap,
            "listing_date": listing_date.isoformat() if isinstance(listing_date, date) else listing_date,
            "days": days,
            "has_research": r is not None,
            **(_rec_fields(r) if r else {}),
        }
        items.append(row)

    if search:
        term = search.strip().lower()
        items = [
            i for i in items
            if term in i["symbol"].lower() or term in (i["company_name"] or "").lower()
        ]

    reverse = bool(sort_desc)
    if sort_by == "signal":
        items.sort(key=lambda i: _SIGNAL_RANK.get((i.get("signal") or "hold").lower(), 0), reverse=reverse)
    else:
        def _key(i):
            v = i.get(sort_by)
            return (v is not None, v)
        items.sort(key=_key, reverse=reverse)

    total = len(items)
    return PaginatedResponse(items=items[skip:skip + limit], total=total, skip=skip, limit=limit)


@router.get("/{symbol}")
async def get_research_detail(
    symbol: str,
    session: Annotated[AsyncSession, Depends(deps.get_session)],
    _: Annotated[User, Depends(deps.get_current_active_user)],
) -> dict:
    company = (await session.execute(
        select(
            Company.symbol, Company.company_name, Company.sector,
            Company.industry, Company.market_cap, Company.listing_date,
        ).where(Company.symbol == symbol.upper())
    )).first()
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    sym, name, sector, industry, mcap, listing_date = company
    r = (await session.execute(
        select(Recommendation)
        .where(Recommendation.symbol == sym, Recommendation.status == "active")
        .order_by(desc(Recommendation.generated_at))
        .limit(1)
    )).scalar_one_or_none()

    meta = _meta(r) if r else {}
    price_days = await _price_days(session)
    days = int(meta.get("data_points") or price_days.get(sym, 0))

    payload: dict = {
        "symbol": sym,
        "company_name": name,
        "sector": sector,
        "industry": industry,
        "market_cap": mcap,
        "listing_date": listing_date.isoformat() if isinstance(listing_date, date) else listing_date,
        "days": days,
        "has_research": r is not None,
    }
    if r is not None:
        payload.update(_rec_fields(r))
        payload["evidence"] = meta.get("evidence") or []
        payload["caution"] = meta.get("caution") or []
        payload["returns"] = meta.get("returns") or {}
    return payload