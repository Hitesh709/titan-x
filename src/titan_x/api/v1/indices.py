import asyncio
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from titan_x.api.dependencies import get_current_active_user
from titan_x.infrastructure.market_data_providers import YahooFinanceProvider
from titan_x.models.user import User

router = APIRouter(prefix="/indices", tags=["indices"])

# Index-only universe. No individual stocks, commodities, FX or crypto.
INDEXES = [
    ("NIFTY", "NIFTY 50", "^NSEI"),
    ("SENSEX", "S&P BSE Sensex", "^BSESN"),
    ("BANKNIFTY", "NIFTY Bank", "^NSEBANK"),
    ("NIFTYIT", "NIFTY IT", "^CNXIT"),
    ("NIFTYFIN", "NIFTY Financial Services", "^CNXFIN"),
    ("NIFTYMID", "NIFTY Midcap 100", "^NSEMDCP50"),
    ("NIFTYSMALLCAP", "NIFTY Smallcap 100", "^NSMIDCP"),
    ("NIFTYAUTO", "NIFTY Auto", "^CNXAUTO"),
    ("NIFTYPHARMA", "NIFTY Pharma", "^CNXPHARMA"),
    ("NIFTYFMCG", "NIFTY FMCG", "^CNXFMCG"),
    ("NIFTYMETAL", "NIFTY Metal", "^CNXMETAL"),
    ("NIFTYENERGY", "NIFTY Energy", "^CNXENERGY"),
    ("NIFTYREALTY", "NIFTY Realty", "^CNXREALTY"),
    ("SP500", "S&P 500", "^GSPC"),
    ("NASDAQ", "NASDAQ Composite", "^IXIC"),
    ("DOW", "Dow Jones Industrial Average", "^DJI"),
    ("RUSSELL2000", "Russell 2000", "^RUT"),
    ("FTSE100", "FTSE 100", "^FTSE"),
    ("DAX", "DAX", "^GDAXI"),
    ("CAC40", "CAC 40", "^FCHI"),
    ("NIKKEI225", "Nikkei 225", "^N225"),
    ("HANGSENG", "Hang Seng Index", "^HSI"),
    ("SHANGHAI", "Shanghai Composite", "000001.SS"),
    ("KOSPI", "KOSPI", "^KS11"),
    ("ASX200", "S&P/ASX 200", "^AXJO"),
]

RANGES = {"1W": "5d", "1M": "1mo", "3M": "3mo", "6M": "6mo", "YTD": "ytd", "1Y": "1y"}


async def _fetch_index(provider: YahooFinanceProvider, symbol: str, name: str, ticker: str, range_name: str = "5d") -> list[dict]:
    data = await provider._get(
        f"{provider.BASE_URL}/{ticker}",
        params={"range": RANGES.get(range_name, "5d"), "interval": "1d"},
    )
    result = (data.get("chart") or {}).get("result")
    if not result:
        return []
    chart = result[0]
    timestamps = chart.get("timestamp") or []
    quote = ((chart.get("indicators") or {}).get("quote") or [{}])[0]
    rows = []
    for i, ts in enumerate(timestamps):
        close = quote.get("close", [])[i] if i < len(quote.get("close", [])) else None
        if close is None:
            continue
        rows.append({
            "trade_date": datetime.fromtimestamp(ts, tz=datetime.now().astimezone().tzinfo).date().isoformat(),
            "open": float(quote.get("open", [close])[i] or close),
            "high": float(quote.get("high", [close])[i] or close),
            "low": float(quote.get("low", [close])[i] or close),
            "close": float(close),
            "volume": int(quote.get("volume", [0])[i] or 0),
        })
    return rows


@router.get("")
async def list_indices(
    _: Annotated[User, Depends(get_current_active_user)],
):
    """Return live index data only. Synthetic/demo index values are never used."""
    provider = YahooFinanceProvider()
    try:
        results = await asyncio.gather(
            *[_fetch_index(provider, symbol, name, ticker) for symbol, name, ticker in INDEXES],
            return_exceptions=True,
        )
    finally:
        await provider.close()

    items = []
    for (symbol, name, _), result in zip(INDEXES, results):
        if isinstance(result, Exception) or not result:
            continue
        current = result[-1]
        previous = result[-2] if len(result) > 1 else None
        prev_close = previous["close"] if previous else None
        change = current["close"] - prev_close if prev_close else 0.0
        change_pct = (change / prev_close * 100) if prev_close else 0.0
        items.append({
            "symbol": symbol,
            "name": name,
            **current,
            "prev_close": prev_close,
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "source": "yahoo_finance",
        })

    if not items:
        raise HTTPException(503, "Live index data is temporarily unavailable. Synthetic index data has been disabled.")
    return {"items": items}


@router.get("/{symbol}/history")
async def get_index_history(
    symbol: str,
    _: Annotated[User, Depends(get_current_active_user)],
    range: str = Query("3M", pattern=r"^(1W|1M|3M|6M|YTD|1Y)$"),
):
    item = next((x for x in INDEXES if x[0] == symbol.upper()), None)
    if item is None:
        raise HTTPException(404, f"No history for index {symbol.upper()}")
    provider = YahooFinanceProvider()
    try:
        points = await _fetch_index(provider, item[0], item[1], item[2], range)
    except Exception as exc:
        raise HTTPException(503, f"Live index history unavailable: {exc}")
    finally:
        await provider.close()
    if not points:
        raise HTTPException(404, f"No live history for index {symbol.upper()}")
    return {"symbol": item[0], "range": range, "source": "yahoo_finance", "points": points}


@router.get("/{symbol}/performance")
async def get_index_performance(
    symbol: str,
    _: Annotated[User, Depends(get_current_active_user)],
):
    item = next((x for x in INDEXES if x[0] == symbol.upper()), None)
    if item is None:
        raise HTTPException(404, f"No data for index {symbol.upper()}")
    provider = YahooFinanceProvider()
    try:
        points = await _fetch_index(provider, item[0], item[1], item[2], "1y")
    except Exception as exc:
        raise HTTPException(503, f"Live index performance unavailable: {exc}")
    finally:
        await provider.close()
    if len(points) < 2:
        raise HTTPException(404, f"No data for index {symbol.upper()}")
    last = points[-1]["close"]
    periods = {}
    for label, days in (("1W", 5), ("1M", 21), ("3M", 63), ("6M", 126), ("1Y", 252)):
        if len(points) > days and points[-days - 1]["close"]:
            periods[label] = round((last - points[-days - 1]["close"]) / points[-days - 1]["close"] * 100, 2)
    return {"symbol": item[0], "trade_date": points[-1]["trade_date"], "close": last, "periods": periods, "source": "yahoo_finance"}
