import json
import math
from datetime import date, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.market_breadth import MarketBreadth
from titan_x.models.price import DailyPrice
from titan_x.models.regime import MarketRegime, RegimeSignal


class RegimeDetectionService:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ============================================================
    # REGIME DETECTION
    # ============================================================

    async def detect_regime(self, symbol: str, as_of_date: date | None = None) -> MarketRegime:
        symbol = symbol.upper()
        if as_of_date is None:
            as_of_date = date.today()

        lookback = as_of_date - timedelta(days=400)

        price_result = await self.session.execute(
            select(DailyPrice).where(
                DailyPrice.symbol == symbol,
                DailyPrice.trade_date <= as_of_date,
                DailyPrice.trade_date >= lookback,
            ).order_by(DailyPrice.trade_date.asc())
        )
        prices = price_result.scalars().all()
        closes = [p.close for p in prices]
        dates_list = [p.trade_date for p in prices]
        volumes = [p.volume for p in prices]

        if len(closes) < 50:
            return await self._create_default_regime(symbol, as_of_date, "insufficient_data")

        current_price = closes[-1]

        # --- Trend Analysis ---
        sma_50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else current_price
        sma_200 = sum(closes[-200:]) / 200 if len(closes) >= 200 else current_price

        price_vs_sma_200 = (current_price - sma_200) / sma_200 if sma_200 > 0 else 0

        momentum_20d = (closes[-1] - closes[-21]) / closes[-21] if len(closes) >= 21 else 0
        momentum_50d = (closes[-1] - closes[-51]) / closes[-51] if len(closes) >= 51 else 0

        sma_20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else current_price

        trend_score = self._compute_trend_score(price_vs_sma_200, momentum_20d, momentum_50d, sma_50, sma_200, current_price)
        if trend_score >= 60:
            trend_regime = "bull"
        elif trend_score <= 40:
            trend_regime = "bear"
        else:
            trend_regime = "sideways"

        # --- Volatility Analysis ---
        returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
        vol_20d = self._compute_std(returns[-20:]) * math.sqrt(252) if len(returns) >= 20 else 0
        vol_60d_avg = self._compute_std(returns[-60:]) * math.sqrt(252) if len(returns) >= 60 else vol_20d
        vol_ratio = vol_20d / vol_60d_avg if vol_60d_avg > 0 else 1.0

        if vol_ratio > 1.3:
            volatility_regime = "high_volatility"
        elif vol_ratio < 0.7:
            volatility_regime = "low_volatility"
        else:
            volatility_regime = "normal_volatility"

        vol_score = min(100, max(0, vol_ratio * 50))

        # --- Sentiment Analysis ---
        breadth_data = await self._get_breadth_data(as_of_date)
        adv_decl_ratio = breadth_data.get("adv_decl_ratio")
        new_highs_vs_lows = breadth_data.get("new_highs_vs_lows")

        sentiment_score = self._compute_sentiment_score(trend_score, vol_ratio, adv_decl_ratio, new_highs_vs_lows)
        if sentiment_score >= 60:
            sentiment_regime = "risk_on"
        elif sentiment_score <= 40:
            sentiment_regime = "risk_off"
        else:
            sentiment_regime = "neutral"

        # --- Confidence ---
        confidence = self._compute_confidence(trend_score, vol_ratio, len(prices))

        regime = MarketRegime(
            symbol=symbol,
            as_of_date=as_of_date,
            trend_regime=trend_regime,
            volatility_regime=volatility_regime,
            sentiment_regime=sentiment_regime,
            trend_score=round(trend_score, 1),
            volatility_score=round(vol_score, 1),
            sentiment_score=round(sentiment_score, 1),
            momentum_20d=round(momentum_20d, 4),
            momentum_50d=round(momentum_50d, 4),
            sma_50=round(sma_50, 2),
            sma_200=round(sma_200, 2),
            price_vs_sma_200_pct=round(price_vs_sma_200, 4),
            volatility_20d=round(vol_20d, 4),
            volatility_60d_avg=round(vol_60d_avg, 4),
            adv_decl_ratio=round(adv_decl_ratio, 4) if adv_decl_ratio else None,
            new_highs_vs_lows=round(new_highs_vs_lows, 4) if new_highs_vs_lows else None,
            confidence=round(confidence, 2),
            details_json=json.dumps({
                "price_count": len(prices),
                "current_price": current_price,
                "sma_20": round(sma_20, 2),
                "vol_ratio": round(vol_ratio, 4),
            }),
        )
        self.session.add(regime)
        await self.session.flush()
        await self.session.refresh(regime)
        return regime

    # ============================================================
    # AI SIGNAL GENERATION
    # ============================================================

    async def generate_signal(self, symbol: str, as_of_date: date | None = None) -> RegimeSignal:
        symbol = symbol.upper()
        if as_of_date is None:
            as_of_date = date.today()

        regime = await self.get_regime(symbol, as_of_date)
        if regime is None:
            regime = await self.detect_regime(symbol, as_of_date)

        factors = []
        score = 50.0

        # Trend contribution (40%)
        if regime.trend_regime == "bull":
            score += 16 * (regime.trend_score / 100) if regime.trend_score else 12
            factors.append(f"Bullish trend (score {regime.trend_score:.0f}/100)")
        elif regime.trend_regime == "bear":
            score -= 16 * ((100 - (regime.trend_score or 0)) / 100)
            factors.append(f"Bearish trend (score {regime.trend_score:.0f}/100)")
        else:
            factors.append(f"Sideways trend (score {regime.trend_score:.0f}/100)")

        # Volatility contribution (30%)
        if regime.volatility_regime == "high_volatility":
            score -= 10
            factors.append("High volatility warning")
        elif regime.volatility_regime == "low_volatility":
            score += 8
            factors.append("Low volatility supports stability")

        # Sentiment contribution (30%)
        if regime.sentiment_regime == "risk_on":
            score += 12
            factors.append("Risk-on sentiment")
        elif regime.sentiment_regime == "risk_off":
            score -= 12
            factors.append("Risk-off sentiment")

        # Momentum boost
        if regime.momentum_20d and regime.momentum_20d > 0.05:
            score += 5
            factors.append("Strong 20-day momentum")
        elif regime.momentum_20d and regime.momentum_20d < -0.05:
            score -= 5
            factors.append("Weak 20-day momentum")

        score = max(0, min(100, score))

        if score >= 75:
            signal = "strong_buy"
        elif score >= 55:
            signal = "buy"
        elif score >= 40:
            signal = "hold"
        elif score >= 25:
            signal = "sell"
        else:
            signal = "strong_sell"

        confidence = regime.confidence * 0.7 + 0.3 * (abs(score - 50) / 50)
        confidence = round(min(1.0, confidence), 2)
        expiry = as_of_date + timedelta(days=5)

        regime_summary = f"{regime.trend_regime}/{regime.volatility_regime}/{regime.sentiment_regime}"

        reg_signal = RegimeSignal(
            symbol=symbol,
            as_of_date=as_of_date,
            regime_id=regime.id,
            signal=signal,
            confidence=confidence,
            regime_summary=regime_summary,
            supporting_factors=json.dumps(factors),
            expiry_date=expiry,
        )
        self.session.add(reg_signal)
        await self.session.flush()
        await self.session.refresh(reg_signal)
        return reg_signal

    # ============================================================
    # GETTERS
    # ============================================================

    async def get_regime(self, symbol: str, as_of_date: date | None = None) -> MarketRegime | None:
        symbol = symbol.upper()
        stmt = select(MarketRegime).where(MarketRegime.symbol == symbol)
        if as_of_date:
            stmt = stmt.where(MarketRegime.as_of_date == as_of_date)
        stmt = stmt.order_by(MarketRegime.as_of_date.desc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_regimes(self, symbol: str, limit: int = 30, offset: int = 0) -> list[MarketRegime]:
        symbol = symbol.upper()
        result = await self.session.execute(
            select(MarketRegime).where(MarketRegime.symbol == symbol)
            .order_by(MarketRegime.as_of_date.desc())
            .offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def get_signal(self, symbol: str, as_of_date: date | None = None) -> RegimeSignal | None:
        symbol = symbol.upper()
        stmt = select(RegimeSignal).where(RegimeSignal.symbol == symbol)
        if as_of_date:
            stmt = stmt.where(RegimeSignal.as_of_date == as_of_date)
        stmt = stmt.order_by(RegimeSignal.as_of_date.desc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_signals(self, symbol: str, limit: int = 30, offset: int = 0) -> list[RegimeSignal]:
        symbol = symbol.upper()
        result = await self.session.execute(
            select(RegimeSignal).where(RegimeSignal.symbol == symbol)
            .order_by(RegimeSignal.as_of_date.desc())
            .offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    # ============================================================
    # PRIVATE HELPERS
    # ============================================================

    def _compute_trend_score(self, price_vs_sma_200: float, momentum_20d: float, momentum_50d: float,
                             sma_50: float, sma_200: float, current_price: float) -> float:
        score = 50.0

        score += max(-20, min(20, price_vs_sma_200 * 200))
        score += max(-15, min(15, momentum_20d * 200))
        score += max(-15, min(15, momentum_50d * 100))

        if sma_200 > 0:
            sma_ratio = sma_50 / sma_200
            if sma_ratio > 1.0:
                score += 10
            elif sma_ratio < 0.95:
                score -= 10

        return max(0, min(100, score))

    def _compute_std(self, values: list[float]) -> float:
        if len(values) < 2:
            return 0
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return math.sqrt(variance)

    def _compute_sentiment_score(self, trend_score: float, vol_ratio: float,
                                 adv_decl_ratio: float | None, new_highs_vs_lows: float | None) -> float:
        score = trend_score * 0.5

        if adv_decl_ratio is not None:
            score += max(-15, min(15, (adv_decl_ratio - 1) * 30))

        if new_highs_vs_lows is not None:
            score += max(-10, min(10, new_highs_vs_lows * 10))

        if vol_ratio > 1.3:
            score -= 10

        return max(0, min(100, score))

    def _compute_confidence(self, trend_score: float, vol_ratio: float, price_count: int) -> float:
        conf = 0.5

        trend_strength = abs(trend_score - 50) / 50
        conf += trend_strength * 0.2

        if vol_ratio < 0.7 or vol_ratio > 1.3:
            conf += 0.1

        if price_count >= 200:
            conf += 0.15
        elif price_count >= 100:
            conf += 0.1
        elif price_count >= 50:
            conf += 0.05

        return min(1.0, max(0.1, conf))

    async def _get_breadth_data(self, as_of_date: date) -> dict:
        result = await self.session.execute(
            select(MarketBreadth).where(MarketBreadth.trade_date == as_of_date).limit(1)
        )
        mb = result.scalar_one_or_none()
        if mb is None:
            return {}

        adv_decl_ratio = mb.advance_decline_ratio
        new_highs_vs_lows = (mb.new_highs - mb.new_lows) / (mb.new_highs + mb.new_lows + 1)
        return {
            "adv_decl_ratio": adv_decl_ratio,
            "new_highs_vs_lows": new_highs_vs_lows,
        }

    async def _create_default_regime(self, symbol: str, as_of_date: date, reason: str) -> MarketRegime:
        regime = MarketRegime(
            symbol=symbol,
            as_of_date=as_of_date,
            trend_regime="sideways",
            volatility_regime="normal_volatility",
            sentiment_regime="neutral",
            trend_score=50.0, volatility_score=50.0, sentiment_score=50.0,
            confidence=0.1,
            details_json=json.dumps({"reason": reason}),
        )
        self.session.add(regime)
        await self.session.flush()
        await self.session.refresh(regime)
        return regime
