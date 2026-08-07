import json
import uuid
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.chart_pattern import ChartPattern
from titan_x.models.company import Company
from titan_x.models.pattern_library import PATTERN_CATEGORIES, PatternDefinition, PatternInstance
from titan_x.models.price import DailyPrice

logger = structlog.get_logger(__name__)


class PatternLibraryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.def_repo = BaseRepository(session, PatternDefinition)
        self.inst_repo = BaseRepository(session, PatternInstance)

    async def create_definition(
        self, name: str, category: str, description: str | None = None,
        detection_params: dict | None = None, metadata_json: str | None = None,
    ) -> PatternDefinition:
        if category not in PATTERN_CATEGORIES:
            raise ValueError(f"Invalid category: {category}. Must be one of {PATTERN_CATEGORIES}")
        ai_id = f"AI-{uuid.uuid4().hex[:8].upper()}"
        definition = PatternDefinition(
            name=name, category=category, description=description,
            ai_pattern_id=ai_id,
            detection_params_json=json.dumps(detection_params) if detection_params else None,
            metadata_json=metadata_json or "{}",
        )
        self.session.add(definition)
        await self.session.flush()
        await self.session.refresh(definition)
        return definition

    async def list_definitions(
        self, category: str | None = None, active_only: bool = True,
        skip: int = 0, limit: int = 100,
    ) -> tuple[list[PatternDefinition], int]:
        stmt = select(PatternDefinition)
        if active_only:
            stmt = stmt.where(PatternDefinition.is_active == True)
        if category:
            stmt = stmt.where(PatternDefinition.category == category)
        count_result = await self.session.execute(stmt)
        total = len(count_result.scalars().all())
        stmt = stmt.order_by(PatternDefinition.category, PatternDefinition.name).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def detect_candlestick(
        self, symbol: str, end_date: date | None = None,
    ) -> list[PatternInstance]:
        if end_date is None:
            end_date = date.today()
        start = end_date - timedelta(days=30)
        result = await self.session.execute(
            select(DailyPrice).where(
                DailyPrice.symbol == symbol,
                DailyPrice.trade_date >= start,
                DailyPrice.trade_date <= end_date,
            ).order_by(DailyPrice.trade_date)
        )
        prices = list(result.scalars().all())
        if len(prices) < 2:
            return []

        defs_result = await self.session.execute(
            select(PatternDefinition).where(
                PatternDefinition.category == "candlestick",
                PatternDefinition.is_active == True,
            )
        )
        defs = list(defs_result.scalars().all())
        def_map = {d.name: d for d in defs}

        instances: list[PatternInstance] = []
        latest = prices[-1]
        prev = prices[-2] if len(prices) >= 2 else latest
        body = abs(latest.close - latest.open)
        range_total = latest.high - latest.low
        upper_shadow = latest.high - max(latest.open, latest.close)
        lower_shadow = min(latest.open, latest.close) - latest.low

        if body > 0 and range_total > 0:
            if body > range_total * 0.7 and latest.close > latest.open and lower_shadow < body * 0.1:
                instances.append(self._make_instance(defs, def_map, "marubozu", symbol, end_date, latest.close, 0.8))
            if upper_shadow > body * 2 and lower_shadow > body * 2 and body < range_total * 0.1:
                instances.append(self._make_instance(defs, def_map, "doji", symbol, end_date, latest.close, 0.7))
            if body > range_total * 0.6 and latest.close < latest.open and upper_shadow < body * 0.1:
                instances.append(self._make_instance(defs, def_map, "hanging_man", symbol, end_date, latest.close, 0.6))
            if body > range_total * 0.6 and latest.close > latest.open and upper_shadow < body * 0.1:
                instances.append(self._make_instance(defs, def_map, "hammer", symbol, end_date, latest.close, 0.6))
            if body > range_total * 0.6 and latest.close < latest.open and lower_shadow < body * 0.1:
                instances.append(self._make_instance(defs, def_map, "shooting_star", symbol, end_date, latest.close, 0.6))
            # engulfing
            if len(prices) >= 3:
                prev_body = abs(prev.close - prev.open)
                if prev_body > 0 and body > prev_body * 1.5:
                    if latest.close > latest.open and prev.close < prev.open and latest.close > prev.open and latest.open < prev.close:
                        instances.append(self._make_instance(defs, def_map, "bullish_engulfing", symbol, end_date, latest.close, 0.75))
                    if latest.close < latest.open and prev.close > prev.open and latest.close < prev.open and latest.open > prev.close:
                        instances.append(self._make_instance(defs, def_map, "bearish_engulfing", symbol, end_date, latest.close, 0.75))

        instances = [i for i in instances if i is not None]
        for inst in instances:
            self.session.add(inst)
        await self.session.flush()
        for inst in instances:
            await self.session.refresh(inst)
        return instances

    async def detect_volume(
        self, symbol: str, end_date: date | None = None,
    ) -> list[PatternInstance]:
        if end_date is None:
            end_date = date.today()
        start = end_date - timedelta(days=30)
        result = await self.session.execute(
            select(DailyPrice).where(
                DailyPrice.symbol == symbol,
                DailyPrice.trade_date >= start,
                DailyPrice.trade_date <= end_date,
            ).order_by(DailyPrice.trade_date)
        )
        prices = list(result.scalars().all())
        if len(prices) < 20:
            return []

        defs_result = await self.session.execute(
            select(PatternDefinition).where(
                PatternDefinition.category == "volume",
                PatternDefinition.is_active == True,
            )
        )
        defs = list(defs_result.scalars().all())
        def_map = {d.name: d for d in defs}
        instances: list[PatternInstance] = []

        volumes = [p.volume for p in prices[-20:]]
        avg_vol = sum(volumes) / len(volumes)
        latest = prices[-1]
        if latest.volume > avg_vol * 2:
            direction = "bullish" if latest.close > latest.open else "bearish"
            instances.append(self._make_instance(defs, def_map, "volume_spike", symbol, end_date, latest.close, 0.7, direction))

        if len(prices) >= 5:
            last_5 = [p.volume for p in prices[-5:]]
            avg_5 = sum(last_5) / len(last_5)
            if all(v < avg_vol * 0.5 for v in last_5):
                instances.append(self._make_instance(defs, def_map, "volume_dry_up", symbol, end_date, latest.close, 0.6))

            if len(prices) >= 10:
                prev_volumes = [p.volume for p in prices[-10:-5]]
                if prev_volumes and avg_5 > sum(prev_volumes) / len(prev_volumes) * 1.5:
                    instances.append(self._make_instance(defs, def_map, "volume_rising", symbol, end_date, latest.close, 0.65))

        instances = [i for i in instances if i is not None]
        for inst in instances:
            self.session.add(inst)
        await self.session.flush()
        for inst in instances:
            await self.session.refresh(inst)
        return instances

    async def detect_breakout(
        self, symbol: str, end_date: date | None = None,
    ) -> list[PatternInstance]:
        if end_date is None:
            end_date = date.today()
        start = end_date - timedelta(days=60)
        result = await self.session.execute(
            select(DailyPrice).where(
                DailyPrice.symbol == symbol,
                DailyPrice.trade_date >= start,
                DailyPrice.trade_date <= end_date,
            ).order_by(DailyPrice.trade_date)
        )
        prices = list(result.scalars().all())
        if len(prices) < 20:
            return []

        defs_result = await self.session.execute(
            select(PatternDefinition).where(
                PatternDefinition.category == "breakout",
                PatternDefinition.is_active == True,
            )
        )
        defs = list(defs_result.scalars().all())
        def_map = {d.name: d for d in defs}
        instances: list[PatternInstance] = []

        recent = prices[-20:]
        highs = [p.high for p in recent]
        lows = [p.low for p in recent]
        resistance = max(highs[:-1]) if len(highs) > 1 else highs[0]
        support = min(lows[:-1]) if len(lows) > 1 else lows[0]
        latest = prices[-1]

        if latest.close > resistance * 1.01 and latest.volume > sum(p.volume for p in recent[-5:]) / 5 * 1.2:
            instances.append(self._make_instance(defs, def_map, "breakout_above_resistance", symbol, end_date, latest.close, 0.8, "bullish"))
        if latest.close < support * 0.99 and latest.volume > sum(p.volume for p in recent[-5:]) / 5 * 1.2:
            instances.append(self._make_instance(defs, def_map, "breakdown_below_support", symbol, end_date, latest.close, 0.8, "bearish"))

        instances = [i for i in instances if i is not None]
        for inst in instances:
            self.session.add(inst)
        await self.session.flush()
        for inst in instances:
            await self.session.refresh(inst)
        return instances

    async def detect_gap(
        self, symbol: str, end_date: date | None = None,
    ) -> list[PatternInstance]:
        if end_date is None:
            end_date = date.today()
        start = end_date - timedelta(days=10)
        result = await self.session.execute(
            select(DailyPrice).where(
                DailyPrice.symbol == symbol,
                DailyPrice.trade_date >= start,
                DailyPrice.trade_date <= end_date,
            ).order_by(DailyPrice.trade_date)
        )
        prices = list(result.scalars().all())
        if len(prices) < 2:
            return []

        defs_result = await self.session.execute(
            select(PatternDefinition).where(
                PatternDefinition.category == "gap",
                PatternDefinition.is_active == True,
            )
        )
        defs = list(defs_result.scalars().all())
        def_map = {d.name: d for d in defs}
        instances: list[PatternInstance] = []

        latest = prices[-1]
        prev = prices[-2]
        gap_pct = (latest.open - prev.close) / prev.close * 100

        if gap_pct > 1.5:
            inst = self._make_instance(defs, def_map, "breakaway_gap", symbol, end_date, latest.close, min(abs(gap_pct) / 5, 0.9), "bullish")
            inst.entry_price = latest.open
            instances.append(inst)
        elif gap_pct < -1.5:
            inst = self._make_instance(defs, def_map, "breakaway_gap", symbol, end_date, latest.close, min(abs(gap_pct) / 5, 0.9), "bearish")
            inst.entry_price = latest.open
            instances.append(inst)
        elif 0.5 < gap_pct < 1.5:
            inst = self._make_instance(defs, def_map, "common_gap", symbol, end_date, latest.close, 0.5)
            inst.entry_price = latest.open
            instances.append(inst)
        elif -1.5 < gap_pct < -0.5:
            inst = self._make_instance(defs, def_map, "common_gap", symbol, end_date, latest.close, 0.5)
            inst.entry_price = latest.open
            instances.append(inst)

        if len(prices) >= 3:
            prev2 = prices[-3]
            gap1 = (prices[-2].open - prev2.close) / prev2.close * 100
            gap2 = gap_pct
            if gap1 > 1.5 and gap2 > 1.5:
                inst = self._make_instance(defs, def_map, "runaway_gap", symbol, end_date, latest.close, 0.75, "bullish")
                inst.entry_price = latest.open
                instances.append(inst)
            if gap1 < -1.5 and gap2 < -1.5:
                inst = self._make_instance(defs, def_map, "runaway_gap", symbol, end_date, latest.close, 0.75, "bearish")
                inst.entry_price = latest.open
                instances.append(inst)

        instances = [i for i in instances if i is not None]
        for inst in instances:
            self.session.add(inst)
        await self.session.flush()
        for inst in instances:
            await self.session.refresh(inst)
        return instances

    async def detect_trend(
        self, symbol: str, end_date: date | None = None,
    ) -> list[PatternInstance]:
        if end_date is None:
            end_date = date.today()
        start = end_date - timedelta(days=120)
        result = await self.session.execute(
            select(DailyPrice).where(
                DailyPrice.symbol == symbol,
                DailyPrice.trade_date >= start,
                DailyPrice.trade_date <= end_date,
            ).order_by(DailyPrice.trade_date)
        )
        prices = list(result.scalars().all())
        if len(prices) < 30:
            return []

        defs_result = await self.session.execute(
            select(PatternDefinition).where(
                PatternDefinition.category == "trend",
                PatternDefinition.is_active == True,
            )
        )
        defs = list(defs_result.scalars().all())
        def_map = {d.name: d for d in defs}
        instances: list[PatternInstance] = []

        closes = [p.close for p in prices]
        sma_20 = sum(closes[-20:]) / 20
        sma_50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else sma_20
        latest = prices[-1]

        if latest.close > sma_20 > sma_50:
            instances.append(self._make_instance(defs, def_map, "uptrend", symbol, end_date, latest.close, 0.7, "bullish"))
        elif latest.close < sma_20 < sma_50:
            instances.append(self._make_instance(defs, def_map, "downtrend", symbol, end_date, latest.close, 0.7, "bearish"))
        elif abs(latest.close - sma_20) / sma_20 < 0.02 and abs(sma_20 - sma_50) / sma_50 < 0.02:
            instances.append(self._make_instance(defs, def_map, "sideways", symbol, end_date, latest.close, 0.5))

        if len(closes) >= 50:
            highs = [p.high for p in prices[-50:]]
            lows = [p.low for p in prices[-50:]]
            range_50 = max(highs) - min(lows)
            avg_range = sum(p.high - p.low for p in prices[-50:]) / 50
            if avg_range > 0 and range_50 / avg_range < 2:
                instances.append(self._make_instance(defs, def_map, "consolidation", symbol, end_date, latest.close, 0.6))

        instances = [i for i in instances if i is not None]
        for inst in instances:
            self.session.add(inst)
        await self.session.flush()
        for inst in instances:
            await self.session.refresh(inst)
        return instances

    async def detect_all(
        self, symbol: str, end_date: date | None = None,
    ) -> dict[str, list[PatternInstance]]:
        return {
            "candlestick": await self.detect_candlestick(symbol, end_date),
            "volume": await self.detect_volume(symbol, end_date),
            "breakout": await self.detect_breakout(symbol, end_date),
            "gap": await self.detect_gap(symbol, end_date),
            "trend": await self.detect_trend(symbol, end_date),
        }

    async def get_instances(
        self, symbol: str | None = None, category: str | None = None,
        definition_id: int | None = None, active_only: bool = True,
        limit: int = 100, offset: int = 0,
    ) -> list[PatternInstance]:
        stmt = select(PatternInstance)
        if symbol:
            stmt = stmt.where(PatternInstance.symbol == symbol.upper())
        if category:
            stmt = stmt.where(PatternInstance.category == category)
        if definition_id:
            stmt = stmt.where(PatternInstance.definition_id == definition_id)
        if active_only:
            stmt = stmt.where(PatternInstance.is_active == True)
        stmt = stmt.order_by(desc(PatternInstance.end_date)).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_instances(
        self, symbol: str | None = None, category: str | None = None,
        definition_id: int | None = None, active_only: bool = True,
    ) -> int:
        stmt = select(func.count()).select_from(PatternInstance)
        if symbol:
            stmt = stmt.where(PatternInstance.symbol == symbol.upper())
        if category:
            stmt = stmt.where(PatternInstance.category == category)
        if definition_id:
            stmt = stmt.where(PatternInstance.definition_id == definition_id)
        if active_only:
            stmt = stmt.where(PatternInstance.is_active == True)
        return (await self.session.execute(stmt)).scalar() or 0

    async def get_instance_stats(
        self, definition_id: int, since: date | None = None,
    ) -> dict[str, Any]:
        stmt = select(PatternInstance).where(PatternInstance.definition_id == definition_id)
        if since:
            stmt = stmt.where(PatternInstance.end_date >= since)
        result = await self.session.execute(stmt)
        instances = list(result.scalars().all())
        total = len(instances)
        if not total:
            return {"total": 0}
        bullish = sum(1 for i in instances if i.direction == "bullish")
        bearish = sum(1 for i in instances if i.direction == "bearish")
        scores = [i.confidence_score for i in instances if i.confidence_score]
        return {
            "total": total,
            "unique_symbols": len(set(i.symbol for i in instances)),
            "bullish_count": bullish,
            "bearish_count": bearish,
            "avg_confidence": round(sum(scores) / len(scores), 4) if scores else None,
            "latest_date": max(i.end_date for i in instances),
        }

    def _make_instance(
        self, defs: list[PatternDefinition], def_map: dict[str, PatternDefinition],
        pattern_name: str, symbol: str, end_date: date, price: float,
        confidence: float, direction: str = "neutral",
    ) -> PatternInstance | None:
        definition = def_map.get(pattern_name)
        if not definition:
            for d in defs:
                if d.name == pattern_name:
                    definition = d
                    def_map[pattern_name] = d
                    break
        if not definition:
            return None
        return PatternInstance(
            definition_id=definition.id,
            symbol=symbol.upper(),
            category=definition.category,
            direction=direction,
            start_date=end_date - timedelta(days=5),
            end_date=end_date,
            entry_price=price,
            target_price=round(price * 1.05, 2) if direction == "bullish" else round(price * 0.95, 2),
            stop_loss=round(price * 0.97, 2) if direction == "bullish" else round(price * 1.03, 2),
            confidence_score=confidence,
            pattern_data_json=json.dumps({"pattern": pattern_name, "price": price}),
        )
