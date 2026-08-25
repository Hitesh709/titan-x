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


async def _daily_technical_gate(
    symbol: str,
    yahoo: YahooFinanceProvider,
    stooq: StooqProvider,
) -> float | None:
    points = None
    try:
        points = await yahoo.get_historical_prices(
            symbol,
            interval="1d",
            start=date.today() - timedelta(days=400),
            synthetic_ok=False,
        )
    except Exception:
        points = None
    if not points:
        try:
            points = await stooq.get_historical_prices(
                symbol,
                interval="1d",
                start=date.today() - timedelta(days=400),
            )
        except Exception:
            points = None
    if not points:
        return None
    return float(_technical_pillar(bars_from_records(points)).score)


async def _full_market_universe(session, segment: str) -> list[str]:
    """Build the real scan universe instead of using the old 30-symbol fallback."""
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
    symbols = [str(row[0]).upper().strip() for row in rows if row[0]]
    return list(dict.fromkeys(symbols))


async def get_strict_recommendations(
    *,
    session,
    mode: str = "delivery",
    segment: str = "equity",
    limit: int = 100,
) -> dict:
    """Return only recommendations passing the actual Technical Pillar >=95 gate.

    IMPORTANT: every strict intraday request scans the complete active NSE/BSE
    universe (currently thousands of symbols), not the legacy 30-symbol list.
    Confidence is never substituted for Technical Pillar Score.
    """
    mode = mode.lower().strip()
    segment = segment.lower().strip()
    limit = max(1, min(int(limit), MAX_MARKET_SCAN))

    if mode == "intraday":
        universe_symbols = await _full_market_universe(session, segment)
        result = await get_intraday_recommendations(
            segment=segment,
            limit=MAX_MARKET_SCAN,
            universe_symbols=universe_symbols,
        )
        qualified = []
        for item in result.get("recommendations", []):
            direction = item.get("direction")
            technical_score = float(
                item.get("technical_pillar_score")
                if item.get("technical_pillar_score") is not None
                else item.get("technical_score") or 0.0
            )
            if direction not in {"BUY", "SELL"} or technical_score < STRICT_TECHNICAL_THRESHOLD:
                continue
            item["technical_score"] = round(technical_score, 2)
            item["technical_pillar_score"] = round(technical_score, 2)
            item["strict_technical_gate"] = True
            qualified.append(item)

        qualified.sort(
            key=lambda r: (
                r.get("technical_pillar_score", 0.0),
                r.get("confidence", 0.0),
            ),
            reverse=True,
        )
        result["recommendations"] = qualified[:limit]
        result["universe_size"] = len(universe_symbols)
        result["scanned_universe"] = len(universe_symbols)
        result["strict_technical_threshold"] = STRICT_TECHNICAL_THRESHOLD
        result["strict_gate"] = "actual Technical pillar score >=95 in intraday"
        result["scan_scope"] = "FULL_ACTIVE_NSE_BSE_UNIVERSE" if segment == "equity" else "FULL_FNO_UNIVERSE"
        return result

    if mode != "delivery":
        raise ValueError("mode must be delivery or intraday")

    rows = (
        await session.execute(
            select(Recommendation)
            .where(Recommendation.status == "active")
            .where(Recommendation.direction.in_(["BUY", "SELL"]))
            .order_by(Recommendation.generated_at.desc())
            .limit(500)
        )
    ).scalars().all()

    yahoo = YahooFinanceProvider()
    stooq = StooqProvider()
    semaphore = asyncio.Semaphore(6)
    try:
        async def verify(rec: Recommendation):
            async with semaphore:
                daily_score = await _daily_technical_gate(rec.symbol, yahoo, stooq)
                if daily_score is None or daily_score < STRICT_TECHNICAL_THRESHOLD:
                    return None
                return rec, daily_score

        verified = await asyncio.gather(*(verify(r) for r in rows))
    finally:
        await yahoo.close()
        await stooq.close()

    delivery_candidates = [x for x in verified if x is not None]
    if not delivery_candidates:
        return {
            "mode": "delivery",
            "segment": "equity",
            "generated_at": date.today().isoformat(),
            "universe_size": len(rows),
            "scanned": len(rows),
            "recommendations": [],
            "strict_technical_threshold": STRICT_TECHNICAL_THRESHOLD,
            "strict_gate": "delivery Technical pillar score >=95 AND intraday Technical pillar score >=95",
        }

    symbols = [x[0].symbol for x in delivery_candidates]
    intraday = await get_intraday_recommendations(
        segment="equity",
        limit=MAX_MARKET_SCAN,
        universe_symbols=symbols,
    )
    intraday_by_symbol = {x["symbol"]: x for x in intraday.get("recommendations", [])}

    recommendations = []
    for rec, daily_score in delivery_candidates:
        intra = intraday_by_symbol.get(rec.symbol)
        if not intra:
            continue
        intraday_score = float(
            intra.get("technical_pillar_score")
            if intra.get("technical_pillar_score") is not None
            else intra.get("technical_score") or 0.0
        )
        if intraday_score < STRICT_TECHNICAL_THRESHOLD:
            continue
        if intra.get("direction") not in {"BUY", "SELL"}:
            continue
        item = _rec_dict(rec, daily_score)
        item["intraday_technical_score"] = round(intraday_score, 2)
        item["intraday_technical_pillar_score"] = round(intraday_score, 2)
        item["intraday"] = intra
        recommendations.append(item)

    recommendations.sort(
        key=lambda r: min(r["technical_pillar_score"], r["intraday_technical_pillar_score"]),
        reverse=True,
    )

    return {
        "mode": "delivery",
        "segment": "equity",
        "generated_at": date.today().isoformat(),
        "universe_size": len(rows),
        "scanned": len(rows),
        "recommendations": recommendations[:limit],
        "strict_technical_threshold": STRICT_TECHNICAL_THRESHOLD,
        "strict_gate": "delivery Technical pillar score >=95 AND intraday Technical pillar score >=95",
    }
