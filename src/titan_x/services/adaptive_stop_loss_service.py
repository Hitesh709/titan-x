import json
import math
from datetime import date, timedelta
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.adaptive_stop_loss import AdaptiveStopLoss
from titan_x.models.chart_pattern import SupportResistance
from titan_x.models.microstructure import MarketMicrostructure
from titan_x.models.price import DailyPrice
from titan_x.models.regime import MarketRegime
from titan_x.services.technical_indicator_engine import IndicatorMath

DEFAULT_ATR_MULTIPLIER = 2.0
DEFAULT_VOL_MULTIPLIER = 1.5
MIN_STOP_PCT = 0.5
MAX_STOP_PCT = 15.0
TRAILING_ACTIVATION_PCT = 5.0


class AdaptiveStopLossService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def compute(
        self, symbol: str, entry_price: float | None = None,
        atr_multiplier: float = DEFAULT_ATR_MULTIPLIER,
        vol_multiplier: float = DEFAULT_VOL_MULTIPLIER,
        trailing_activation_pct: float | None = TRAILING_ACTIVATION_PCT,
    ) -> AdaptiveStopLoss:
        symbol = symbol.upper()
        today = date.today()

        prices = await self._load_prices(symbol, today)
        if not prices:
            return await self._store_result(symbol, today, entry_price or 0, None)

        current_price = prices[-1].close
        entry = entry_price or current_price

        closes = [p.close for p in prices]
        highs = [p.high for p in prices]
        lows = [p.low for p in prices]
        volumes = [p.volume for p in prices]

        # 1) ATR
        atr_values = IndicatorMath.atr(highs, lows, closes, 14)
        atr_val = atr_values[-1] if atr_values and atr_values[-1] is not None else None
        sl_price_atr = None
        sl_pct_atr = None
        if atr_val is not None and current_price > 0:
            sl_price_atr = round(current_price - atr_val * atr_multiplier, 2)
            sl_pct_atr = round(atr_val * atr_multiplier / current_price * 100, 2)

        # 2) Support
        nearest_support = None
        support_distance_pct = None
        support_strength = None
        sl_price_support = None
        sl_pct_support = None
        support_levels = await self._get_support_levels(symbol)
        if support_levels and current_price > 0:
            below = [s for s in support_levels if s["price"] < current_price]
            if below:
                nearest = max(below, key=lambda s: s["price"])
                nearest_support = nearest["price"]
                support_strength = nearest["strength"]
                support_distance_pct = round((current_price - nearest_support) / current_price * 100, 2)
                sl_price_support = round(nearest_support * 0.99, 2)
                sl_pct_support = round((current_price - sl_price_support) / current_price * 100, 2)

        # 3) Volatility
        vol_20d = None
        vol_60d = None
        sl_price_vol = None
        sl_pct_vol = None
        if len(closes) >= 20:
            returns_20 = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(-19, 0)]
            vol_20d = self._std(returns_20) * math.sqrt(252)
        if len(closes) >= 60:
            returns_60 = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(-59, 0)]
            vol_60d = self._std(returns_60) * math.sqrt(252)
        if vol_20d is not None and current_price > 0:
            sl_price_vol = round(current_price * (1 - vol_20d * vol_multiplier), 2)
            sl_pct_vol = round(vol_20d * vol_multiplier * 100, 2)

        # 4) Market regime
        regime = await self._get_regime(symbol, today)
        trend_regime = regime.trend_regime if regime else None
        vol_regime = regime.volatility_regime if regime else None
        regime_adjustment = self._compute_regime_adjustment(regime)

        # 5) Liquidity
        liquidity = await self._get_liquidity(symbol, today)
        liq_score = liquidity.liquidity_score if liquidity else None
        liq_rating = liquidity.liquidity_rating if liquidity else None
        liq_adjustment = self._compute_liquidity_adjustment(liquidity)

        # 6) Composite
        base_pct = sl_pct_atr or sl_pct_vol or 5.0
        comp_pct = base_pct * (1 + regime_adjustment) * (1 - liq_adjustment)
        comp_pct = max(MIN_STOP_PCT, min(MAX_STOP_PCT, comp_pct))
        if sl_price_support is not None:
            support_pct = (current_price - sl_price_support) / current_price * 100
            comp_pct = min(comp_pct, support_pct * 1.1)
        comp_pct = max(MIN_STOP_PCT, min(MAX_STOP_PCT, comp_pct))
        composite_stop_price = round(current_price * (1 - comp_pct / 100), 2)
        composite_stop_pct = round(comp_pct, 2)

        method = "composite"

        return await self._store_result(
            symbol, today, entry, current_price,
            atr_val, atr_multiplier, sl_price_atr, sl_pct_atr,
            nearest_support, support_distance_pct, support_strength,
            sl_price_support, sl_pct_support,
            vol_20d, vol_60d, vol_multiplier, sl_price_vol, sl_pct_vol,
            trend_regime, vol_regime, regime_adjustment,
            liq_score, liq_rating, liq_adjustment,
            composite_stop_price, composite_stop_pct, method,
            trailing_activation_pct,
        )

    async def get_level(self, stop_loss_id: int) -> AdaptiveStopLoss | None:
        r = await self.session.execute(
            select(AdaptiveStopLoss).where(AdaptiveStopLoss.id == stop_loss_id)
        )
        return r.scalar_one_or_none()

    async def get_levels(
        self, symbol: str, limit: int = 20, offset: int = 0,
    ) -> list[AdaptiveStopLoss]:
        r = await self.session.execute(
            select(AdaptiveStopLoss).where(AdaptiveStopLoss.symbol == symbol.upper())
            .order_by(desc(AdaptiveStopLoss.trade_date))
            .offset(offset).limit(limit)
        )
        return list(r.scalars().all())

    async def get_active(self, symbol: str) -> AdaptiveStopLoss | None:
        r = await self.session.execute(
            select(AdaptiveStopLoss).where(
                AdaptiveStopLoss.symbol == symbol.upper(),
                AdaptiveStopLoss.is_active == True,
            ).order_by(desc(AdaptiveStopLoss.trade_date)).limit(1)
        )
        return r.scalar_one_or_none()

    async def deactivate(self, stop_loss_id: int) -> AdaptiveStopLoss | None:
        sl = await self.get_level(stop_loss_id)
        if sl:
            sl.is_active = False
            await self.session.flush()
            await self.session.refresh(sl)
        return sl

    # ---- private helpers ----

    async def _load_prices(
        self, symbol: str, as_of_date: date, lookback: int = 400,
    ) -> list[DailyPrice]:
        start = as_of_date - timedelta(days=lookback)
        r = await self.session.execute(
            select(DailyPrice).where(
                DailyPrice.symbol == symbol,
                DailyPrice.trade_date <= as_of_date,
                DailyPrice.trade_date >= start,
            ).order_by(DailyPrice.trade_date)
        )
        return list(r.scalars().all())

    async def _get_support_levels(
        self, symbol: str,
    ) -> list[dict[str, Any]]:
        r = await self.session.execute(
            select(SupportResistance).where(
                SupportResistance.symbol == symbol,
                SupportResistance.level_type == "support",
                SupportResistance.is_active == True,
            ).order_by(desc(SupportResistance.strength_score))
        )
        levels = list(r.scalars().all())
        return [
            {"price": lev.price_level, "strength": lev.strength_score or 0}
            for lev in levels
        ]

    async def _get_regime(
        self, symbol: str, as_of_date: date,
    ) -> MarketRegime | None:
        r = await self.session.execute(
            select(MarketRegime).where(
                MarketRegime.symbol == symbol,
                MarketRegime.as_of_date == as_of_date,
            ).limit(1)
        )
        regime = r.scalar_one_or_none()
        if regime:
            return regime
        r = await self.session.execute(
            select(MarketRegime).where(MarketRegime.symbol == symbol)
            .order_by(desc(MarketRegime.as_of_date)).limit(1)
        )
        return r.scalar_one_or_none()

    async def _get_liquidity(
        self, symbol: str, as_of_date: date,
    ) -> MarketMicrostructure | None:
        r = await self.session.execute(
            select(MarketMicrostructure).where(
                MarketMicrostructure.symbol == symbol,
                MarketMicrostructure.as_of_date == as_of_date,
            ).limit(1)
        )
        liq = r.scalar_one_or_none()
        if liq:
            return liq
        r = await self.session.execute(
            select(MarketMicrostructure).where(MarketMicrostructure.symbol == symbol)
            .order_by(desc(MarketMicrostructure.as_of_date)).limit(1)
        )
        return r.scalar_one_or_none()

    def _compute_regime_adjustment(
        self, regime: MarketRegime | None,
    ) -> float:
        if regime is None:
            return 0.0
        adj = 0.0
        if regime.trend_regime == "bull":
            adj -= 0.1
        elif regime.trend_regime == "bear":
            adj += 0.15
        if regime.volatility_regime == "high_volatility":
            adj += 0.2
        elif regime.volatility_regime == "low_volatility":
            adj -= 0.05
        return adj

    def _compute_liquidity_adjustment(
        self, liquidity: MarketMicrostructure | None,
    ) -> float:
        if liquidity is None or liquidity.liquidity_score is None:
            return 0.0
        score = liquidity.liquidity_score
        if score >= 80:
            return 0.15
        elif score >= 60:
            return 0.05
        elif score >= 40:
            return -0.05
        else:
            return -0.15

    def _std(self, values: list[float]) -> float:
        if len(values) < 2:
            return 0
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return math.sqrt(variance)

    async def _store_result(
        self, symbol: str, trade_date: date, entry_price: float,
        current_price: float | None = None,
        atr_val: float | None = None,
        atr_multiplier: float = DEFAULT_ATR_MULTIPLIER,
        sl_price_atr: float | None = None,
        sl_pct_atr: float | None = None,
        nearest_support: float | None = None,
        support_distance_pct: float | None = None,
        support_strength: float | None = None,
        sl_price_support: float | None = None,
        sl_pct_support: float | None = None,
        vol_20d: float | None = None,
        vol_60d: float | None = None,
        vol_multiplier: float = DEFAULT_VOL_MULTIPLIER,
        sl_price_vol: float | None = None,
        sl_pct_vol: float | None = None,
        trend_regime: str | None = None,
        volatility_regime: str | None = None,
        regime_adjustment: float | None = None,
        liq_score: float | None = None,
        liq_rating: str | None = None,
        liq_adjustment: float | None = None,
        composite_stop_price: float | None = None,
        composite_stop_pct: float | None = None,
        method: str = "composite",
        trailing_activation_pct: float | None = TRAILING_ACTIVATION_PCT,
    ) -> AdaptiveStopLoss:
        result = AdaptiveStopLoss(
            symbol=symbol,
            trade_date=trade_date,
            entry_price=entry_price,
            current_price=current_price,
            atr_value=atr_val,
            atr_multiplier=atr_multiplier,
            sl_price_atr=sl_price_atr,
            sl_pct_atr=sl_pct_atr,
            nearest_support=nearest_support,
            support_distance_pct=support_distance_pct,
            support_strength=support_strength,
            sl_price_support=sl_price_support,
            sl_pct_support=sl_pct_support,
            volatility_20d=vol_20d,
            volatility_60d=vol_60d,
            vol_multiplier=vol_multiplier,
            sl_price_volatility=sl_price_vol,
            sl_pct_volatility=sl_pct_vol,
            trend_regime=trend_regime,
            volatility_regime=volatility_regime,
            regime_adjustment=regime_adjustment,
            liquidity_score=liq_score,
            liquidity_rating=liq_rating,
            liq_adjustment=liq_adjustment,
            composite_stop_price=composite_stop_price,
            composite_stop_pct=composite_stop_pct,
            method=method,
            trailing_activation_pct=trailing_activation_pct,
            is_trailing=trailing_activation_pct is not None,
            is_active=True,
            metadata_json=json.dumps({
                "entry_price": entry_price,
                "current_price": current_price,
                "atr_value": atr_val,
                "nearest_support": nearest_support,
                "volatility_20d": vol_20d,
                "regime": trend_regime,
                "volatility_regime": volatility_regime,
                "regime_adjustment": regime_adjustment,
                "liquidity_score": liq_score,
                "liquidity_adjustment": liq_adjustment,
            }),
        )
        self.session.add(result)
        await self.session.flush()
        await self.session.refresh(result)
        return result
