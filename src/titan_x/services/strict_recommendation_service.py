from __future__ import annotations

import asyncio
from datetime import date, timedelta

from sqlalchemy import select

from titan_x.infrastructure.market_data_providers import StooqProvider, YahooFinanceProvider
from titan_x.models.company import Company
from titan_x.models.recommendation import Recommendation
from titan_x.services.ai_recommendation_engine import _technical_pillar, bars_from_records
from titan_x.services.intraday_recommendation_service import FNO_UNIVERSE, get_intraday_recommendations

STRICT_TECHNICAL_THRESHOLD = 95.0
MAX_MARKET_SCAN = 3000


def _rec_dict(r: Recommendation, technical_score: float) -> dict:
    return {
        "id": r.id,
        "symbol": r.symbol,
        "direction": r.direction,
        "signal": r.signal,
        "confidence": r.confidence,
        "price_target": r.price_target,
        "current_price": r.current_price,
        "timeframe": r.timeframe,
        "reasoning": r.reasoning,
        "recommendation_type": r.recommendation_type,
        "status": r.status,
        "score": r.score,
        "risk_level": r.risk_level,
        "predicted_return_pct": r.predicted_return_pct,
        "source": r.source,
        "metadata_json": r.metadata_json,
        "model_version_id": r.model_version_id,
        "model_version_label": r.model_version_label,
        "decision": r.decision,
        "decision_reason": r.decision_reason,
        "decided_at": r.decided_at.isoformat() if r.decided_at else None,
        "outcome": r.outcome,
        "actual_outcome_pnl": r.actual_outcome_pnl,
        "outcome_details": r.outcome_details,
        "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
        "generated_at": r.generated_at.isoformat() if r.generated_at else None,
        "expires_at": r.expires_at.isoformat() if r.expires_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "technical_score": round(technical_score, 2),
        "technical_pillar_score": round(technical_score, 2),
        "strict_technical_gate": True,
    }


async def _daily_technical_gate(symbol: str, yahoo: YahooFinanceProvider, stooq: StooqProvider) -> float | None:
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
        return None
    return float(_technical_pillar(bars_from_records(points)).score)


async def _full_market_universe(session, segment: str) -> list[str]:
    """Return the complete scan universe, never the old 30-symbol fallback."""
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


async def _scan_daily_scores(symbols: list[str]) -> dict[str, float]:
    """Scan the full delivery universe with the same Technical Pillar engine."""
    yahoo = YahooFinanceProvider()
    stooq = StooqProvider()
    semaphore = asyncio.Semaphore(8)

    async def scan(symbol: str):
        async with semaphore:
            try:
                score = await _daily_technical_gate(symbol, yahoo, stooq)
                return symbol, score
            except Exception:
                return symbol, None

    try:
        pairs = await asyncio.gather(*(scan(symbol) for symbol in symbols))
    finally:
        await yahoo.close()
        await stooq.close()
    return {symbol: float(score) for symbol, score in pairs if score is not None}


async def get_strict_recommendations(*, session, mode: str = "delivery", segment: str = "equity", limit: int = 100) -> dict:
    """Return only stocks whose actual Technical Pillar Score is >=95.

    Delivery mode scans the complete active NSE/BSE universe first, then checks
    every daily-qualified symbol against the live 5-minute intraday engine.
    Intraday mode scans the complete same universe directly. Confidence is
    never used as a substitute for Technical Pillar Score.
    """
    mode = mode.lower().strip()
    segment = segment.lower().strip()
    limit = max(1, min(int(limit), MAX_MARKET_SCAN))
    universe_symbols = await _full_market_universe(session, segment)

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
        result["strict_gate"] = "actual Technical pillar score >=95 in intraday"
        result["scan_scope"] = "FULL_ACTIVE_NSE_BSE_UNIVERSE" if segment == "equity" else "FULL_FNO_UNIVERSE"
        return result

    if mode != "delivery":
        raise ValueError("mode must be delivery or intraday")

    # Full-market delivery scan. The old implementation only examined the
    # latest 500 Recommendation rows, which could hide qualifying companies.
    daily_scores = await _scan_daily_scores(universe_symbols)
    daily_qualified = {
        symbol: score for symbol, score in daily_scores.items() if score >= STRICT_TECHNICAL_THRESHOLD
    }

    # Only symbols that pass the delivery Technical Pillar gate need the more
    # expensive live 5-minute scan. This keeps the full-market scan practical.
    intraday = await get_intraday_recommendations(
        segment=segment,
        limit=MAX_MARKET_SCAN,
        universe_symbols=list(daily_qualified),
    )

    recommendations = []
    for intra in intraday.get("recommendations", []):
        symbol = intra.get("symbol")
        intraday_score = float(intra.get("technical_pillar_score") or intra.get("technical_score") or 0.0)
        delivery_score = daily_qualified.get(symbol)
        if delivery_score is None or delivery_score < STRICT_TECHNICAL_THRESHOLD:
            continue
        if intra.get("direction") not in {"BUY", "SELL"}:
            continue
        if intraday_score < STRICT_TECHNICAL_THRESHOLD:
            continue

        item = dict(intra)
        item["technical_score"] = round(intraday_score, 2)
        item["technical_pillar_score"] = round(intraday_score, 2)
        item["delivery_technical_score"] = round(delivery_score, 2)
        item["delivery_technical_pillar_score"] = round(delivery_score, 2)
        item["strict_technical_gate"] = True
        item["strict_gate_passed"] = True
        recommendations.append(item)

    recommendations.sort(
        key=lambda r: min(r["delivery_technical_pillar_score"], r["intraday_technical_pillar_score"]),
        reverse=True,
    )

    return {
        "mode": "delivery",
        "segment": segment,
        "generated_at": date.today().isoformat(),
        "universe_size": len(universe_symbols),
        "scanned": len(universe_symbols),
        "delivery_scored": len(daily_scores),
        "delivery_qualified": len(daily_qualified),
        "intraday_scanned": len(daily_qualified),
        "recommendations": recommendations[:limit],
        "strict_technical_threshold": STRICT_TECHNICAL_THRESHOLD,
        "strict_gate": "delivery Technical pillar score >=95 AND intraday Technical pillar score >=95",
        "scan_scope": "FULL_ACTIVE_NSE_BSE_UNIVERSE" if segment == "equity" else "FULL_FNO_UNIVERSE",
    }
