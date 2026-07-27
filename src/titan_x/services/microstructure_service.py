import json
import math
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.company import Company
from titan_x.models.microstructure import MarketMicrostructure
from titan_x.models.price import DailyPrice


class MicrostructureService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def analyze(
        self,
        symbol: str,
        as_of_date: date | None = None,
        delivery_quantity: int | None = None,
        total_traded_quantity: int | None = None,
    ) -> MarketMicrostructure:
        symbol = symbol.upper()
        if as_of_date is None:
            as_of_date = date.today()

        prices = await self._get_prices(symbol, as_of_date)

        if not prices:
            return await self._create_default(symbol, as_of_date)

        current = prices[-1]
        volume = current.volume
        close = current.close
        high = current.high
        low = current.low

        # ============================================================
        # VOLUME ANALYSIS
        # ============================================================
        volumes_20d = [p.volume for p in prices[-21:-1]] if len(prices) > 21 else [p.volume for p in prices[:-1]]
        volumes_5d = [p.volume for p in prices[-6:-1]] if len(prices) > 6 else volumes_20d

        avg_vol_5d = sum(volumes_5d) / len(volumes_5d) if volumes_5d else volume
        avg_vol_20d = sum(volumes_20d) / len(volumes_20d) if volumes_20d else volume
        vol_ratio = round(volume / avg_vol_20d, 4) if avg_vol_20d > 0 else 1.0

        vol_percentile = self._percentile(volume, volumes_20d) if volumes_20d else 50.0

        # volume trend: compare recent 5d avg vs 20d avg
        vol_trend = "stable"
        if avg_vol_5d > avg_vol_20d * 1.15:
            vol_trend = "rising"
        elif avg_vol_5d < avg_vol_20d * 0.85:
            vol_trend = "falling"

        # ============================================================
        # DELIVERY ANALYSIS
        # ============================================================
        delivery_pct = None
        delivery_trend = None
        delivery_score = None
        if delivery_quantity is not None and total_traded_quantity and total_traded_quantity > 0:
            delivery_pct = round(delivery_quantity / total_traded_quantity, 4)

            # compute trend from recent history
            deliveries = await self._get_recent_deliveries(symbol, as_of_date)
            if deliveries:
                recent_avg = sum(deliveries) / len(deliveries)
                if delivery_pct > recent_avg * 1.15:
                    delivery_trend = "rising"
                elif delivery_pct < recent_avg * 0.85:
                    delivery_trend = "falling"
                else:
                    delivery_trend = "stable"

            if delivery_pct is not None:
                delivery_score = round(min(100, delivery_pct * 200), 1)

        # ============================================================
        # SPREAD ANALYSIS (high-low proxy)
        # ============================================================
        spread_pct = round((high - low) / ((high + low) / 2) * 100, 4) if (high + low) > 0 else 0
        spreads_20d = []
        for p in prices[-21:-1]:
            hl = (p.high - p.low) / ((p.high + p.low) / 2) * 100 if (p.high + p.low) > 0 else 0
            spreads_20d.append(hl)
        spread_vol = self._std(spreads_20d) if spreads_20d else 0

        spread_regime = "moderate"
        if spread_pct < 1.0:
            spread_regime = "tight"
        elif spread_pct > 3.0:
            spread_regime = "wide"

        spread_score = round(max(0, min(100, 100 - spread_pct * 20)), 1)

        # ============================================================
        # MARKET DEPTH ANALYSIS
        # ============================================================
        dollar_vol = round(close * volume, 2)
        dol_vols_20d = [p.close * p.volume for p in prices[-21:-1]] if len(prices) > 21 else [p.close * p.volume for p in prices[:-1]]
        avg_dollar_vol_20d = sum(dol_vols_20d) / len(dol_vols_20d) if dol_vols_20d else dollar_vol
        depth_score = round(min(100, max(0, (dollar_vol / avg_dollar_vol_20d) * 50 if avg_dollar_vol_20d > 0 else 50)), 1)

        # ============================================================
        # TURNOVER ANALYSIS
        # ============================================================
        turnover = round(volume * close, 2)
        turnovers_20d = [p.volume * p.close for p in prices[-21:-1]] if len(prices) > 21 else [p.volume * p.close for p in prices[:-1]]
        avg_turnover_20d = sum(turnovers_20d) / len(turnovers_20d) if turnovers_20d else turnover
        turnover_ratio = round(turnover / avg_turnover_20d, 4) if avg_turnover_20d > 0 else 1.0

        free_float_turnover = None
        company_result = await self.session.execute(
            select(Company).where(Company.symbol == symbol)
        )
        company = company_result.scalar_one_or_none()
        if company and company.market_cap and company.market_cap > 0:
            free_float_turnover = round(turnover / company.market_cap, 6)

        # ============================================================
        # AMIHUD ILLIQUIDITY
        # ============================================================
        prev_close = prices[-2].close if len(prices) >= 2 else close
        daily_return = abs(close - prev_close) / prev_close if prev_close > 0 else 0
        amihud = round(daily_return / dollar_vol, 12) if dollar_vol > 0 else 0

        # ============================================================
        # COMPOSITE LIQUIDITY SCORE
        # ============================================================
        vol_component = min(100, vol_ratio * 50)
        depth_component = depth_score
        spread_component = spread_score
        delivery_component = delivery_score if delivery_score is not None else 50.0
        liq_score = round(vol_component * 0.25 + depth_component * 0.30 + spread_component * 0.25 + delivery_component * 0.20, 1)

        liq_rating = "high"
        if liq_score < 40:
            liq_rating = "low"
        elif liq_score < 60:
            liq_rating = "moderate"

        result = MarketMicrostructure(
            symbol=symbol,
            as_of_date=as_of_date,
            volume=volume,
            avg_volume_5d=int(avg_vol_5d),
            avg_volume_20d=int(avg_vol_20d),
            volume_ratio=vol_ratio,
            volume_percentile_20d=round(vol_percentile, 1),
            volume_trend=vol_trend,
            delivery_quantity=delivery_quantity,
            total_traded_quantity=total_traded_quantity,
            delivery_percentage=delivery_pct,
            delivery_trend=delivery_trend,
            delivery_score=delivery_score,
            avg_spread_pct=spread_pct,
            spread_volatility=round(spread_vol, 4),
            spread_regime=spread_regime,
            spread_score=spread_score,
            dollar_volume=dollar_vol,
            avg_dollar_volume_20d=round(avg_dollar_vol_20d, 2),
            depth_score=depth_score,
            turnover=turnover,
            avg_turnover_20d=round(avg_turnover_20d, 2),
            turnover_ratio=turnover_ratio,
            free_float_turnover=free_float_turnover,
            liquidity_score=liq_score,
            amihud_illiquidity=amihud,
            liquidity_rating=liq_rating,
            details_json=json.dumps({
                "close": close,
                "high": high,
                "low": low,
                "daily_return": round(daily_return, 6),
                "vol_component": round(vol_component, 1),
                "depth_component": depth_component,
                "spread_component": spread_component,
                "delivery_component": round(delivery_component, 1),
            }),
        )
        self.session.add(result)
        await self.session.flush()
        await self.session.refresh(result)
        return result

    async def get_analysis(self, symbol: str, as_of_date: date | None = None) -> MarketMicrostructure | None:
        symbol = symbol.upper()
        stmt = select(MarketMicrostructure).where(MarketMicrostructure.symbol == symbol)
        if as_of_date:
            stmt = stmt.where(MarketMicrostructure.as_of_date == as_of_date)
        stmt = stmt.order_by(MarketMicrostructure.as_of_date.desc()).limit(1)
        r = await self.session.execute(stmt)
        return r.scalar_one_or_none()

    async def list_analysis(self, symbol: str, limit: int = 30, offset: int = 0) -> list[MarketMicrostructure]:
        symbol = symbol.upper()
        r = await self.session.execute(
            select(MarketMicrostructure).where(MarketMicrostructure.symbol == symbol)
            .order_by(MarketMicrostructure.as_of_date.desc())
            .offset(offset).limit(limit)
        )
        return list(r.scalars().all())

    async def _get_prices(self, symbol: str, as_of_date: date) -> list[DailyPrice]:
        lookback = as_of_date - timedelta(days=60)
        r = await self.session.execute(
            select(DailyPrice).where(
                DailyPrice.symbol == symbol,
                DailyPrice.trade_date <= as_of_date,
                DailyPrice.trade_date >= lookback,
            ).order_by(DailyPrice.trade_date.asc())
        )
        return list(r.scalars().all())

    async def _get_recent_deliveries(self, symbol: str, as_of_date: date, lookback_days: int = 30) -> list[float]:
        lookback = as_of_date - timedelta(days=lookback_days)
        r = await self.session.execute(
            select(MarketMicrostructure).where(
                MarketMicrostructure.symbol == symbol,
                MarketMicrostructure.as_of_date < as_of_date,
                MarketMicrostructure.as_of_date >= lookback,
                MarketMicrostructure.delivery_percentage.isnot(None),
            ).order_by(MarketMicrostructure.as_of_date.asc())
        )
        return [m.delivery_percentage for m in r.scalars().all() if m.delivery_percentage is not None]

    def _percentile(self, value: float, values: list[float]) -> float:
        if not values:
            return 50.0
        below = sum(1 for v in values if v <= value)
        return below / len(values) * 100

    def _std(self, values: list[float]) -> float:
        if len(values) < 2:
            return 0
        mean = sum(values) / len(values)
        return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))

    async def _create_default(self, symbol: str, as_of_date: date) -> MarketMicrostructure:
        m = MarketMicrostructure(
            symbol=symbol,
            as_of_date=as_of_date,
            liquidity_score=0.0,
            liquidity_rating="low",
            details_json=json.dumps({"reason": "no_price_data"}),
        )
        self.session.add(m)
        await self.session.flush()
        await self.session.refresh(m)
        return m
