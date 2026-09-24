"""Fusion API router - Titan X Unified Intraday Strategy.

Exposes:
  GET /fusion/signal          : current BUY / SELL / HOLD decision
  GET /fusion/chart           : candles + per-bar signals + SuperTrend for chart overlay
  POST /fusion/backtest       : run an intraday backtest (in-sample / out-of-sample / walk-forward)
"""

from __future__ import annotations

import html

from datetime import date, datetime, timedelta, timezone as tz_mod

from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, request_session
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.db.repository import BaseRepository
from titan_x.infrastructure.market_data_providers import (
    MarketDataPoint,
    YahooFinanceProvider,
)
from titan_x.services.backtest_engine import BacktestEngine
from titan_x.services.performance_analyzer import PerformanceAnalyzer
from titan_x.services.titan_x_fusion import TitanXFusionEngine, FusionParams

router = APIRouter(
    prefix="/fusion",
    tags=["fusion"],
    dependencies=[Depends(get_current_active_user)],
)

_params = FusionParams()


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _normalize_symbol(s: str) -> str:
    """Yahoo normalises to .NS for India equities."""
    return s.strip().upper() + (".NS" if "." not in s.upper() and not s.upper().startswith("^") else "")


def _sanitize_reason(reason: str) -> str:
    """Replace Unicode mathematical symbols with ASCII equivalents for safe JSON transport.

    The Fusion engine uses ``≥`` / ``≤`` for risk/reward ratios; these characters
    can cause cp1252 encoding errors on some frontends.  This function maps them
    to ``>=`` / ``<=`` while leaving everything else untouched.
    """
    reason = reason.replace("\u2265", ">=").replace("\u2264", "<=")
    # Also HTML-entity-escape anything else that might be problematic.
    return html.escape(reason, quote=True)


async def _get_provider(session: AsyncSession) -> YahooFinanceProvider:
    return YahooFinanceProvider()


async def _fetch_candles(
    symbol: str,
    interval: str = "5m",
    start: date | None = None,
    end: date | None = None,
) -> list[MarketDataPoint]:
    """Fetch intraday candles from Yahoo via the provider."""
    provider = await _get_provider(None)  # provider does not need a session for candles
    points = await provider.get_historical_prices(
        symbol, interval=interval, start=start, end=end, synthetic_ok=False
    )
    return points


# ---------------------------------------------------------------------------
#  Endpoint 1 – Current signal
# ---------------------------------------------------------------------------

@router.get("/signal", response_model=dict[str, Any])
async def fusion_signal(
    symbol: str = Query(..., min_length=1, max_length=16),
    interval: str = Query("5m", pattern=r"^(5m|15m|30m)$"),
) -> dict[str, Any]:
    """Return the latest Titan X Fusion BUY/SELL/HOLD decision.

    The decision is based on the most recent *confirmed* bar (i.e. the last bar
    whose interval has fully elapsed).  No scores or confidence percentages are
    returned – only the deterministic decision with entry / stop / target if a
    trade is triggered.
    """
    sym = _normalize_symbol(symbol)
    points = await _fetch_candles(sym, interval=interval)

    if not points or len(points) < 60:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient candle data for {symbol} (need ≥60 bars)",
        )

    engine = TitanXFusionEngine(_params)
    decision = engine.evaluate(points, dedupe=True)

    # Sanitize the reason string for safe JSON transport.
    sanitized_reason = _sanitize_reason(decision["reason"])

    # Drop the internal ``gates`` dict from the public response – keep only what
    # the UI needs.
    result = {
        "symbol": sym,
        "interval": interval,
        "decision": decision["decision"],
        "reason": sanitized_reason,
        "entry": decision.get("entry"),
        "stop_loss": decision.get("stop_loss"),
        "target": decision.get("target"),
        "price": decision.get("price"),
        "regime": decision.get("regime"),
        "gates": decision.get("gates", {}),
        "stale": False,  # caller can add staleness check if desired
    }
    return result


# ---------------------------------------------------------------------------
#  Endpoint 2 – Chart data (candles + signals + SuperTrend)
# ---------------------------------------------------------------------------

@router.get("/chart", response_model=dict[str, Any])
async def fusion_chart(
    symbol: str = Query(..., min_length=1, max_length=16),
    interval: str = Query("5m", pattern=r"^(5m|15m|30m)$"),
    period: str = Query("1d", pattern=r"^(1d|5d|1mo|3mo|6mo|1y|5y|max)$"),
) -> dict[str, Any]:
    """Return candle data plus fusion signal markers and SuperTrend overlay.

    The payload is shaped for direct consumption by the frontend ``CandlestickChart``
    component (``web/components/dashboard/candlestick-chart.tsx``).  It contains:

    * ``candles`` – list of ``{time, open, high, low, close, volume}`` with real
      timestamps (ISO‑8601) so the chart can display intraday times correctly.
    * ``signals`` – per‑bar ``{time, side, reason}`` entries for BUY/SELL markers.
      HOLD bars are omitted so the chart isn't cluttered.
    * ``supertrend`` – the SuperTrend ``st_line`` values (one per candle) to
      render the trailing‑stop band as an overlay.
    * ``indicators`` – optional EMA / RSI / MACD values if the frontend wishes
      to keep its own client‑side overlays (currently the plan is to replace the
      client‑side scoring engine entirely, but the data is here for a smooth
      transition).
    """
    sym = _normalize_symbol(symbol)
    # Map the friendly ``period`` string to start / end dates for Yahoo.
    # Simple heuristics – production would use a proper calendar.
    today = datetime.now(tz_mod.utc).date()
    period_map = {
        "1d": (today - timedelta(days=1), today),
        "5d": (today - timedelta(days=5), today),
        "1mo": (today - timedelta(days=30), today),
        "3mo": (today - timedelta(days=90), today),
        "6mo": (today - timedelta(days=180), today),
        "1y": (today - timedelta(days=365), today),
        "5y": (today - timedelta(days=365 * 5), today),
        "max": (today - timedelta(days=365 * 10), today),
    }
    rng = period_map.get(period, (today - timedelta(days=30), today))
    start_date, end_date = rng

    points = await _fetch_candles(sym, interval=interval, start=start_date, end=end_date)

    if not points or len(points) < 60:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient candle data for {symbol}",
        )

    # ------------------------------------------------------------------
    #  Build indicator series (reuse IndicatorMath directly)
    # ------------------------------------------------------------------
    n = len(points)
    highs = [p.high for p in points]
    lows = [p.low for p in points]
    closes = [p.close for p in points]
    vols = [p.volume for p in points]

    from titan_x.services.technical_indicator_engine import IndicatorMath

    e9_vals = IndicatorMath.ema(closes, 9)
    e20_vals = IndicatorMath.ema(closes, 20)
    e50_vals = IndicatorMath.ema(closes, 50)
    rsi_vals = IndicatorMath.rsi(closes, 14)
    macd_line, macd_signal, macd_hist = IndicatorMath.macd(
        closes, 12, 26, 9
    )
    atr_vals = IndicatorMath.atr(highs, lows, closes, 14)
    st_dir, st_line = IndicatorMath.supertrend(highs, lows, closes, 10, 3.0)
    adx_line, pdi, mdi = IndicatorMath.adx(highs, lows, closes, 14)

    vol_sma = sum(vols[-20:]) / min(20, len(vols)) if len(vols) >= 20 else 0.0

    # ------------------------------------------------------------------
    #  Per‑bar signal series (markers) – BUY/SELL only (no HOLD clutter)
    # ------------------------------------------------------------------
    series: list[dict[str, Any]] = []
    warmup = 60
    for i in range(warmup, n):
        series.append({
            "time": item["time"],
            "side": item["side"],
            "reason": _sanitize_reason(item.get("reason", "Fusion signal")),
            "entry": item.get("entry"),
            "stop_loss": item.get("stop_loss"),
            "target": item.get("target"),
        })

    # ------------------------------------------------------------------
    #  Candles – use the point time if present, otherwise fall back to date.
    # ------------------------------------------------------------------
    candles = []
    for p in points:
        t = p.timestamp.isoformat() if p.timestamp else p.trade_date.isoformat()
        candles.append({
            "time": t,
            "open": p.open,
            "high": p.high,
            "low": p.low,
            "close": p.close,
            "volume": p.volume,
        })

    # ------------------------------------------------------------------
    #  SuperTrend line (same length as candles) for overlay rendering.
    # ------------------------------------------------------------------
    supertrend_vals = st_line if len(st_line) == n else [None] * n

    return {
        "symbol": sym,
        "interval": interval,
        "period": period,
        "candles": candles,
        "signals": series,
        "supertrend": supertrend_vals,
        "indicators": {
            "e9": e9_vals,
            "e20": e20_vals,
            "e50": e50_vals,
            "rsi": rsi_vals,
            "macd": macd_line,
            "macd_signal": macd_signal,
            "macd_hist": macd_hist,
            "atr": atr_vals,
            "adx": adx_line,
            "volume_sma": vol_sma,
        },
    }


# ---------------------------------------------------------------------------
#  Endpoint 3 – Backtest (intraday, with IS/OOS + walk-forward)
# ---------------------------------------------------------------------------

@router.post("/backtest", response_model=dict[str, Any])
async def fusion_backtest(
    symbol: str = Query(..., min_length=1, max_length=16),
    interval: str = Query("5m", pattern=r"^(5m|15m|30m)$"),
    start: date = Query(...),
    end: date = Query(...),
    initial_capital: float = Query(100_000.0, gt=0),
    commission_pct: float = Query(0.001, ge=0),
    slippage_pct: float = Query(0.001, ge=0),
    walk_forward: bool = Query(True),
) -> dict[str, Any]:
    """Run an intraday backtest for the Titan X Fusion strategy.

    The backtest uses the TitanXFusionEngine to generate BUY/SELL/HOLD decisions
    bar-by-bar over the intraday OHLCV series, with position management (entry /
    stop / target), slippage / commission, and equity-curve generation.  Results
    include standard metrics (win rate, profit factor, max drawdown) and, when
    ``walk_forward`` is ``True``, an in‑sample / out‑of‑sample split with per‑window
    decision counts.

    Returns a dict with:
    * ``total_return_pct``, ``win_rate``, ``profit_factor``, ``max_drawdown_pct``
    * ``trades`` list (entry/exit prices, pnl, holding time, exit reason)
    * ``equity_curve`` points (date, equity, cash, holdings value)
    * ``walk_forward`` object with in‑sample / out‑of‑sample bar counts and
      BUY/SELL decision tallies
    """
    sym = _normalize_symbol(symbol)

    # Fetch intraday candles
    points = await _fetch_candles(sym, interval=interval, start=start, end=end)
    if not points or len(points) < 60:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient data for {symbol} ({len(points) if points else 0} bars)",
        )

    # ------------------------------------------------------------------
    #  Prepare price arrays (all lists indexed by bar position, newest last)
    # ------------------------------------------------------------------
    n = len(points)
    highs = [p.high for p in points]
    lows = [p.low for p in points]
    closes = [p.close for p in points]
    opens = [p.open for p in points]
    vols = [p.volume for p in points]
    timestamps = [p.timestamp for p in points]

    # ------------------------------------------------------------------
    #  Core simulation loop
    # ------------------------------------------------------------------
    engine = TitanXFusionEngine(_params)

    cash = float(initial_capital)
    position: dict[str, Any] | None = None  # holds side, entry_price, sl, tgt, quantity, etc.
    trades: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []

    warmup = 60  # minimum bars needed for all indicators to stabilise

    # ------------------------------------------------------------------
    #  Iterate bars from warmup index onward
    # ------------------------------------------------------------------
    for i in range(warmup, n):
        # Use only confirmed data up to bar i (the engine already drops the forming bar)
        sub_points = points[: i + 1]

        # Evaluate the fusion engine at bar i
        decision = engine.evaluate(sub_points, dedupe=False)

        # ---------------------------------------------------
        #  Position management
        # ---------------------------------------------------
        if position is None:
            # Flat: if decision is BUY, schedule entry on the next bar's open
            if decision["decision"] == "BUY":
                if i + 1 < n:
                    position = {
                        "entry_bar": i + 1,          # will enter at bar i+1 open
                        "entry_price": None,         # to be filled at open[i+1] * (1+slippage)
                        "stop_loss": decision.get("stop_loss"),
                        "target": decision.get("target"),
                        "side": "long",
                        "decision_reason": decision["reason"],
                        "commission": 0.0,
                        "slippage": 0.0,
                    }
            # SELL while flat: ignored (no short in this basic model)
            elif decision["decision"] == "SELL":
                pass
        else:
            # We hold a position – check exit conditions on this bar
            entry_price = position.get("entry_price")
            sl = position.get("stop_loss")
            tp = position.get("target")

            if entry_price is not None and sl is not None and tp is not None:
                bar_low = lows[i]
                bar_high = highs[i]

                sl_hit = sl is not None and bar_low <= sl
                tp_hit = tp is not None and bar_high >= tp

                if sl_hit or tp_hit:
                    # Exit the position on this bar
                    exit_bar = i
                    # Priority: SL first if both hit same bar (conservative)
                    if sl_hit and tp_hit:
                        exit_price = sl  # SL takes priority
                    elif sl_hit:
                        exit_price = sl
                    elif tp_hit:
                        exit_price = tp
                    else:
                        exit_price = None

                    if exit_price is not None:
                        # Compute quantity: allocate 95% of cash at entry price
                        quantity = max(0.0, (cash * 0.95) / entry_price) if entry_price > 0 else 0.0
                        commission = quantity * exit_price * commission_pct
                        slippage_val = quantity * entry_price * slippage_pct

                        pnl = (exit_price - entry_price) * quantity - commission - slippage_val
                        pnl_pct = ((exit_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0.0
                        holding_days = (
                            (timestamps[exit_bar] - timestamps[position["entry_bar"]]).days
                            if position.get("entry_bar") is not None and exit_bar >= position["entry_bar"]
                            else 0
                        )

                        trades.append({
                            "entry_price": entry_price,
                            "exit_price": exit_price,
                            "pnl": pnl,
                            "pnl_pct": pnl_pct,
                            "holding_days": holding_days,
                            "side": "long",
                            "exit_reason": "stop_loss" if sl_hit else "take_profit",
                            "entry_bar": position["entry_bar"],
                            "exit_bar": exit_bar,
                        })

                        # Update cash (add proceeds, subtract commission + slippage)
                        cash += exit_price * quantity - commission
                        position = None  # flat again

            # If we have a pending entry from a prior iteration (entry_bar == i, entry_price not set yet),
            # finalise it by entering at this bar's open.
            if (
                position is not None
                and position.get("entry_bar") == i
                and position.get("entry_price") is None
            ):
                entry_price = opens[i] * (1 + slippage_pct)
                position = {
                    "entry_bar": i,
                    "entry_price": entry_price,
                    "stop_loss": position.get("stop_loss"),
                    "target": position.get("target"),
                    "side": "long",
                    "decision_reason": position.get("decision_reason"),
                    "commission": 0.0,
                    "slippage": entry_price - opens[i],
                }

        # ---------------------------------------------------
        #  Append mark-to-market equity curve point
        # ---------------------------------------------------
        holdings_value = 0.0
        if position is not None and position.get("entry_price") is not None:
            # Use the quantity that was proportion of cash at entry
            ep = position.get("entry_price", 0)
            if ep > 0:
                q = (cash * 0.95) / ep
                holdings_value = q * closes[i]
            elif "quantity" in position:
                holdings_value = position["quantity"] * closes[i]
        equity = cash + holdings_value
        equity_curve.append({
            "date": timestamps[i].isoformat() if timestamps[i] else points[i].trade_date.isoformat(),
            "equity": equity,
            "cash": cash,
            "holdings_value": holdings_value,
            "returns_pct": (
                (equity - initial_capital) / initial_capital * 100
                if i >= warmup else None
            ),
            "drawdown_pct": None,
        })

    # ---------------------------------------------------------------
    #  Post‑simulation metrics
    # ---------------------------------------------------------------
    closed_trades = [t for t in trades if t.get("pnl") is not None]
    winning_trades = [t for t in closed_trades if t.get("pnl", 0) > 0]
    losing_trades = [t for t in closed_trades if t.get("pnl", 0) <= 0]

    total_trades = len(closed_trades)
    win_rate = (len(winning_trades) / total_trades * 100) if total_trades else 0.0

    gross_profit = sum(t.get("pnl", 0) for t in winning_trades)
    gross_loss = abs(sum(t.get("pnl", 0) for t in losing_trades))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else None

    total_return_pct = sum(t.get("pnl_pct", 0) for t in closed_trades) if closed_trades else 0.0

    # Max drawdown from the equity curve
    max_dd = 0.0
    peak = initial_capital
    for point in equity_curve:
        peak = max(peak, point["equity"])
        dd = peak - point["equity"]
        if dd > max_dd:
            max_dd = dd
    max_drawdown_pct = (max_dd / initial_capital * 100) if initial_capital > 0 else 0.0

    # ---------------------------------------------------------------
    #  Walk‑forward / in‑sample / out‑of‑sample split (if requested)
    # ---------------------------------------------------------------
    iso_split_info: dict[str, Any] | None = None
    if walk_forward:
        # Split the bar series: first 60% = in-sample, last 40% = out-of-sample
        split_idx = int(n * 0.6)
        in_sample_points = points[:split_idx]
        out_of_sample_points = points[split_idx:]

        def _run_segment(seg_points: list[MarketDataPoint]) -> int:
            """Count non-HOLD decisions in a segment (lightweight eval)."""
            eng2 = TitanXFusionEngine(_params)
            count = 0
            for j in range(60, len(seg_points)):
                sub = seg_points[: j + 1]
                d = eng2.evaluate(sub, dedupe=False)
                if d["decision"] != "HOLD":
                    count += 1
            return count

        in_sample_count = _run_segment(in_sample_points)
        out_of_sample_count = _run_segment(out_of_sample_points)

        iso_split_info = {
            "split_point": (
                points[split_idx].trade_date.isoformat()
                if points[split_idx].trade_date
                else str(points[split_idx].timestamp.date())
            ),
            "in_sample_bars": len(in_sample_points),
            "out_of_sample_bars": len(out_of_sample_points),
            "in_sample_buy_sell_count": in_sample_count,
            "out_of_sample_buy_sell_count": out_of_sample_count,
        }

    # ---------------------------------------------------------------
    #  Return result
    # ---------------------------------------------------------------
    return {
        "symbol": sym,
        "interval": interval,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "initial_capital": initial_capital,
        "total_return_pct": total_return_pct,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "max_drawdown_pct": max_drawdown_pct,
        "total_trades": total_trades,
        "closed_trades": len(closed_trades),
        "trades": trades[-20:],  # last 20 trades for brevity
        "equity_curve_points": len(equity_curve),
        "walk_forward": iso_split_info,
        "bars_fetched": len(points),
        "warmup_bars": warmup,
    }