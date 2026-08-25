from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select

from titan_x.infrastructure.market_data_providers import StooqProvider, YahooFinanceProvider
from titan_x.models.company import Company
from titan_x.services.ai_recommendation_engine import AIRecommendationEngine, _technical_pillar, bars_from_records
from titan_x.services.intraday_recommendation_service import FNO_UNIVERSE, get_intraday_recommendations

STRICT_TECHNICAL_THRESHOLD = 95.0
MAX_MARKET_SCAN = 3000

_strict_state: dict[tuple[str, str], dict[str, Any]] = {}
_strict_tasks: dict[tuple[str, str], asyncio.Task] = {}
_strict_lock = asyncio.Lock()


def _daily_recommendation(symbol: str, points: list[Any]) -> tuple[float, dict] | None:
    if not points:
        return None
    bars = bars_from_records(points)
    technical = _technical_pillar(bars)
    if technical.score < STRICT_TECHNICAL_THRESHOLD or technical.direction == 0:
        return float(technical.score), {}

    # Delivery is intentionally independent from the intraday model.
    # The only recommendation gate here is the DELIVERY Technical Pillar >=95.
    engine = AIRecommendationEngine()
    try:
        rec = engine.build(symbol, bars)
    except Exception:
        rec = {}

    direction = "BUY" if technical.direction > 0 else "SELL"
    now = datetime.now().astimezone().isoformat()
    detail = technical.detail or {}
    item = {
        "id": f"strict-delivery-{symbol}",
        "symbol": symbol,
        "direction": direction,
        "signal": f"TECHNICAL_{direction}",
        "confidence": round(float(technical.confidence) * 100.0, 2),
        "price_target": rec.get("price_target"),
        "current_price": rec.get("current_price") or (bars[-1].close if bars else None),
        "timeframe": "Delivery / Short Term",
        "reasoning": "Delivery recommendation passed the Technical Pillar threshold.",
        "recommendation_type": "STRICT_DELIVERY",
        "status": "active",
        "score": round(float(technical.score), 2),
        "risk_level": rec.get("risk_level"),
        "predicted_return_pct": rec.get("expected_return_pct"),
        "source": "technical-delivery-live",
        "metadata_json": json.dumps({
            "signal": f"TECHNICAL_{direction}",
            "evidence": [
                f"Delivery Technical Pillar Score: {technical.score:.2f} / 100",
                "Recommendation gate: Delivery Technical Pillar >=95",
            ],
            "caution": ["Intraday Technical Pillar is not part of the Delivery gate."],
            "technical_detail": detail,
        }, default=str),
        "inputs_json": json.dumps({
            "technical": {
                "score": float(technical.score),
                "direction": int(technical.direction),
            }
        }),
        "generated_at": now,
        "created_at": now,
        "technical_score": round(float(technical.score), 2),
        "technical_pillar_score": round(float(technical.score), 2),
        "strict_technical_gate": True,
        "delivery_technical_score": round(float(technical.score), 2),
        "delivery_technical_pillar_score": round(float(technical.score), 2),
    }
    return float(technical.score), item


async def _daily_technical_gate(symbol: str, yahoo: YahooFinanceProvider, stooq: StooqProvider) -> tuple[float | None, dict]:
    points = None
    try:
        points = await yahoo.get_historical_prices(
            symbol, interval="1d", start=date.today() - timedelta(days=400), synthetic_ok=False
        )
    except Exception:
        points = None
    if not points:
        try:
            points = await stooq.get_historical_prices(
                symbol, interval="1d", start=date.today() - timedelta(days=400)
            )
        except Exception:
            points = None
    if not points:
        return None, {}
    result = _daily_recommendation(symbol, points)
    if result is None:
        return None, {}
    return result


async def _full_market_universe(session, segment: str) -> list[str]:
    if segment == "fno":
        return list(dict.fromkeys(FNO_UNIVERSE))
    rows = (
        await session.execute(
            select(Company.symbol)
            .where(Company.status == "active")
            .where(Company.exchange.in_(["NSE", "BSE"]))
            .order_by(Company.symbol.asc())
            .limit(MAX_MARKET_SCAN)
        )
    ).all()
    return list(dict.fromkeys(str(row[0]).upper().strip() for row in rows if row[0]))


async def _scan_daily_scores(symbols: list[str], state: dict[str, Any]) -> tuple[dict[str, float], dict[str, dict]]:
    yahoo = YahooFinanceProvider()
    stooq = StooqProvider()
    semaphore = asyncio.Semaphore(8)
    total = len(symbols)
    completed = 0

    async def scan(symbol: str):
        nonlocal completed
        async with semaphore:
            try:
                score, item = await _daily_technical_gate(symbol, yahoo, stooq)
                return symbol, score, item
            except Exception:
                return symbol, None, {}
            finally:
                completed += 1
                state["scanned"] = completed
                state["progress_pct"] = round(completed * 100.0 / max(total, 1), 1)

    try:
        results = await asyncio.gather(*(scan(symbol) for symbol in symbols))
    finally:
        await yahoo.close()
        await stooq.close()
    scores = {symbol: float(score) for symbol, score, _ in results if score is not None}
    items = {symbol: item for symbol, _, item in results if item}
    return scores, items


async def _compute_strict_recommendations(*, session, mode: str, segment: str, limit: int, state: dict[str, Any]) -> dict:
    universe_symbols = await _full_market_universe(session, segment)
    state["universe_size"] = len(universe_symbols)
    state["scan_scope"] = "FULL_ACTIVE_NSE_BSE_UNIVERSE" if segment == "equity" else "FULL_FNO_UNIVERSE"

    if mode == "intraday":
        result = await get_intraday_recommendations(
            segment=segment,
            limit=MAX_MARKET_SCAN,
            universe_symbols=universe_symbols,
        )
        qualified = []
        for item in result.get("recommendations", []):
            technical_score = float(item.get("technical_pillar_score") or item.get("technical_score") or 0.0)
            if item.get("direction") not in {"BUY", "SELL"} or technical_score < STRICT_TECHNICAL_THRESHOLD:
                continue
            item["technical_score"] = round(technical_score, 2)
            item["technical_pillar_score"] = round(technical_score, 2)
            item["strict_technical_gate"] = True
            qualified.append(item)
        qualified.sort(key=lambda r: (r.get("technical_pillar_score", 0.0), r.get("confidence", 0.0)), reverse=True)
        result["recommendations"] = qualified[:limit]
        result["universe_size"] = len(universe_symbols)
        result["scanned_universe"] = len(universe_symbols)
        result["strict_technical_threshold"] = STRICT_TECHNICAL_THRESHOLD
        result["strict_gate"] = "actual Intraday Technical pillar score >=95"
        result["scan_scope"] = "FULL_ACTIVE_NSE_BSE_UNIVERSE" if segment == "equity" else "FULL_FNO_UNIVERSE"
        return result

    if mode != "delivery":
        raise ValueError("mode must be delivery or intraday")

    # DELIVERY IS INDEPENDENT: do not run or require the intraday model.
    # A stock qualifies here solely because its Delivery Technical Pillar >=95.
    daily_scores, daily_items = await _scan_daily_scores(universe_symbols, state)
    daily_qualified = {
        symbol: score for symbol, score in daily_scores.items()
        if score >= STRICT_TECHNICAL_THRESHOLD and daily_items.get(symbol)
    }
    state["delivery_scored"] = len(daily_scores)
    state["delivery_qualified"] = len(daily_qualified)
    state["progress_pct"] = 100.0

    recommendations = [daily_items[symbol] for symbol in daily_qualified]
    recommendations.sort(
        key=lambda r: (r.get("delivery_technical_pillar_score", 0.0), r.get("confidence", 0.0)),
        reverse=True,
    )
    return {
        "mode": "delivery",
        "segment": segment,
        "generated_at": datetime.now().astimezone().isoformat(),
        "universe_size": len(universe_symbols),
        "scanned": len(universe_symbols),
        "delivery_scored": len(daily_scores),
        "delivery_qualified": len(daily_qualified),
        "intraday_scanned": 0,
        "recommendations": recommendations[:limit],
        "strict_technical_threshold": STRICT_TECHNICAL_THRESHOLD,
        "strict_gate": "Delivery Technical pillar score >=95 only; Intraday is independent",
        "scan_scope": "FULL_ACTIVE_NSE_BSE_UNIVERSE" if segment == "equity" else "FULL_FNO_UNIVERSE",
    }


async def _run_strict_scan(session_factory, mode: str, segment: str, limit: int) -> None:
    key = (mode, segment)
    state = _strict_state.setdefault(key, {})
    state.update({"running": True, "error": None, "scanned": 0, "progress_pct": 0.0, "started_at": datetime.now().astimezone().isoformat()})
    try:
        async with session_factory() as session:
            result = await _compute_strict_recommendations(
                session=session, mode=mode, segment=segment, limit=limit, state=state
            )
        state.update({"running": False, "result": result, "finished_at": datetime.now().astimezone().isoformat(), "error": None})
    except asyncio.CancelledError:
        state.update({"running": False, "error": "Scan cancelled"})
        raise
    except Exception as exc:
        state.update({"running": False, "error": f"{type(exc).__name__}: {exc}", "finished_at": datetime.now().astimezone().isoformat()})
    finally:
        _strict_tasks.pop(key, None)


async def get_strict_recommendations(*, session=None, session_factory=None, mode: str = "delivery", segment: str = "equity", limit: int = 100) -> dict:
    mode = mode.lower().strip()
    segment = segment.lower().strip()
    if mode not in {"delivery", "intraday"}:
        raise ValueError("mode must be delivery or intraday")
    if segment not in {"equity", "fno"}:
        raise ValueError("segment must be equity or fno")
    limit = max(1, min(int(limit), MAX_MARKET_SCAN))
    key = (mode, segment)

    state = _strict_state.get(key)
    if state and state.get("result") and not state.get("running"):
        result = dict(state["result"])
        result["scan_status"] = {k: v for k, v in state.items() if k != "result"}
        return result

    async with _strict_lock:
        state = _strict_state.setdefault(key, {})
        if not state.get("running"):
            if session_factory is None:
                if session is None:
                    raise ValueError("A database session or session factory is required")
                result = await _compute_strict_recommendations(session=session, mode=mode, segment=segment, limit=limit, state=state)
                state.update({"running": False, "result": result})
                return result
            _strict_tasks[key] = asyncio.create_task(_run_strict_scan(session_factory, mode, segment, limit))
            state.update({"running": True, "error": None, "scan_status": "started"})

    state = _strict_state[key]
    result = state.get("result") or {
        "mode": mode,
        "segment": segment,
        "generated_at": None,
        "universe_size": state.get("universe_size", 0),
        "scanned": state.get("scanned", 0),
        "recommendations": [],
        "strict_technical_threshold": STRICT_TECHNICAL_THRESHOLD,
        "strict_gate": "Delivery Technical pillar score >=95 only" if mode == "delivery" else "Intraday Technical pillar score >=95",
        "scan_scope": "FULL_ACTIVE_NSE_BSE_UNIVERSE" if segment == "equity" else "FULL_FNO_UNIVERSE",
    }
    result = dict(result)
    result["scan_status"] = {k: v for k, v in state.items() if k != "result"}
    result["scanning"] = bool(state.get("running"))
    return result


def get_strict_scan_status(mode: str, segment: str) -> dict[str, Any]:
    key = (mode.lower().strip(), segment.lower().strip())
    state = dict(_strict_state.get(key, {}))
    result = state.pop("result", None)
    if result:
        state["result_summary"] = {
            "universe_size": result.get("universe_size", 0),
            "scanned": result.get("scanned", 0),
            "recommendations": len(result.get("recommendations", [])),
            "generated_at": result.get("generated_at"),
        }
    return state
