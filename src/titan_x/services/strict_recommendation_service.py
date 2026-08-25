from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select

from titan_x.infrastructure.market_data_providers import StooqProvider, YahooFinanceProvider
from titan_x.models.company import Company
from titan_x.services.ai_recommendation_engine import AIRecommendationEngine, _technical_pillar, bars_from_records
from titan_x.services.intraday_recommendation_service import FNO_UNIVERSE, YAHOO_INDEX_TICKERS, _score_intraday

STRICT_TECHNICAL_THRESHOLD = 95.0
MAX_MARKET_SCAN = 3000

_strict_state: dict[tuple[str, str], dict[str, Any]] = {}
_strict_tasks: dict[tuple[str, str], asyncio.Task] = {}
_strict_lock = asyncio.Lock()

INDEX_DISPLAY_NAMES = {
    "NIFTY": "NIFTY 50",
    "BANKNIFTY": "NIFTY Bank",
    "SENSEX": "BSE SENSEX",
    "FINNIFTY": "NIFTY Financial Services",
    "MIDCPNIFTY": "NIFTY Midcap Select",
    "NIFTYNXT50": "NIFTY Next 50",
}


def _safe_score(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
        return value if value == value else default
    except (TypeError, ValueError):
        return default


def _technical_window(points: list[Any]) -> tuple[float, int, float, dict]:
    if not points:
        return 0.0, 0, 0.0, {}
    bars = bars_from_records(points)
    if not bars:
        return 0.0, 0, 0.0, {}
    pillar = _technical_pillar(bars)
    return _safe_score(pillar.score), int(pillar.direction), _safe_score(pillar.confidence), pillar.detail or {}


def _bar_time(bar: Any) -> datetime | None:
    value = getattr(bar, "timestamp", None)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.astimezone()
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _slice_since(bars: list[Any], days: int) -> list[Any]:
    if not bars:
        return []
    times = [t for t in (_bar_time(b) for b in bars) if t is not None]
    if not times:
        return bars
    latest = max(times)
    cutoff = latest - timedelta(days=days)
    return [b for b in bars if (t := _bar_time(b)) is not None and t >= cutoff]


def _multi_timeframe_technical(points_5m: list[Any], points_daily: list[Any] | None) -> tuple[float, int, float, dict]:
    """Build the Technical Pillar from multiple independent horizons.

    Intraday is not a single 5-minute candle score anymore. It combines:
    - 5m: last 24 hours
    - 5m: last 1 week
    - 5m: last 1 month
    - daily: last 1 month
    - daily: last 3 months

    _technical_pillar is deliberately reused for every window so RSI, EMA/trend,
    momentum, volume and the other technical components remain part of the score.
    The 5m windows carry the intraday weight; daily windows provide the 1m/3m trend context.
    """
    bars5 = bars_from_records(points_5m or [])
    barsd = bars_from_records(points_daily or [])
    if not bars5:
        return 0.0, 0, 0.0, {"error": "No 5m market data"}

    windows: list[tuple[str, list[Any], float]] = [
        ("5m_24h", _slice_since(bars5, 1), 0.30),
        ("5m_1w", _slice_since(bars5, 7), 0.25),
        ("5m_1m", _slice_since(bars5, 31), 0.20),
    ]
    if barsd:
        windows.extend([
            ("1d_1m", _slice_since(barsd, 31), 0.10),
            ("1d_3m", _slice_since(barsd, 100), 0.15),
        ])
    else:
        # Keep the score honest when the long-history provider fails: do not pretend
        # that a missing 3-month history was measured.
        windows[2] = ("5m_1m", windows[2][1], 0.35)

    parts: list[tuple[str, float, int, float, float, int]] = []
    for name, bars, weight in windows:
        if len(bars) < 8:
            continue
        score, direction, confidence, detail = _technical_window(bars)
        parts.append((name, score, direction, confidence, weight, len(bars)))

    if not parts:
        return 0.0, 0, 0.0, {"error": "Insufficient technical history"}

    total_weight = sum(p[4] for p in parts)
    weighted_score = sum(p[1] * p[4] for p in parts) / max(total_weight, 1e-9)
    weighted_direction = sum(p[2] * p[1] * p[4] for p in parts) / max(total_weight, 1e-9)
    direction = 1 if weighted_direction > 0 else -1 if weighted_direction < 0 else 0
    confidence = sum(p[3] * p[4] for p in parts) / max(total_weight, 1e-9)
    detail = {
        "method": "multi_timeframe_technical_pillar",
        "windows": [
            {"timeframe": p[0], "score": round(p[1], 2), "direction": p[2], "confidence": round(p[3], 4), "bars": p[5]}
            for p in parts
        ],
        "components": "RSI + volume + EMA/trend + momentum/other technical indicators from the technical pillar engine",
        "history_required": "5m 24h + 5m 1w + 5m 1m + daily 1m + daily 3m",
    }
    return round(max(0.0, min(100.0, weighted_score)), 2), direction, confidence, detail


def _daily_recommendation(symbol: str, points: list[Any]) -> tuple[float, dict] | None:
    if not points:
        return None
    bars = bars_from_records(points)
    technical = _technical_pillar(bars)
    if technical.score < STRICT_TECHNICAL_THRESHOLD or technical.direction == 0:
        return float(technical.score), {}
    engine = AIRecommendationEngine()
    try:
        rec = engine.build(symbol, bars)
    except Exception:
        rec = {}
    direction = "BUY" if technical.direction > 0 else "SELL"
    now = datetime.now().astimezone().isoformat()
    detail = technical.detail or {}
    factors = rec.get("factors") or {"technical": {"score": float(technical.score), "direction": int(technical.direction), "confidence": float(technical.confidence)}}
    item = {
        "id": f"strict-delivery-{symbol}", "symbol": symbol, "display_name": symbol,
        "direction": direction, "signal": f"TECHNICAL_{direction}",
        "confidence": round(float(technical.confidence) * 100.0, 2),
        "price_target": rec.get("price_target"), "current_price": rec.get("current_price") or (bars[-1].close if bars else None),
        "timeframe": "Delivery / Short Term", "reasoning": "Delivery recommendation passed the Delivery Technical Pillar threshold.",
        "recommendation_type": "STRICT_DELIVERY", "status": "active", "score": round(float(technical.score), 2),
        "risk_level": rec.get("risk_level"), "predicted_return_pct": rec.get("expected_return_pct"), "source": "technical-delivery-live",
        "metadata_json": json.dumps({"signal": f"TECHNICAL_{direction}", "evidence": [f"Delivery Technical Pillar Score: {technical.score:.2f} / 100", "Recommendation gate: Delivery Technical Pillar >=95"], "caution": ["Intraday Technical Pillar is not part of the Delivery gate."], "technical_detail": detail, "factors": factors}, default=str),
        "inputs_json": json.dumps(factors, default=str), "generated_at": now, "created_at": now,
        "technical_score": round(float(technical.score), 2), "technical_pillar_score": round(float(technical.score), 2),
        "strict_technical_gate": True, "delivery_technical_score": round(float(technical.score), 2), "delivery_technical_pillar_score": round(float(technical.score), 2),
    }
    return float(technical.score), item


async def _daily_technical_gate(symbol: str, yahoo: YahooFinanceProvider, stooq: StooqProvider) -> tuple[float | None, dict]:
    points = None
    try:
        points = await yahoo.get_historical_prices(symbol, interval="1d", start=date.today() - timedelta(days=400), synthetic_ok=False)
    except Exception:
        points = None
    if not points:
        try:
            points = await stooq.get_historical_prices(symbol, interval="1d", start=date.today() - timedelta(days=400))
        except Exception:
            points = None
    if not points:
        return None, {}
    return _daily_recommendation(symbol, points) or (None, {})


async def _full_market_universe(session, segment: str) -> list[str]:
    if segment == "fno":
        return list(dict.fromkeys(FNO_UNIVERSE))
    rows = (await session.execute(select(Company.symbol).where(Company.status == "active").where(Company.exchange.in_(["NSE", "BSE"])).order_by(Company.symbol.asc()).limit(MAX_MARKET_SCAN))).all()
    return list(dict.fromkeys(str(row[0]).upper().strip() for row in rows if row[0]))


async def _company_names(session, symbols: list[str]) -> dict[str, str]:
    if not symbols:
        return {}
    try:
        rows = (await session.execute(select(Company.symbol, Company.name).where(Company.symbol.in_(symbols)))).all()
        return {str(symbol).upper().strip(): str(name).strip() for symbol, name in rows if symbol and name}
    except Exception:
        return {}


async def _scan_daily_scores(symbols: list[str], state: dict[str, Any]) -> tuple[dict[str, float], dict[str, dict]]:
    yahoo, stooq = YahooFinanceProvider(), StooqProvider()
    semaphore = asyncio.Semaphore(8)
    total, completed = len(symbols), 0
    async def scan(symbol: str):
        nonlocal completed
        async with semaphore:
            try:
                score, item = await _daily_technical_gate(symbol, yahoo, stooq)
                return symbol, score, item
            except Exception:
                return symbol, None, {}
            finally:
                completed += 1; state["scanned"] = completed; state["progress_pct"] = round(completed * 100.0 / max(total, 1), 1)
    try:
        results = await asyncio.gather(*(scan(symbol) for symbol in symbols))
    finally:
        await yahoo.close(); await stooq.close()
    return ({symbol: float(score) for symbol, score, _ in results if score is not None}, {symbol: item for symbol, _, item in results if item})


async def _scan_intraday_scores(symbols: list[str], state: dict[str, Any], segment: str, session) -> list[dict]:
    provider = YahooFinanceProvider()
    semaphore = asyncio.Semaphore(6)
    total, completed = len(symbols), 0
    start_5m, end_5m = date.today() - timedelta(days=31), date.today() + timedelta(days=1)
    start_daily = date.today() - timedelta(days=400)
    names = await _company_names(session, symbols) if segment == "equity" else {}

    async def scan(display_symbol: str):
        nonlocal completed
        async with semaphore:
            try:
                ticker = YAHOO_INDEX_TICKERS.get(display_symbol, display_symbol)
                points_5m = await provider.get_historical_prices(ticker, interval="5m", start=start_5m, end=end_5m, synthetic_ok=False)
                if not points_5m:
                    return None
                # Daily history supplies the 1-month and 3-month context. This is kept
                # separate from the 5m feed so the Technical Pillar never confuses
                # intraday momentum with the longer trend.
                points_daily = await provider.get_historical_prices(ticker, interval="1d", start=start_daily, end=end_5m, synthetic_ok=False)
                technical_score, technical_direction, technical_confidence, technical_detail = _multi_timeframe_technical(points_5m, points_daily)
                if technical_score < STRICT_TECHNICAL_THRESHOLD or technical_direction == 0:
                    return None

                bars5 = bars_from_records(points_5m)
                scored = _score_intraday(points_5m) or {}
                direction = "BUY" if technical_direction > 0 else "SELL"
                try:
                    engine_rec = AIRecommendationEngine().build(display_symbol, bars5)
                except Exception:
                    engine_rec = {}
                factors = engine_rec.get("factors") or {"technical": {"score": technical_score, "direction": technical_direction, "confidence": technical_confidence}}
                name = INDEX_DISPLAY_NAMES.get(display_symbol, names.get(display_symbol, display_symbol))
                scored.update({
                    "symbol": display_symbol, "display_name": name, "direction": direction,
                    "technical_pillar_score": technical_score, "technical_score": technical_score,
                    "score": technical_score, "technical_confidence": technical_confidence,
                    "technical_timeframes": technical_detail.get("windows", []), "factors": factors,
                    "risk_level": engine_rec.get("risk_level") or ("Medium" if _safe_score(scored.get("risk_reward"), 0) < 2 else "Low"),
                    "generated_at": datetime.now().astimezone().isoformat(), "segment": segment,
                    "instrument": "INDEX" if display_symbol in YAHOO_INDEX_TICKERS else ("FUTURES" if segment == "fno" else "EQUITY"),
                    "option_bias": "CALL" if direction == "BUY" else "PUT", "option_strike": None,
                    "timeframe": "Intraday · 5m + 24h/1w/1m/3m technical context", "strict_technical_gate": True,
                    "evidence": [f"Multi-timeframe Technical Pillar: {technical_score:.2f}/100", "5m RSI/volume/momentum and trend windows: 24h, 1 week, 1 month", "Daily technical context: 1 month and 3 months"],
                })
                return scored
            except Exception:
                return None
            finally:
                completed += 1; state["scanned"] = completed; state["progress_pct"] = round(completed * 100.0 / max(total, 1), 1)
    try:
        results = await asyncio.gather(*(scan(symbol) for symbol in symbols))
    finally:
        await provider.close()
    qualified = [r for r in results if r is not None]
    qualified.sort(key=lambda r: (_safe_score(r.get("technical_pillar_score")), _safe_score(r.get("confidence"))), reverse=True)
    return qualified


async def _compute_strict_recommendations(*, session, mode: str, segment: str, limit: int, state: dict[str, Any]) -> dict:
    universe_symbols = await _full_market_universe(session, segment)
    state["universe_size"] = len(universe_symbols)
    state["scan_scope"] = "FULL_ACTIVE_NSE_BSE_UNIVERSE" if segment == "equity" else "FULL_FNO_UNIVERSE"
    if mode == "intraday":
        qualified = await _scan_intraday_scores(universe_symbols, state, segment, session)
        return {"mode": "intraday", "segment": segment, "generated_at": datetime.now().astimezone().isoformat(), "universe_size": len(universe_symbols), "scanned": len(universe_symbols), "recommendations": qualified[:limit], "strict_technical_threshold": STRICT_TECHNICAL_THRESHOLD, "strict_gate": "Intraday Technical pillar score >=95 only; Delivery is independent", "scan_scope": state["scan_scope"]}
    if mode != "delivery":
        raise ValueError("mode must be delivery or intraday")
    daily_scores, daily_items = await _scan_daily_scores(universe_symbols, state)
    daily_qualified = {symbol: score for symbol, score in daily_scores.items() if score >= STRICT_TECHNICAL_THRESHOLD and daily_items.get(symbol)}
    state["delivery_scored"] = len(daily_scores); state["delivery_qualified"] = len(daily_qualified); state["progress_pct"] = 100.0
    recommendations = [daily_items[symbol] for symbol in daily_qualified]
    recommendations.sort(key=lambda r: (_safe_score(r.get("delivery_technical_pillar_score")), _safe_score(r.get("confidence"))), reverse=True)
    return {"mode": "delivery", "segment": segment, "generated_at": datetime.now().astimezone().isoformat(), "universe_size": len(universe_symbols), "scanned": len(universe_symbols), "delivery_scored": len(daily_scores), "delivery_qualified": len(daily_qualified), "intraday_scanned": 0, "recommendations": recommendations[:limit], "strict_technical_threshold": STRICT_TECHNICAL_THRESHOLD, "strict_gate": "Delivery Technical pillar score >=95 only; Intraday is independent", "scan_scope": state["scan_scope"]}


async def _run_strict_scan(session_factory, mode: str, segment: str, limit: int) -> None:
    key = (mode, segment); state = _strict_state.setdefault(key, {})
    state.update({"running": True, "error": None, "scanned": 0, "progress_pct": 0.0, "started_at": datetime.now().astimezone().isoformat()})
    try:
        async with session_factory() as session:
            result = await _compute_strict_recommendations(session=session, mode=mode, segment=segment, limit=limit, state=state)
        state.update({"running": False, "result": result, "finished_at": datetime.now().astimezone().isoformat(), "error": None})
    except asyncio.CancelledError:
        state.update({"running": False, "error": "Scan cancelled"}); raise
    except Exception as exc:
        state.update({"running": False, "error": f"{type(exc).__name__}: {exc}", "finished_at": datetime.now().astimezone().isoformat()})
    finally:
        _strict_tasks.pop(key, None)


async def get_strict_recommendations(*, session=None, session_factory=None, mode: str = "delivery", segment: str = "equity", limit: int = 100) -> dict:
    mode, segment = mode.lower().strip(), segment.lower().strip()
    if mode not in {"delivery", "intraday"}: raise ValueError("mode must be delivery or intraday")
    if segment not in {"equity", "fno"}: raise ValueError("segment must be equity or fno")
    limit = max(1, min(int(limit), MAX_MARKET_SCAN)); key = (mode, segment)
    state = _strict_state.get(key)
    if state and state.get("result") and not state.get("running"):
        result = dict(state["result"]); result["scan_status"] = {k: v for k, v in state.items() if k != "result"}; result["scanning"] = False; return result
    async with _strict_lock:
        state = _strict_state.setdefault(key, {})
        if not state.get("running"):
            if session_factory is None:
                if session is None: raise ValueError("A database session or session factory is required")
                result = await _compute_strict_recommendations(session=session, mode=mode, segment=segment, limit=limit, state=state)
                state.update({"running": False, "result": result}); return result
            _strict_tasks[key] = asyncio.create_task(_run_strict_scan(session_factory, mode, segment, limit))
            state.update({"running": True, "error": None, "scan_status": "started"})
    state = _strict_state[key]
    result = state.get("result") or {"mode": mode, "segment": segment, "generated_at": None, "universe_size": state.get("universe_size", 0), "scanned": state.get("scanned", 0), "recommendations": [], "strict_technical_threshold": STRICT_TECHNICAL_THRESHOLD, "strict_gate": "Delivery Technical pillar score >=95 only" if mode == "delivery" else "Intraday Technical pillar score >=95 only", "scan_scope": "FULL_ACTIVE_NSE_BSE_UNIVERSE" if segment == "equity" else "FULL_FNO_UNIVERSE"}
    result = dict(result); result["scan_status"] = {k: v for k, v in state.items() if k != "result"}; result["scanning"] = bool(state.get("running")); return result


def get_strict_scan_status(mode: str, segment: str) -> dict[str, Any]:
    key = (mode.lower().strip(), segment.lower().strip()); state = dict(_strict_state.get(key, {})); result = state.pop("result", None)
    if result:
        state["result_summary"] = {"universe_size": result.get("universe_size", 0), "scanned": result.get("scanned", 0), "recommendations": len(result.get("recommendations", [])), "generated_at": result.get("generated_at")}
    return state
