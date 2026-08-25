from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta

from sqlalchemy import select

from titan_x.infrastructure.market_data_providers import StooqProvider, YahooFinanceProvider
from titan_x.models.recommendation import Recommendation
from titan_x.services.ai_recommendation_engine import _technical_pillar, bars_from_records
from titan_x.services.intraday_recommendation_service import YAHOO_INDEX_TICKERS, get_intraday_recommendations

STRICT_TECHNICAL_THRESHOLD = 95.0


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
    pillar = _technical_pillar(bars_from_records(points))
    return float(pillar.score)


async def _intraday_technical_scores(items: list[dict]) -> dict[str, float]:
    """Recalculate the exact Technical pillar used by Pillar Scores.

    The intraday scanner has its own market-structure score used to discover
    candidates. That score is NOT the six-pillar Technical score shown by the
    analyzer. Strict recommendations must use the latter, otherwise a card can
    display Technical=100 while the gate is actually testing a different score.
    """
    if not items:
        return {}

    provider = YahooFinanceProvider()
    semaphore = asyncio.Semaphore(8)
    start = date.today() - timedelta(days=30)
    end = date.today() + timedelta(days=1)

    async def calculate(item: dict) -> tuple[str, float | None]:
        symbol = str(item.get("symbol") or "").upper()
        ticker = YAHOO_INDEX_TICKERS.get(symbol, symbol)
        if not ticker:
            return symbol, None
        async with semaphore:
            try:
                points = await provider.get_historical_prices(
                    ticker,
                    interval="5m",
                    start=start,
                    end=end,
                    synthetic_ok=False,
                )
                if not points:
                    return symbol, None
                pillar = _technical_pillar(bars_from_records(points))
                return symbol, float(pillar.score)
            except Exception:
                return symbol, None

    try:
        pairs = await asyncio.gather(*(calculate(item) for item in items))
    finally:
        await provider.close()
    return {symbol: score for symbol, score in pairs if score is not None}


async def get_strict_recommendations(
    *,
    session,
    mode: str = "delivery",
    segment: str = "equity",
    limit: int = 100,
) -> dict:
    """Return recommendations only when the actual Technical pillar score is >=95.

    The gate uses the same ``_technical_pillar`` calculation rendered by the
    Symbol Analyzer's Pillar Scores section. It does NOT use confidence,
    probability, directional conviction, or the scanner's discovery score.

    Delivery mode requires the same stock to have Technical pillar score >=95
    on the daily/delivery model AND >=95 on the live 5-minute intraday model.
    Intraday mode applies the same >=95 Technical pillar score gate directly
    to the live 5-minute model.
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
        candidates = [
            item for item in result.get("recommendations", [])
            if item.get("direction") in {"BUY", "SELL"}
        ]
        technical_scores = await _intraday_technical_scores(candidates)
        qualified = []
        for item in candidates:
            symbol = str(item.get("symbol") or "").upper()
            technical_score = technical_scores.get(symbol)
            if technical_score is None or technical_score < STRICT_TECHNICAL_THRESHOLD:
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
        result["strict_technical_threshold"] = STRICT_TECHNICAL_THRESHOLD
        result["strict_gate"] = "actual Technical pillar score >=95 in intraday"
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
        limit=3000,
        universe_symbols=symbols,
    )
    intraday_candidates = [
        item for item in intraday.get("recommendations", [])
        if item.get("direction") in {"BUY", "SELL"}
    ]
    intraday_scores = await _intraday_technical_scores(intraday_candidates)
    intraday_by_symbol = {x["symbol"]: x for x in intraday_candidates}

    recommendations = []
    for rec, daily_score in delivery_candidates:
        intra = intraday_by_symbol.get(rec.symbol)
        if not intra:
            continue
        intraday_score = intraday_scores.get(rec.symbol)
        if intraday_score is None or intraday_score < STRICT_TECHNICAL_THRESHOLD:
            continue
        if intra.get("direction") not in {"BUY", "SELL"}:
            continue
        item = _rec_dict(rec, daily_score)
        item["intraday_technical_score"] = round(intraday_score, 2)
        item["intraday_technical_pillar_score"] = round(intraday_score, 2)
        item["intraday"] = {**intra, "technical_score": round(intraday_score, 2), "technical_pillar_score": round(intraday_score, 2)}
        recommendations.append(item)

    recommendations.sort(
        key=lambda r: min(
            r["technical_pillar_score"],
            r["intraday_technical_pillar_score"],
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
        "strict_gate": "delivery Technical pillar score >=95 AND intraday Technical pillar score >=95",
    }
