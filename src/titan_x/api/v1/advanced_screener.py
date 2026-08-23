from datetime import date
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api import deps
from titan_x.api.schemas import PaginatedResponse
from titan_x.models.user import User
from titan_x.services.advanced_screener_service import AdvancedScreenerService
from titan_x.services.backtest_engine import BacktestEngine
from titan_x.services.market_data_service import MarketDataService

router = APIRouter(prefix="/screener", tags=["screener"])


class SavedScreenCreate(BaseModel):
    name: str
    description: str | None = None
    filters_json: str


class SavedScreenUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    filters_json: str | None = None


class ScreenerBacktestCreate(BaseModel):
    screen_id: int
    symbol: str
    start_date: date
    end_date: date
    initial_capital: float = 10000.0
    strategy_type: str = "sma_crossover"
    strategy_params: dict = Field(default_factory=dict)
    config: dict = Field(default_factory=dict)
    description: str | None = None


async def _enrich_current_market_data(
    session: AsyncSession,
    results: list[dict],
    as_of_date: date | None,
) -> list[dict]:
    """Overlay live quote price/volume for current screens.

    Historical/as-of screens must remain point-in-time and therefore keep the
    database price. For a current screen, however, a missing/stale DailyPrice
    row must never be displayed as if it were today's live quote.
    """
    if not results:
        return results
    if as_of_date is not None and as_of_date < date.today():
        return results

    symbols = [str(row.get("symbol", "")).upper() for row in results if row.get("symbol")]
    if not symbols:
        return results

    try:
        quotes = await MarketDataService(session).get_quotes(symbols)
    except Exception:
        return results

    by_symbol = {
        str(q.get("symbol", "")).upper(): q
        for q in (quotes.get("quotes") or [])
        if isinstance(q, dict)
    }

    enriched: list[dict] = []
    for row in results:
        item = dict(row)
        q = by_symbol.get(str(item.get("symbol", "")).upper())
        if q:
            live_price = q.get("last_price")
            live_volume = q.get("volume")
            if isinstance(live_price, (int, float)) and live_price > 0:
                item["close"] = live_price
            if isinstance(live_volume, (int, float)) and live_volume >= 0:
                item["volume"] = int(live_volume)
            item["live_quote"] = True
            item["quote_source"] = q.get("source") or "live_market_feed"
        else:
            item["live_quote"] = False
        enriched.append(item)
    return enriched


@router.post("/run")
async def run_adhoc_screen(
    filters: dict,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    as_of_date: date | None = Query(None, description="Evaluate historical data as of this date"),
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    service = AdvancedScreenerService(session)
    result = await service.run_screen(
        filters, current_user.id, skip=skip, limit=limit, as_of_date=as_of_date
    )
    result["results"] = await _enrich_current_market_data(session, result.get("results", []), as_of_date)
    return result


@router.post("/screens", status_code=status.HTTP_201_CREATED)
async def create_saved_screen(
    body: SavedScreenCreate,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    service = AdvancedScreenerService(session)
    return await service.save_screen(current_user.id, body.name, body.filters_json, body.description)


@router.get("/screens")
async def list_saved_screens(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    service = AdvancedScreenerService(session)
    screens, total = await service.list_screens(current_user.id, skip, limit)
    return PaginatedResponse(items=screens, total=total, skip=skip, limit=limit)


@router.get("/screens/{screen_id}")
async def get_saved_screen(
    screen_id: int,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    service = AdvancedScreenerService(session)
    screen = await service.get_screen(screen_id, current_user.id)
    if screen is None:
        raise HTTPException(status_code=404, detail="Saved screen not found")
    return screen


@router.put("/screens/{screen_id}")
async def update_saved_screen(
    screen_id: int,
    body: SavedScreenUpdate,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    service = AdvancedScreenerService(session)
    screen = await service.update_screen(
        screen_id, current_user.id,
        name=body.name, description=body.description, filters_json=body.filters_json,
    )
    if screen is None:
        raise HTTPException(status_code=404, detail="Saved screen not found")
    return screen


@router.delete("/screens/{screen_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saved_screen(
    screen_id: int,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    service = AdvancedScreenerService(session)
    deleted = await service.delete_screen(screen_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Saved screen not found")


@router.post("/screens/{screen_id}/run")
async def run_saved_screen(
    screen_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    as_of_date: date | None = Query(None, description="Evaluate historical data as of this date"),
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    service = AdvancedScreenerService(session)
    if as_of_date is None:
        result = await service.run_saved_screen(screen_id, current_user.id, skip, limit)
    else:
        screen = await service.get_screen(screen_id, current_user.id)
        if screen is None:
            raise HTTPException(status_code=404, detail="Saved screen not found")
        filters = json.loads(screen.filters_json)
        result = await service.run_screen(
            filters, current_user.id, screen_id, skip, limit, as_of_date=as_of_date
        )
    if result is None:
        raise HTTPException(status_code=404, detail="Saved screen not found")
    result["results"] = await _enrich_current_market_data(session, result.get("results", []), as_of_date)
    return result


@router.post("/screens/{screen_id}/backtest", status_code=status.HTTP_201_CREATED)
async def backtest_screened_symbol(
    screen_id: int,
    body: ScreenerBacktestCreate,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    if body.screen_id != screen_id:
        raise HTTPException(status_code=400, detail="screen_id in path and body must match")
    if body.start_date > body.end_date:
        raise HTTPException(status_code=400, detail="start_date must be on or before end_date")
    if body.initial_capital <= 0:
        raise HTTPException(status_code=400, detail="initial_capital must be greater than zero")

    screener = AdvancedScreenerService(session)
    screen = await screener.get_screen(screen_id, current_user.id)
    if screen is None:
        raise HTTPException(status_code=404, detail="Saved screen not found")

    try:
        filters = json.loads(screen.filters_json)
    except (json.JSONDecodeError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="Saved screen contains invalid filter JSON") from exc

    screen_result = await screener.run_screen(
        filters, current_user.id, screen_id=screen_id, skip=0, limit=5000
    )
    symbol = body.symbol.strip().upper()
    screened_symbols = {
        str(result.get("symbol", "")).upper() for result in screen_result.get("results", [])
    }
    if symbol not in screened_symbols:
        raise HTTPException(
            status_code=400,
            detail=f"Symbol {symbol} is not present in the current saved-screen result",
        )

    engine = BacktestEngine(session)
    backtest = await engine.create_backtest(
        user_id=current_user.id,
        name=f"{screen.name} - {symbol}",
        symbol=symbol,
        start_date=body.start_date,
        end_date=body.end_date,
        initial_capital=body.initial_capital,
        strategy_type=body.strategy_type,
        strategy_params=body.strategy_params,
        config=body.config,
        description=body.description or f"Backtest launched from saved screen {screen_id}",
    )

    try:
        result = await engine.run_backtest(backtest["id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "screen_id": screen_id,
        "symbol": symbol,
        "backtest": backtest,
        "result": result,
    }
