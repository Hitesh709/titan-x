import asyncio
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from titan_x.api.dependencies import get_current_active_user
from titan_x.infrastructure.jugaad_nse_provider import JugaadNSEProvider
from titan_x.models.user import User

router = APIRouter(prefix="/indices", tags=["indices"])

# NSE-only universe. International/SENSEX values are not fabricated when the
# selected provider does not supply them.
INDEXES = [
    ("NIFTY", "NIFTY 50", "NIFTY 50"),
    ("BANKNIFTY", "NIFTY Bank", "NIFTY BANK"),
    ("NIFTYNEXT50", "NIFTY Next 50", "NIFTY NEXT 50"),
    ("NIFTY100", "NIFTY 100", "NIFTY 100"),
    ("NIFTYMID", "NIFTY Midcap 100", "NIFTY MIDCAP 100"),
    ("NIFTYSMALLCAP", "NIFTY Smallcap 100", "NIFTY SMALLCAP 100"),
    ("NIFTYAUTO", "NIFTY Auto", "NIFTY AUTO"),
    ("NIFTYPHARMA", "NIFTY Pharma", "NIFTY PHARMA"),
    ("NIFTYFMCG", "NIFTY FMCG", "NIFTY FMCG"),
    ("NIFTYIT", "NIFTY IT", "NIFTY IT"),
    ("NIFTYMETAL", "NIFTY Metal", "NIFTY METAL"),
    ("NIFTYREALTY", "NIFTY Realty", "NIFTY REALTY"),
    ("NIFTYFIN", "NIFTY Financial Services", "NIFTY FINANCIAL SERVICES"),
    ("INDIAVIX", "India VIX", "INDIA VIX"),
]


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _index_row(raw: dict) -> dict | None:
    rows = raw.get("data") or []
    if isinstance(rows, dict):
        rows = [rows]
    row = rows[0] if rows else raw.get("metadata") or {}
    if not isinstance(row, dict):
        return None
    close = _number(row.get("last", row.get("lastPrice")))
    if close is None or close <= 0:
        return None
    previous = _number(row.get("previousClose", row.get("previousDay")))
    open_ = _number(row.get("open")) or close
    high = _number(row.get("high")) or close
    low = _number(row.get("low")) or close
    change = _number(row.get("variation"))
    change_pct = _number(row.get("percentChange"))
    if change is None and previous is not None:
        change = close - previous
    if change_pct is None and previous:
        change_pct = change / previous * 100 if change is not None else 0.0
    return {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "prev_close": previous,
        "change": round(change or 0.0, 2),
        "change_pct": round(change_pct or 0.0, 2),
        "volume": int(_number(row.get("volume")) or 0),
    }


async def _fetch_index(client, symbol: str, name: str, nse_name: str) -> dict | None:
    raw = await asyncio.to_thread(client.live_index, nse_name)
    current = _index_row(raw or {})
    if not current:
        return None
    timestamp = raw.get("timestamp") if isinstance(raw, dict) else None
    if timestamp:
        try:
            dt = datetime.strptime(timestamp, "%d-%b-%Y %H:%M:%S").replace(tzinfo=timezone.utc)
            trade_date = dt.date().isoformat()
        except ValueError:
            trade_date = datetime.now(timezone.utc).date().isoformat()
    else:
        trade_date = datetime.now(timezone.utc).date().isoformat()
    return {"symbol": symbol, "name": name, "trade_date": trade_date, **current, "source": "jugaad-data/NSE"}


@router.get("")
async def list_indices(_: Annotated[User, Depends(get_current_active_user)]):
    """Return live NSE index data only; never synthetic values."""
    client = JugaadNSEProvider()._client()
    results = await asyncio.gather(
        *[_fetch_index(client, symbol, name, nse_name) for symbol, name, nse_name in INDEXES],
        return_exceptions=True,
    )
    items = [result for result in results if isinstance(result, dict)]
    if not items:
        raise HTTPException(503, "Live NSE index data is temporarily unavailable. No synthetic index data is used.")
    return {"items": items, "source": "jugaad-data/NSE"}


@router.get("/{symbol}/history")
async def get_index_history(
    symbol: str,
    _: Annotated[User, Depends(get_current_active_user)],
    range: str = Query("1W", pattern=r"^(1W|1M|3M|6M|YTD|1Y)$"),
):
    item = next((x for x in INDEXES if x[0] == symbol.upper()), None)
    if item is None:
        raise HTTPException(404, f"No NSE history for index {symbol.upper()}")
    client = JugaadNSEProvider()._client()
    try:
        raw = await asyncio.to_thread(client.chart_data, item[2], True)
        rows = JugaadNSEProvider._parse_chart_rows(raw or {}, item[0])
    except Exception as exc:
        raise HTTPException(503, f"Live NSE index history unavailable: {exc}") from exc
    if not rows:
        raise HTTPException(404, f"No live NSE history for index {symbol.upper()}")
    return {"symbol": item[0], "range": range, "source": "jugaad-data/NSE", "points": rows}


@router.get("/{symbol}/performance")
async def get_index_performance(
    symbol: str,
    _: Annotated[User, Depends(get_current_active_user)],
):
    item = next((x for x in INDEXES if x[0] == symbol.upper()), None)
    if item is None:
        raise HTTPException(404, f"No NSE data for index {symbol.upper()}")
    client = JugaadNSEProvider()._client()
    try:
        raw = await asyncio.to_thread(client.live_index, item[2])
    except Exception as exc:
        raise HTTPException(503, f"Live NSE index performance unavailable: {exc}") from exc
    if not raw:
        raise HTTPException(404, f"No live NSE data for index {symbol.upper()}")
    data = raw.get("data") or []
    row = data[0] if data and isinstance(data[0], dict) else raw.get("metadata") or {}
    periods = {}
    for label, key in (("1M", "perChange30d"), ("1Y", "perChange365d")):
        value = _number(row.get(key) if isinstance(row, dict) else None)
        if value is not None:
            periods[label] = round(value, 2)
    current = _index_row(raw)
    if not current:
        raise HTTPException(404, f"No live NSE data for index {symbol.upper()}")
    return {"symbol": item[0], "trade_date": datetime.now(timezone.utc).date().isoformat(), "close": current["close"], "periods": periods, "source": "jugaad-data/NSE"}
