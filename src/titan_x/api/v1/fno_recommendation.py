from __future__ import annotations

import asyncio
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query

from titan_x.api import deps
from titan_x.infrastructure.market_data_providers import YahooFinanceProvider
from titan_x.services.ai_recommendation_engine import AIRecommendationEngine, bars_from_records
from titan_x.services.technical_strength_engine import score_technical_strength

router = APIRouter(tags=["fno-recommendations"])

# Yahoo symbols for the liquid Indian index underlyings used for F&O strategy signals.
FNO_UNDERLYINGS = (
    ("NIFTY", "^NSEI", 50),
    ("BANKNIFTY", "^NSEBANK", 100),
    ("FINNIFTY", "^CNXFINANCE", 50),
    ("MIDCPNIFTY", "^NSEMDCP50", 25),
    ("SENSEX", "^BSESN", 100),
)
TECHNICAL_THRESHOLD = 95.0


def _atm(price: float | None, step: int) -> int | None:
    if price is None or price <= 0:
        return None
    return int(round(price / step) * step)


async def _one(name: str, yahoo_symbol: str, strike_step: int, provider: YahooFinanceProvider) -> dict | None:
    try:
        start = date.today() - timedelta(days=7)
        end = date.today() + timedelta(days=1)
        points = await provider.get_historical_prices(
            yahoo_symbol, interval="15m", start=start, end=end, synthetic_ok=False
        )
        if len(points) < 30:
            return None
        bars = bars_from_records(points)
        technical = await asyncio.to_thread(score_technical_strength, bars, mode="intraday")
        score = float(technical.score)
        if score < TECHNICAL_THRESHOLD or technical.direction not in ("BUY", "SELL"):
            return None
        quote = await provider.get_quote(yahoo_symbol)
        current = quote.get("last_price")
        current_num = float(current) if current is not None else None
        supporting = {}
        try:
            rec = AIRecommendationEngine().build(name, bars)
            supporting = rec if isinstance(rec, dict) else {}
        except Exception:
            pass
        direction = str(technical.direction).upper()
        option_bias = "CALL" if direction == "BUY" else "PUT"
        return {
            "symbol": name,
            "display_name": f"{name} F&O",
            "yahoo_symbol": yahoo_symbol,
            "segment": "fno",
            "instrument": "FUTURES",
            "direction": direction,
            "signal": technical.label,
            "score": round(score, 2),
            "technical_pillar_score": round(score, 2),
            "confidence": round(score, 2),
            "current_price": current_num,
            "entry_price": current_num,
            "target_price": technical.target_price if hasattr(technical, "target_price") else current_num,
            "stop_price": technical.stop_price if hasattr(technical, "stop_price") else current_num,
            "risk_reward": 0,
            "expected_return_pct": quote.get("change_percent"),
            "volume_ratio": None,
            "rsi": None,
            "ema20": None,
            "ema50": None,
            "option_bias": option_bias,
            "option_strike": _atm(current_num, strike_step),
            "timeframe": "intraday",
            "generated_at": date.today().isoformat(),
            "evidence": technical.evidence or [],
            "caution": ["F&O signal is derived from the underlying index. Verify live contract expiry, liquidity, spread and margin before trading."],
            "factors": technical.factors,
            "pillar_scores": supporting.get("pillar_scores") or supporting.get("pillars") or supporting.get("factors"),
            "technical_timeframes": [],
            "data_points": len(points),
            "interval": "15m",
            "window": "7d",
        }
    except Exception:
        return None


@router.get("/recommendations/fno")
async def fno_recommendations(
    limit: int = Query(100, ge=1, le=100),
    _: object = Depends(deps.get_current_active_user),
):
    provider = YahooFinanceProvider()
    try:
        results = await asyncio.gather(*(_one(*item, provider) for item in FNO_UNDERLYINGS))
        recommendations = [r for r in results if r]
        recommendations.sort(key=lambda r: float(r.get("score") or 0), reverse=True)
        return {
            "recommendations": recommendations[:limit],
            "count": min(limit, len(recommendations)),
            "segment": "fno",
            "instrument": "FUTURES_OPTIONS",
            "universe_size": len(FNO_UNDERLYINGS),
            "scanned": len(FNO_UNDERLYINGS),
            "technical_threshold": TECHNICAL_THRESHOLD,
            "strict_gate": "technical_pillar>=95",
            "interval": "15m",
            "window": "7d",
            "provider": "yahoo",
            "live": True,
        }
    finally:
        await provider.close()
