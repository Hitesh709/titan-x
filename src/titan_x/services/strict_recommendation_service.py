from __future__ import annotations

import asyncio
from datetime import date, timedelta

from sqlalchemy import select

from titan_x.infrastructure.market_data_providers import StooqProvider, YahooFinanceProvider
from titan_x.models.recommendation import Recommendation
from titan_x.services.ai_recommendation_engine import _technical_pillar, bars_from_records
from titan_x.services.intraday_recommendation_service import get_intraday_recommendations

STRICT_TECHNICAL_THRESHOLD = 95.0


def _technical_conviction(raw_score: float, direction: str) -> float:
    """Convert the 0..100 bullish technical score into directional conviction.

    BUY conviction is the bullish score; SELL conviction is the inverse score.
    This makes the strict 95+ rule symmetrical for both directions.
    """
    if direction == "BUY":
        return round(raw_score, 2)
    if direction == "SELL":
        return round(100.0 - raw_score, 2)
    return 0.0


def _rec_dict(r: Recommendation, technical_score: float, technical_conviction: float) -> dict:
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
        "technical_conviction_score": round(technical_conviction, 2),
        "strict_technical_gate": True,
    }


async def _daily_technical_gate(symbol: str) -> tuple[float, float] | None:
    yahoo = YahooFinanceProvider()
    stooq = StooqProvider()
    try:
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
        pillar = _technical_pillar(bars_from_records(points))
        raw = float(pillar.score)
        return raw, raw
    finally:
        await yahoo.close()
        await stooq.close()


async def get_strict_recommendations(
    *,
    session,
    mode: str = "delivery",
    segment: str = "equity",
    limit: int = 100,
) -> dict:
    """Return only actionable recommendations passing the 95+ technical gate.

    Delivery mode starts from Titan X's existing active delivery recommendations,
    verifies their live daily technical score, then verifies the same symbol's
    live 5-minute intraday technical conviction. Therefore a delivery result is
    shown only when BOTH delivery and intraday technical conviction are >=95.

    Intraday mode uses the existing full-universe 5-minute scanner and applies
    the same >=95 directional technical-conviction gate.
    """
    mode = mode.lower().strip()
    segment = segment.lower().strip()
    limit = max(1, min(int(limit), 3000))

    if mode == "intraday":
        result = await get_intraday_recommendations(
            segment=segment,
            limit=3000,
            universe_symbols=None,
        )
        qualified = []
        for item in result.get("recommendations", []):
            direction = item.get("direction")
            raw = float(item.get("score") or 0.0)
            conviction = _technical_conviction(raw, direction)
            if direction in {"BUY", "SELL"} and conviction >= STRICT_TECHNICAL_THRESHOLD:
                item["technical_score"] = raw
                item["technical_conviction_score"] = conviction
                item["strict_technical_gate"] = True
                qualified.append(item)
        result["recommendations"] = qualified[:limit]
        result["strict_technical_threshold"] = STRICT_TECHNICAL_THRESHOLD
        result["strict_gate"] = "technical_conviction >= 95 in intraday"
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

    semaphore = asyncio.Semaphore(6)

    async def verify(rec: Recommendation):
        async with semaphore:
            daily = await _daily_technical_gate(rec.symbol)
            if daily is None:
                return None
            raw_daily, _ = daily
            daily_conviction = _technical_conviction(raw_daily, rec.direction)
            if daily_conviction < STRICT_TECHNICAL_THRESHOLD:
                return None
            return rec, raw_daily, daily_conviction

    verified = await asyncio.gather(*(verify(r) for r in rows))
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
            "strict_gate": "delivery technical conviction >=95 AND intraday technical conviction >=95",
        }

    # Verify the SAME symbols on the live 5-minute model. This is the important
    # intersection: a stock must pass both time horizons before it is displayed.
    symbols = [x[0].symbol for x in delivery_candidates]
    intraday = await get_intraday_recommendations(
        segment="equity",
        limit=3000,
        universe_symbols=symbols,
    )
    intraday_by_symbol = {x["symbol"]: x for x in intraday.get("recommendations", [])}

    recommendations = []
    for rec, daily_raw, daily_conviction in delivery_candidates:
        intra = intraday_by_symbol.get(rec.symbol)
        if not intra:
            continue
        intra_conviction = _technical_conviction(
            float(intra.get("score") or 0.0),
            intra.get("direction"),
        )
        if intra.get("direction") not in {"BUY", "SELL"}:
            continue
        if intra_conviction < STRICT_TECHNICAL_THRESHOLD:
            continue
        if intra.get("direction") != rec.direction:
            continue
        item = _rec_dict(rec, daily_raw, daily_conviction)
        item["intraday_technical_score"] = round(float(intra.get("score") or 0.0), 2)
        item["intraday_technical_conviction_score"] = round(intra_conviction, 2)
        item["intraday"] = intra
        recommendations.append(item)

    recommendations.sort(
        key=lambda r: min(
            r["technical_conviction_score"],
            r["intraday_technical_conviction_score"],
        ),
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
        "strict_gate": "delivery technical conviction >=95 AND intraday technical conviction >=95",
    }
