import json
import math
from datetime import date, timedelta
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.chart_pattern import SupportResistance
from titan_x.models.price import DailyPrice
from titan_x.models.price_target import PriceTarget
from titan_x.services.technical_indicator_engine import IndicatorMath

TARGET_MULTIPLIERS = (1.0, 2.0, 3.0)
BASE_PROBABILITIES = (0.65, 0.40, 0.20)
MIN_TARGET_PCT = 0.5
MAX_TARGET_PCT = 50.0


class PriceTargetService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def generate(
        self, symbol: str, direction: str = "bullish",
        entry_price: float | None = None,
    ) -> PriceTarget:
        symbol = symbol.upper()
        today = date.today()

        prices = await self._load_prices(symbol, today)
        if not prices:
            return await self._store_result(symbol, today, direction, entry_price or 0, None, [], None)

        current_price = prices[-1].close
        entry = entry_price or current_price

        closes = [p.close for p in prices]
        highs = [p.high for p in prices]
        lows = [p.low for p in prices]

        # ATR
        atr_values = IndicatorMath.atr(highs, lows, closes, 14)
        atr_val = atr_values[-1] if atr_values and atr_values[-1] is not None else None
        atr_pct = round(atr_val / current_price * 100, 2) if atr_val and current_price > 0 else None

        # Volatility
        vol_20d = None
        if len(closes) >= 20:
            returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(-19, 0)]
            vol_20d = self._std(returns) * math.sqrt(252)

        # Resistance levels
        resistance_levels = await self._get_resistance_levels(symbol)
        nearest_resistance = None
        resistance_strength = None
        if resistance_levels and current_price > 0:
            above = [r for r in resistance_levels if r["price"] > current_price]
            if above:
                nearest = min(above, key=lambda r: r["price"])
                nearest_resistance = nearest["price"]
                resistance_strength = nearest["strength"]

        # Compute targets
        targets = self._compute_targets(
            current_price, direction, atr_pct, vol_20d,
            nearest_resistance, atr_val,
        )

        # Expected holding days
        expected_holding_days = self._compute_holding_days(
            current_price, direction, atr_val, atr_pct, vol_20d, targets,
        )

        return await self._store_result(
            symbol, today, direction, entry, current_price,
            targets, expected_holding_days,
            atr_val, nearest_resistance, resistance_strength, vol_20d,
        )

    async def get_target(self, target_id: int) -> PriceTarget | None:
        r = await self.session.execute(
            select(PriceTarget).where(PriceTarget.id == target_id)
        )
        return r.scalar_one_or_none()

    async def get_targets(
        self, symbol: str, limit: int = 20, offset: int = 0,
    ) -> list[PriceTarget]:
        r = await self.session.execute(
            select(PriceTarget).where(PriceTarget.symbol == symbol.upper())
            .order_by(desc(PriceTarget.trade_date))
            .offset(offset).limit(limit)
        )
        return list(r.scalars().all())

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

    async def _get_resistance_levels(
        self, symbol: str,
    ) -> list[dict[str, Any]]:
        r = await self.session.execute(
            select(SupportResistance).where(
                SupportResistance.symbol == symbol,
                SupportResistance.level_type == "resistance",
                SupportResistance.is_active == True,
            ).order_by(desc(SupportResistance.strength_score))
        )
        levels = list(r.scalars().all())
        return [
            {"price": lev.price_level, "strength": lev.strength_score or 0}
            for lev in levels
        ]

    def _compute_targets(
        self, current_price: float, direction: str,
        atr_pct: float | None, vol_20d: float | None,
        nearest_resistance: float | None, atr_val: float | None,
    ) -> list[dict[str, Any]]:
        targets = []
        mult = 1.0 if direction == "bullish" else -1.0

        base_pct = atr_pct or (vol_20d * 100 if vol_20d else 2.0)
        base_pct = max(MIN_TARGET_PCT, min(MAX_TARGET_PCT, base_pct))

        for i in range(3):
            pct = base_pct * TARGET_MULTIPLIERS[i]
            price = round(current_price * (1 + mult * pct / 100), 2)
            prob = BASE_PROBABILITIES[i]

            # Adjust target 1 to nearest resistance if available and bullish
            if i == 0 and nearest_resistance is not None and direction == "bullish":
                if (mult > 0 and nearest_resistance > current_price):
                    resist_pct = (nearest_resistance - current_price) / current_price * 100
                    if resist_pct < pct * 1.5:
                        price = round(nearest_resistance, 2)
                        pct = round(resist_pct, 2)

            # Adjust target 2 to 2nd resistance zone for bullish
            if i == 1 and nearest_resistance is not None and direction == "bullish":
                if (mult > 0 and nearest_resistance > current_price):
                    pct_from_resist = pct - (nearest_resistance - current_price) / current_price * 100
                    price = round(current_price * (1 + mult * pct / 100), 2)

            pct = max(MIN_TARGET_PCT, min(MAX_TARGET_PCT, pct))
            targets.append({"price": price, "pct": round(pct, 2), "probability": round(prob, 2)})

        return targets

    def _compute_holding_days(
        self, current_price: float, direction: str,
        atr_val: float | None, atr_pct: float | None,
        vol_20d: float | None, targets: list[dict[str, Any]],
    ) -> int:
        if not targets:
            return 20
        target_pct = abs(targets[1]["pct"]) if len(targets) > 1 else abs(targets[0]["pct"])

        daily_move_pct = atr_pct if atr_pct else (vol_20d / math.sqrt(252) * 100 if vol_20d else 1.0)
        if daily_move_pct <= 0:
            return 20

        days = int(target_pct / daily_move_pct)
        return max(1, min(365, days))

    def _std(self, values: list[float]) -> float:
        if len(values) < 2:
            return 0
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return math.sqrt(variance)

    async def _store_result(
        self, symbol: str, trade_date: date, direction: str,
        entry_price: float, current_price: float | None,
        targets: list[dict[str, Any]], expected_holding_days: int | None,
        atr_val: float | None = None,
        nearest_resistance: float | None = None,
        resistance_strength: float | None = None,
        volatility_20d: float | None = None,
    ) -> PriceTarget:
        t1 = targets[0] if len(targets) > 0 else {}
        t2 = targets[1] if len(targets) > 1 else {}
        t3 = targets[2] if len(targets) > 2 else {}

        result = PriceTarget(
            symbol=symbol,
            trade_date=trade_date,
            direction=direction,
            entry_price=entry_price,
            current_price=current_price,
            target_1_price=t1.get("price"),
            target_1_pct=t1.get("pct"),
            target_1_probability=t1.get("probability"),
            target_2_price=t2.get("price"),
            target_2_pct=t2.get("pct"),
            target_2_probability=t2.get("probability"),
            target_3_price=t3.get("price"),
            target_3_pct=t3.get("pct"),
            target_3_probability=t3.get("probability"),
            expected_holding_days=expected_holding_days,
            method="composite",
            atr_value=atr_val,
            nearest_resistance=nearest_resistance,
            resistance_strength=resistance_strength,
            volatility_20d=volatility_20d,
            is_active=True,
            metadata_json=json.dumps({
                "entry_price": entry_price,
                "current_price": current_price,
                "direction": direction,
                "atr_value": atr_val,
                "nearest_resistance": nearest_resistance,
                "volatility_20d": volatility_20d,
            }),
        )
        self.session.add(result)
        await self.session.flush()
        await self.session.refresh(result)
        return result
