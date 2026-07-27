import json
import math
import statistics
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from titan_x.models.company import Company
from titan_x.models.feature_engineering import FeatureDefinition, FeatureValue
from titan_x.models.financial_analysis import AnnualResult, QuarterlyResult
from titan_x.models.market_breadth import MarketBreadth
from titan_x.models.macro import MacroFeature, MacroIndicator
from titan_x.models.news import NewsArticle
from titan_x.models.news_nlp import NewsNLPAnalysis
from titan_x.models.price import DailyPrice

logger = structlog.get_logger(__name__)

FEATURE_CATEGORIES = [
    "price", "volume", "momentum", "volatility",
    "financial", "news", "macro", "breadth",
]

DEFAULT_VERSION = "1.0.0"


class FeatureEngineeringService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._log = logger.bind(service="feature_engineering")

    # ============================================================
    # DEFINITION MANAGEMENT
    # ============================================================

    async def register_feature(
        self, name: str, category: str, *,
        description: str | None = None,
        formula: str | None = None,
        parameters: dict[str, Any] | None = None,
        source: str | None = None,
        version: str = DEFAULT_VERSION,
    ) -> FeatureDefinition:
        existing = await self.get_feature_definition(name, version)
        if existing:
            return existing
        fd = FeatureDefinition(
            name=name, category=category, version=version,
            description=description, formula=formula,
            parameters=json.dumps(parameters) if parameters else None,
            source=source, is_active=True,
        )
        self.session.add(fd)
        await self.session.flush()
        self._log.info("feature_registered", name=name, category=category, version=version)
        return fd

    async def get_feature_definition(
        self, name: str, version: str | None = None,
    ) -> FeatureDefinition | None:
        stmt = select(FeatureDefinition).where(FeatureDefinition.name == name)
        if version:
            stmt = stmt.where(FeatureDefinition.version == version)
        else:
            stmt = stmt.order_by(FeatureDefinition.version.desc()).limit(1)
        r = await self.session.execute(stmt)
        return r.scalar_one_or_none()

    async def list_definitions(
        self, category: str | None = None, active_only: bool = True,
    ) -> list[FeatureDefinition]:
        stmt = select(FeatureDefinition).order_by(FeatureDefinition.category, FeatureDefinition.name)
        if category:
            stmt = stmt.where(FeatureDefinition.category == category)
        if active_only:
            stmt = stmt.where(FeatureDefinition.is_active.is_(True))
        r = await self.session.execute(stmt)
        return list(r.scalars().all())

    async def create_new_version(
        self, name: str, *,
        description: str | None = None,
        formula: str | None = None,
        parameters: dict[str, Any] | None = None,
        source: str | None = None,
        change_notes: str | None = None,
    ) -> FeatureDefinition:
        latest = await self.get_feature_definition(name)
        parts = [int(x) for x in (latest.version.split(".") if latest else ["0", "0", "0"])]
        new_version = f"{parts[0]}.{parts[1]}.{parts[2] + 1}"
        fd = FeatureDefinition(
            name=name, category=latest.category if latest else "unknown",
            version=new_version, description=description or (latest.description if latest else None),
            formula=formula or (latest.formula if latest else None),
            parameters=json.dumps(parameters) if parameters else (latest.parameters if latest else None),
            source=source or (latest.source if latest else None),
            is_active=True,
        )
        self.session.add(fd)
        await self.session.flush()
        if latest:
            latest.is_active = False
        self._log.info("feature_version_created", name=name, version=new_version)
        return fd

    # ============================================================
    # VALUE STORAGE
    # ============================================================

    async def _upsert_value(
        self, definition_id: int, symbol: str, as_of_date: date,
        value: float, metadata: dict[str, Any] | None = None,
    ) -> FeatureValue:
        r = await self.session.execute(
            select(FeatureValue).where(
                FeatureValue.feature_definition_id == definition_id,
                FeatureValue.symbol == symbol,
                FeatureValue.as_of_date == as_of_date,
            )
        )
        existing = r.scalar_one_or_none()
        if existing:
            existing.value = value
            existing.metadata_json = json.dumps(metadata) if metadata else None
            return existing
        fv = FeatureValue(
            feature_definition_id=definition_id, symbol=symbol,
            as_of_date=as_of_date, value=value,
            metadata_json=json.dumps(metadata) if metadata else None,
        )
        self.session.add(fv)
        return fv

    async def get_values(
        self, symbol: str | None = None, feature_name: str | None = None,
        category: str | None = None, as_of_date: date | None = None,
        limit: int = 100, offset: int = 0,
    ) -> list[FeatureValue]:
        stmt = (
            select(FeatureValue)
            .options(joinedload(FeatureValue.definition))
            .join(FeatureDefinition)
        )
        if symbol:
            stmt = stmt.where(FeatureValue.symbol == symbol)
        if feature_name:
            stmt = stmt.where(FeatureDefinition.name == feature_name)
        if category:
            stmt = stmt.where(FeatureDefinition.category == category)
        if as_of_date:
            stmt = stmt.where(FeatureValue.as_of_date == as_of_date)
        stmt = stmt.order_by(FeatureValue.as_of_date.desc(), FeatureValue.symbol).offset(offset).limit(limit)
        r = await self.session.execute(stmt)
        return list(r.unique().scalars().all())

    # ============================================================
    # UTILITY HELPERS
    # ============================================================

    async def _get_or_create_definition(
        self, name: str, category: str, *,
        description: str | None = None,
        formula: str | None = None,
        parameters: dict[str, Any] | None = None,
        source: str | None = None,
    ) -> FeatureDefinition:
        existing = await self.get_feature_definition(name)
        if existing:
            return existing
        return await self.register_feature(
            name, category, description=description,
            formula=formula, parameters=parameters, source=source,
        )

    async def _get_prices(
        self, symbol: str, lookback: int, as_of_date: date,
    ) -> list[DailyPrice]:
        stmt = (
            select(DailyPrice)
            .where(
                DailyPrice.symbol == symbol,
                DailyPrice.trade_date <= as_of_date,
            )
            .order_by(DailyPrice.trade_date.desc())
            .limit(lookback)
        )
        r = await self.session.execute(stmt)
        return list(reversed(r.scalars().all()))

    def _compute_sma(self, values: list[float], period: int) -> float | None:
        if len(values) < period:
            return None
        return sum(values[-period:]) / period

    def _compute_ema(self, values: list[float], period: int) -> float | None:
        if len(values) < period:
            return None
        multiplier = 2.0 / (period + 1)
        ema = sum(values[:period]) / period
        for v in values[period:]:
            ema = (v - ema) * multiplier + ema
        return ema

    def _safe_div(self, a: float, b: float) -> float | None:
        if b is None or b == 0:
            return None
        return a / b

    # ============================================================
    # 1. PRICE FEATURES
    # ============================================================

    async def _compute_price_features(self, symbol: str, as_of_date: date) -> int:
        prices = await self._get_prices(symbol, 260, as_of_date)
        if len(prices) < 2:
            return 0
        closes = [p.close for p in prices]
        count = 0

        # price_return_1d
        if len(closes) >= 2:
            ret = self._safe_div(closes[-1] - closes[-2], closes[-2])
            if ret is not None:
                fd = await self._get_or_create_definition(
                    "price_return_1d", "price",
                    description="1-day price return", formula="(close - close[t-1]) / close[t-1]",
                    source="daily_price",
                )
                await self._upsert_value(fd.id, symbol, as_of_date, round(ret * 100, 4),
                                         {"lookback": 1, "close": closes[-1], "prev_close": closes[-2]})
                count += 1

        # price_return_5d
        if len(closes) >= 6:
            ret = self._safe_div(closes[-1] - closes[-6], closes[-6])
            if ret is not None:
                fd = await self._get_or_create_definition(
                    "price_return_5d", "price",
                    description="5-day price return", formula="(close - close[t-5]) / close[t-5]",
                    source="daily_price",
                )
                await self._upsert_value(fd.id, symbol, as_of_date, round(ret * 100, 4),
                                         {"lookback": 5})
                count += 1

        # price_return_20d
        if len(closes) >= 21:
            ret = self._safe_div(closes[-1] - closes[-21], closes[-21])
            if ret is not None:
                fd = await self._get_or_create_definition(
                    "price_return_20d", "price",
                    description="20-day price return", formula="(close - close[t-20]) / close[t-20]",
                    source="daily_price",
                )
                await self._upsert_value(fd.id, symbol, as_of_date, round(ret * 100, 4),
                                         {"lookback": 20})
                count += 1

        # log_return_1d
        if len(closes) >= 2 and closes[-2] > 0 and closes[-1] > 0:
            lr = math.log(closes[-1] / closes[-2])
            fd = await self._get_or_create_definition(
                "log_return_1d", "price",
                description="1-day log return", formula="ln(close / close[t-1])",
                source="daily_price",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(lr, 6),
                                     {"lookback": 1})
            count += 1

        # sma_20
        sma20 = self._compute_sma(closes, 20)
        if sma20 is not None:
            fd = await self._get_or_create_definition(
                "sma_20", "price",
                description="20-day simple moving average of close",
                formula="sum(close[-20:]) / 20", source="daily_price",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(sma20, 4))
            count += 1

        # sma_50
        sma50 = self._compute_sma(closes, 50)
        if sma50 is not None:
            fd = await self._get_or_create_definition(
                "sma_50", "price",
                description="50-day simple moving average of close",
                formula="sum(close[-50:]) / 50", source="daily_price",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(sma50, 4))
            count += 1

        # ema_12
        ema12 = self._compute_ema(closes, 12)
        if ema12 is not None:
            fd = await self._get_or_create_definition(
                "ema_12", "price",
                description="12-day exponential moving average of close",
                formula="EMA(close, 12)", source="daily_price",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(ema12, 4))
            count += 1

        # ema_26
        ema26 = self._compute_ema(closes, 26)
        if ema26 is not None:
            fd = await self._get_or_create_definition(
                "ema_26", "price",
                description="26-day exponential moving average of close",
                formula="EMA(close, 26)", source="daily_price",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(ema26, 4))
            count += 1

        # bollinger_width
        if sma20 is not None and len(closes) >= 20:
            recent = closes[-20:]
            stddev = statistics.stdev(recent)
            upper = sma20 + 2 * stddev
            lower = sma20 - 2 * stddev
            width = self._safe_div(upper - lower, sma20)
            if width is not None:
                fd = await self._get_or_create_definition(
                    "bollinger_width", "price",
                    description="Bollinger Band width (upper-lower)/sma_20",
                    formula="2*stddev(close,20)/sma_20", source="daily_price",
                    parameters={"stddev_mult": 2, "period": 20},
                )
                await self._upsert_value(fd.id, symbol, as_of_date, round(width, 6),
                                         {"upper": round(upper, 4), "lower": round(lower, 4), "sma_20": round(sma20, 4)})
                count += 1

        # price_position: (close - sma_20) / sma_20
        if sma20 is not None:
            pos = self._safe_div(closes[-1] - sma20, sma20)
            if pos is not None:
                fd = await self._get_or_create_definition(
                    "price_position", "price",
                    description="Price relative to 20-day SMA",
                    formula="(close - sma_20) / sma_20", source="daily_price",
                )
                await self._upsert_value(fd.id, symbol, as_of_date, round(pos, 6))
                count += 1

        return count

    # ============================================================
    # 2. VOLUME FEATURES
    # ============================================================

    async def _compute_volume_features(self, symbol: str, as_of_date: date) -> int:
        prices = await self._get_prices(symbol, 60, as_of_date)
        if len(prices) < 2:
            return 0
        volumes = [p.volume for p in prices]
        count = 0

        # volume_sma_5
        sma5 = self._compute_sma(volumes, 5)
        if sma5 is not None:
            fd = await self._get_or_create_definition(
                "volume_sma_5", "volume",
                description="5-day SMA of volume",
                formula="sum(volume[-5:]) / 5", source="daily_price",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(sma5, 2))
            count += 1

        # volume_sma_20
        sma20 = self._compute_sma(volumes, 20)
        if sma20 is not None:
            fd = await self._get_or_create_definition(
                "volume_sma_20", "volume",
                description="20-day SMA of volume",
                formula="sum(volume[-20:]) / 20", source="daily_price",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(sma20, 2))
            count += 1

        # volume_ratio_5: volume / volume_sma_5
        if sma5 is not None:
            vr = self._safe_div(volumes[-1], sma5)
            if vr is not None:
                fd = await self._get_or_create_definition(
                    "volume_ratio_5", "volume",
                    description="Volume ratio vs 5-day SMA",
                    formula="volume / sma_5(volume)", source="daily_price",
                )
                await self._upsert_value(fd.id, symbol, as_of_date, round(vr, 4))
                count += 1

        # volume_ratio_20
        if sma20 is not None:
            vr = self._safe_div(volumes[-1], sma20)
            if vr is not None:
                fd = await self._get_or_create_definition(
                    "volume_ratio_20", "volume",
                    description="Volume ratio vs 20-day SMA",
                    formula="volume / sma_20(volume)", source="daily_price",
                )
                await self._upsert_value(fd.id, symbol, as_of_date, round(vr, 4))
                count += 1

        # vwap_20: sum(typical_price * volume) / sum(volume)
        if len(prices) >= 20:
            recent = prices[-20:]
            total_tpv = sum((p.high + p.low + p.close) / 3 * p.volume for p in recent)
            total_vol = sum(p.volume for p in recent)
            vwap = self._safe_div(total_tpv, total_vol)
            if vwap is not None:
                fd = await self._get_or_create_definition(
                    "vwap_20", "volume",
                    description="20-day volume-weighted average price",
                    formula="sum(typical_price*volume) / sum(volume)", source="daily_price",
                )
                await self._upsert_value(fd.id, symbol, as_of_date, round(vwap, 4))
                count += 1

        # obv_change_1d
        obv = 0
        for i in range(1, len(prices)):
            if prices[i].close > prices[i - 1].close:
                obv += prices[i].volume
            elif prices[i].close < prices[i - 1].close:
                obv -= prices[i].volume
        if obv != 0:
            fd = await self._get_or_create_definition(
                "obv", "volume",
                description="On-Balance Volume (cumulative)",
                formula="cumulative signed volume based on close direction",
                source="daily_price",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(obv, 2),
                                     {"cumulative_period": len(prices)})
            count += 1

        return count

    # ============================================================
    # 3. MOMENTUM FEATURES
    # ============================================================

    async def _compute_momentum_features(self, symbol: str, as_of_date: date) -> int:
        prices = await self._get_prices(symbol, 260, as_of_date)
        if len(prices) < 15:
            return 0
        closes = [p.close for p in prices]
        highs = [p.high for p in prices]
        lows = [p.low for p in prices]
        count = 0

        # rsi_14
        if len(closes) >= 15:
            gains, losses = [], []
            for i in range(len(closes) - 14, len(closes)):
                if i == len(closes) - 14:
                    continue
                change = closes[i] - closes[i - 1]
                gains.append(max(change, 0))
                losses.append(max(-change, 0))
            avg_gain = sum(gains) / max(len(gains), 1)
            avg_loss = sum(losses) / max(len(losses), 1)
            if avg_loss != 0:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
            else:
                rsi = 100.0 if avg_gain > 0 else 50.0
            fd = await self._get_or_create_definition(
                "rsi_14", "momentum",
                description="14-day Relative Strength Index",
                formula="100 - (100 / (1 + avg_gain/avg_loss))", source="daily_price",
                parameters={"period": 14},
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(rsi, 4))
            count += 1

        # macd, macd_signal, macd_histogram
        if len(closes) >= 26:
            ema12 = self._compute_ema(closes, 12)
            ema26 = self._compute_ema(closes, 26)
            if ema12 is not None and ema26 is not None:
                macd = ema12 - ema26
                # signal line: 9-day EMA of MACD values
                macd_values = []
                for i in range(9, len(closes)):
                    e12 = self._compute_ema(closes[:i + 1], 12)
                    e26 = self._compute_ema(closes[:i + 1], 26)
                    if e12 is not None and e26 is not None:
                        macd_values.append(e12 - e26)
                if len(macd_values) >= 9:
                    signal = self._compute_ema(macd_values, 9)
                else:
                    signal = macd

                fd = await self._get_or_create_definition(
                    "macd", "momentum",
                    description="MACD line (12-26 EMA)",
                    formula="ema_12 - ema_26", source="daily_price",
                    parameters={"fast_period": 12, "slow_period": 26},
                )
                await self._upsert_value(fd.id, symbol, as_of_date, round(macd, 6))
                count += 1

                if signal is not None:
                    fd = await self._get_or_create_definition(
                        "macd_signal", "momentum",
                        description="MACD signal line (9-day EMA of MACD)",
                        formula="ema(macd, 9)", source="daily_price",
                        parameters={"signal_period": 9},
                    )
                    await self._upsert_value(fd.id, symbol, as_of_date, round(signal, 6))
                    count += 1

                    hist = macd - signal
                    fd = await self._get_or_create_definition(
                        "macd_histogram", "momentum",
                        description="MACD histogram (MACD - signal)",
                        formula="macd - signal", source="daily_price",
                    )
                    await self._upsert_value(fd.id, symbol, as_of_date, round(hist, 6))
                    count += 1

        # stoch_k, stoch_d
        if len(closes) >= 14:
            recent_h = max(highs[-14:])
            recent_l = min(lows[-14:])
            if recent_h != recent_l:
                stoch_k = 100 * (closes[-1] - recent_l) / (recent_h - recent_l)
            else:
                stoch_k = 50.0
            fd = await self._get_or_create_definition(
                "stoch_k", "momentum",
                description="Stochastic %K (14-day)",
                formula="100 * (close - low_14) / (high_14 - low_14)",
                source="daily_price", parameters={"period": 14},
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(stoch_k, 4))
            count += 1

            # stoch_d: 3-day SMA of stoch_k (simplified)
            stoch_values = []
            for i in range(14, len(highs)):
                hh = max(highs[i - 13:i + 1])
                ll = min(lows[i - 13:i + 1])
                stoch_values.append(100 * (closes[i] - ll) / (hh - ll) if hh != ll else 50.0)
            stoch_d = self._compute_sma(stoch_values, 3)
            if stoch_d is not None:
                fd = await self._get_or_create_definition(
                    "stoch_d", "momentum",
                    description="Stochastic %D (3-day SMA of %K)",
                    formula="sma(stoch_k, 3)", source="daily_price",
                    parameters={"smoothing_period": 3},
                )
                await self._upsert_value(fd.id, symbol, as_of_date, round(stoch_d, 4))
                count += 1

        # roc_10
        if len(closes) >= 11:
            roc = self._safe_div(closes[-1] - closes[-11], closes[-11])
            if roc is not None:
                fd = await self._get_or_create_definition(
                    "roc_10", "momentum",
                    description="10-day Rate of Change",
                    formula="(close - close[t-10]) / close[t-10] * 100",
                    source="daily_price", parameters={"period": 10},
                )
                await self._upsert_value(fd.id, symbol, as_of_date, round(roc * 100, 4))
                count += 1

        return count

    # ============================================================
    # 4. VOLATILITY FEATURES
    # ============================================================

    async def _compute_volatility_features(self, symbol: str, as_of_date: date) -> int:
        prices = await self._get_prices(symbol, 120, as_of_date)
        if len(prices) < 15:
            return 0
        closes = [p.close for p in prices]
        highs = [p.high for p in prices]
        lows = [p.low for p in prices]
        count = 0

        # historical_vol_20: annualized std of log returns
        if len(closes) >= 21:
            log_rets = []
            for i in range(len(closes) - 20, len(closes)):
                if i > len(closes) - 20 and closes[i - 1] > 0:
                    log_rets.append(math.log(closes[i] / closes[i - 1]))
            if len(log_rets) >= 2:
                hv20 = statistics.stdev(log_rets) * math.sqrt(252)
                fd = await self._get_or_create_definition(
                    "historical_vol_20", "volatility",
                    description="20-day annualized historical volatility",
                    formula="std(log_returns, 20) * sqrt(252)",
                    source="daily_price", parameters={"period": 20, "annualization": 252},
                )
                await self._upsert_value(fd.id, symbol, as_of_date, round(hv20, 6))
                count += 1

        # historical_vol_60
        if len(closes) >= 61:
            log_rets = []
            for i in range(len(closes) - 60, len(closes)):
                if i > len(closes) - 60 and closes[i - 1] > 0:
                    log_rets.append(math.log(closes[i] / closes[i - 1]))
            if len(log_rets) >= 2:
                hv60 = statistics.stdev(log_rets) * math.sqrt(252)
                fd = await self._get_or_create_definition(
                    "historical_vol_60", "volatility",
                    description="60-day annualized historical volatility",
                    formula="std(log_returns, 60) * sqrt(252)",
                    source="daily_price", parameters={"period": 60, "annualization": 252},
                )
                await self._upsert_value(fd.id, symbol, as_of_date, round(hv60, 6))
                count += 1

        # atr_14
        if len(prices) >= 15:
            tr_values = []
            for i in range(len(prices) - 14, len(prices)):
                if i == len(prices) - 14:
                    continue
                h = highs[i]
                l = lows[i]
                pc = closes[i - 1]
                tr = max(h - l, abs(h - pc), abs(l - pc))
                tr_values.append(tr)
            if tr_values:
                atr = sum(tr_values) / len(tr_values)
                fd = await self._get_or_create_definition(
                    "atr_14", "volatility",
                    description="14-day Average True Range",
                    formula="avg(max(high-low, abs(high-prev_close), abs(low-prev_close)), 14)",
                    source="daily_price", parameters={"period": 14},
                )
                await self._upsert_value(fd.id, symbol, as_of_date, round(atr, 4))
                count += 1

        # high_low_range_14: average (high-low)/close
        if len(closes) >= 14:
            ranges = []
            for i in range(len(closes) - 14, len(closes)):
                if closes[i] > 0:
                    ranges.append((highs[i] - lows[i]) / closes[i])
            if ranges:
                avg_range = sum(ranges) / len(ranges)
                fd = await self._get_or_create_definition(
                    "high_low_range_14", "volatility",
                    description="14-day average high-low range / close",
                    formula="avg((high-low)/close, 14)",
                    source="daily_price", parameters={"period": 14},
                )
                await self._upsert_value(fd.id, symbol, as_of_date, round(avg_range, 6))
                count += 1

        # parkinson_vol_20
        if len(prices) >= 21:
            parkinson_values = []
            for i in range(len(prices) - 20, len(prices)):
                if i > len(prices) - 20 and highs[i] > 0 and lows[i] > 0:
                    ratio = highs[i] / lows[i]
                    if ratio > 0:
                        parkinson_values.append((math.log(ratio) ** 2) / (4 * math.log(2)))
            if parkinson_values:
                parkinson_vol = math.sqrt(sum(parkinson_values) / len(parkinson_values) * 252)
                fd = await self._get_or_create_definition(
                    "parkinson_vol_20", "volatility",
                    description="20-day Parkinson volatility estimator",
                    formula="sqrt(avg(ln(high/low)^2 / (4*ln(2)), 20) * 252)",
                    source="daily_price", parameters={"period": 20, "annualization": 252},
                )
                await self._upsert_value(fd.id, symbol, as_of_date, round(parkinson_vol, 6))
                count += 1

        return count

    # ============================================================
    # 5. FINANCIAL FEATURES
    # ============================================================

    async def _compute_financial_features(self, symbol: str, as_of_date: date) -> int:
        count = 0

        # Get latest quarter / annual EPS
        qr = await self.session.execute(
            select(QuarterlyResult)
            .where(QuarterlyResult.symbol == symbol)
            .order_by(QuarterlyResult.fiscal_year.desc(), QuarterlyResult.quarter.desc())
            .limit(1)
        )
        latest_q = qr.scalar_one_or_none()

        ar = await self.session.execute(
            select(AnnualResult)
            .where(AnnualResult.symbol == symbol)
            .order_by(AnnualResult.fiscal_year.desc())
            .limit(1)
        )
        latest_a = ar.scalar_one_or_none()

        # Get latest close price
        price_r = await self.session.execute(
            select(DailyPrice)
            .where(DailyPrice.symbol == symbol, DailyPrice.trade_date <= as_of_date)
            .order_by(DailyPrice.trade_date.desc())
            .limit(1)
        )
        latest_price = price_r.scalar_one_or_none()
        current_price = latest_price.close if latest_price else None

        # Get company for market cap
        comp_r = await self.session.execute(
            select(Company).where(Company.symbol == symbol)
        )
        company = comp_r.scalar_one_or_none()

        # eps_diluted
        eps = None
        if latest_q and latest_q.eps_diluted is not None:
            eps = latest_q.eps_diluted
        elif latest_a and latest_a.eps_diluted is not None:
            eps = latest_a.eps_diluted
        if eps is not None:
            fd = await self._get_or_create_definition(
                "eps_diluted", "financial",
                description="Latest diluted earnings per share",
                formula="from QuarterlyResult or AnnualResult", source="quarterly_result,annual_result",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(eps, 4),
                                     {"fiscal_year": latest_q.fiscal_year if latest_q else latest_a.fiscal_year,
                                      "quarter": latest_q.quarter if latest_q else None})
            count += 1

        # pe_ratio
        if current_price and eps and eps > 0:
            pe = current_price / eps
            fd = await self._get_or_create_definition(
                "pe_ratio", "financial",
                description="Price-to-Earnings ratio",
                formula="close / eps_diluted", source="daily_price,quarterly_result",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(pe, 4),
                                     {"price": current_price, "eps": eps})
            count += 1

        # market_cap_crore
        if company and company.market_cap:
            mc_cr = company.market_cap / 1e7
            fd = await self._get_or_create_definition(
                "market_cap_crore", "financial",
                description="Market capitalization in crores",
                formula="market_cap / 1e7", source="company",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(mc_cr, 2))
            count += 1

        # revenue_growth_yoy (from quarterly result)
        if latest_q and latest_q.revenue_yoy_growth is not None:
            fd = await self._get_or_create_definition(
                "revenue_growth_yoy", "financial",
                description="Year-over-year revenue growth",
                formula="from QuarterlyResult", source="quarterly_result",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(latest_q.revenue_yoy_growth, 4),
                                     {"fiscal_year": latest_q.fiscal_year, "quarter": latest_q.quarter})
            count += 1

        # eps_growth_yoy
        if latest_q and latest_q.eps_yoy_growth is not None:
            fd = await self._get_or_create_definition(
                "eps_growth_yoy", "financial",
                description="Year-over-year EPS growth",
                formula="from QuarterlyResult", source="quarterly_result",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(latest_q.eps_yoy_growth, 4))
            count += 1

        # net_margin
        if latest_q and latest_q.net_margin is not None:
            fd = await self._get_or_create_definition(
                "net_margin", "financial",
                description="Net profit margin",
                formula="from QuarterlyResult", source="quarterly_result",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(latest_q.net_margin, 4))
            count += 1

        return count

    # ============================================================
    # 6. NEWS FEATURES
    # ============================================================

    async def _compute_news_features(self, symbol: str, as_of_date: date) -> int:
        count = 0
        lookback_start = as_of_date - timedelta(days=7)

        # Get articles for symbol in last 7 days
        articles_r = await self.session.execute(
            select(NewsArticle).where(
                NewsArticle.symbol == symbol,
                NewsArticle.published_at >= lookback_start,
                NewsArticle.published_at <= as_of_date,
            )
        )
        articles = list(articles_r.scalars().all())
        article_ids = [a.id for a in articles]

        # news_count_7d
        fd = await self._get_or_create_definition(
            "news_count_7d", "news",
            description="Number of news articles in last 7 days",
            formula="count(articles)", source="news_article",
        )
        await self._upsert_value(fd.id, symbol, as_of_date, len(articles),
                                 {"lookback_days": 7, "article_ids": article_ids[:10] if article_ids else []})
        count += 1

        if not article_ids:
            # No news, but we still record sentiment_score_7d as None-skip
            return count

        # Get NLP analysis for those articles
        nlp_r = await self.session.execute(
            select(NewsNLPAnalysis).where(
                NewsNLPAnalysis.article_id.in_(article_ids),
                NewsNLPAnalysis.is_processed.is_(True),
            )
        )
        analyses = list(nlp_r.scalars().all())

        if not analyses:
            return count

        # sentiment_score_7d: avg sentiment positive score
        sentiments = [a.sentiment_positive for a in analyses if a.sentiment_positive is not None]
        if sentiments:
            avg_sentiment = sum(sentiments) / len(sentiments)
            fd = await self._get_or_create_definition(
                "sentiment_score_7d", "news",
                description="Average news sentiment score over 7 days",
                formula="avg(sentiment_positive)", source="news_nlp",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(avg_sentiment, 4),
                                     {"article_count": len(analyses), "lookback_days": 7})
            count += 1

        # positive_news_ratio_7d
        if analyses:
            positive_count = sum(1 for a in analyses if a.sentiment_label == "positive")
            ratio = positive_count / len(analyses)
            fd = await self._get_or_create_definition(
                "positive_news_ratio_7d", "news",
                description="Ratio of positive news articles over 7 days",
                formula="positive_articles / total_articles", source="news_nlp",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(ratio, 4))
            count += 1

        # avg_sentiment_confidence
        confidences = [a.sentiment_confidence for a in analyses if a.sentiment_confidence is not None]
        if confidences:
            avg_conf = sum(confidences) / len(confidences)
            fd = await self._get_or_create_definition(
                "avg_sentiment_confidence", "news",
                description="Average sentiment confidence score",
                formula="avg(sentiment_confidence)", source="news_nlp",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(avg_conf, 4))
            count += 1

        return count

    # ============================================================
    # 7. MACRO FEATURES
    # ============================================================

    async def _compute_macro_features(self, symbol: str, as_of_date: date) -> int:
        count = 0

        # Fetch latest macro indicators
        indicator_types = ["interest_rate", "inflation_rate", "gdp_growth"]
        for ind_type in indicator_types:
            r = await self.session.execute(
                select(MacroIndicator)
                .where(MacroIndicator.indicator_type == ind_type, MacroIndicator.as_of_date <= as_of_date)
                .order_by(MacroIndicator.as_of_date.desc())
                .limit(1)
            )
            indicator = r.scalar_one_or_none()
            if indicator and indicator.value is not None:
                fd = await self._get_or_create_definition(
                    ind_type, "macro",
                    description=f"Latest {ind_type.replace('_', ' ')}",
                    formula="from MacroIndicator", source="macro_indicator",
                )
                await self._upsert_value(fd.id, symbol, as_of_date, round(indicator.value, 4),
                                         {"as_of_date": indicator.as_of_date.isoformat(), "unit": indicator.unit})
                count += 1

        # Try MacroFeature as fallback
        if count < 3:
            for ind_type in indicator_types:
                existing = await self.session.execute(
                    select(FeatureValue)
                    .join(FeatureDefinition)
                    .where(
                        FeatureDefinition.name == ind_type,
                        FeatureValue.symbol == symbol,
                        FeatureValue.as_of_date == as_of_date,
                    )
                )
                if existing.scalar_one_or_none():
                    continue
                r = await self.session.execute(
                    select(MacroFeature)
                    .where(MacroFeature.feature_name == ind_type, MacroFeature.as_of_date <= as_of_date)
                    .order_by(MacroFeature.as_of_date.desc())
                    .limit(1)
                )
                mf = r.scalar_one_or_none()
                if mf and mf.value is not None:
                    fd = await self._get_or_create_definition(
                        ind_type, "macro",
                        description=f"Latest {ind_type.replace('_', ' ')} (from MacroFeature)",
                        formula="from MacroFeature", source="macro_feature",
                    )
                    await self._upsert_value(fd.id, symbol, as_of_date, round(mf.value, 4),
                                             {"as_of_date": mf.as_of_date.isoformat()})
                    count += 1

        return count

    # ============================================================
    # 8. MARKET BREADTH FEATURES
    # ============================================================

    async def _compute_breadth_features(self, symbol: str, as_of_date: date) -> int:
        count = 0

        r = await self.session.execute(
            select(MarketBreadth)
            .where(MarketBreadth.trade_date <= as_of_date)
            .order_by(MarketBreadth.trade_date.desc())
            .limit(20)
        )
        breadths = list(reversed(r.scalars().all()))

        if not breadths:
            return count

        latest = breadths[-1]

        # advance_decline_ratio
        if latest.declining and latest.declining > 0:
            ad_ratio = latest.advancing / latest.declining
            fd = await self._get_or_create_definition(
                "advance_decline_ratio", "breadth",
                description="Advance/Decline ratio",
                formula="advancing / declining", source="market_breadth",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(ad_ratio, 4),
                                     {"advancing": latest.advancing, "declining": latest.declining})
            count += 1

        # new_highs_lows_ratio
        if latest.new_lows and latest.new_lows > 0:
            nhl_ratio = latest.new_highs / latest.new_lows
            fd = await self._get_or_create_definition(
                "new_highs_lows_ratio", "breadth",
                description="New Highs / New Lows ratio",
                formula="new_highs / new_lows", source="market_breadth",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(nhl_ratio, 4),
                                     {"new_highs": latest.new_highs, "new_lows": latest.new_lows})
            count += 1
        elif latest.new_lows == 0 and latest.new_highs > 0:
            fd = await self._get_or_create_definition(
                "new_highs_lows_ratio", "breadth",
                description="New Highs / New Lows ratio",
                formula="new_highs / new_lows", source="market_breadth",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, latest.new_highs * 100.0,
                                     {"new_highs": latest.new_highs, "new_lows": 0, "note": "no new_lows"})
            count += 1

        # breadth_oscillator
        if latest.breadth_oscillator is not None:
            fd = await self._get_or_create_definition(
                "breadth_oscillator", "breadth",
                description="Market breadth oscillator value",
                formula="from MarketBreadth", source="market_breadth",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(latest.breadth_oscillator, 4))
            count += 1

        # advance_decline_line (cumulative A/D)
        ad_line = 0
        for b in breadths:
            ad_line += (b.advancing - b.declining)
        fd = await self._get_or_create_definition(
            "advance_decline_line", "breadth",
            description="Cumulative Advance-Decline line (20-day)",
            formula="sum(advancing - declining)", source="market_breadth",
        )
        await self._upsert_value(fd.id, symbol, as_of_date, ad_line, {"period_days": 20})
        count += 1

        # breadth_momentum: change in A/D ratio over 5 days
        if len(breadths) >= 6:
            recent_ad = self._safe_div(breadths[-1].advancing, max(breadths[-1].declining, 1))
            prev_ad = self._safe_div(breadths[-6].advancing, max(breadths[-6].declining, 1))
            if recent_ad is not None and prev_ad is not None and prev_ad != 0:
                bm = self._safe_div(recent_ad - prev_ad, prev_ad)
                if bm is not None:
                    fd = await self._get_or_create_definition(
                        "breadth_momentum_5d", "breadth",
                        description="5-day change in Advance/Decline ratio",
                        formula="(ad_ratio[t] - ad_ratio[t-5]) / ad_ratio[t-5]",
                        source="market_breadth",
                    )
                    await self._upsert_value(fd.id, symbol, as_of_date, round(bm * 100, 4))
                    count += 1

        return count

    # ============================================================
    # COMPUTE ALL
    # ============================================================

    async def compute_all_features(self, symbol: str, as_of_date: date | None = None) -> dict[str, int]:
        as_of_date = as_of_date or date.today()
        if as_of_date.weekday() >= 5:
            as_of_date = as_of_date - timedelta(days=as_of_date.weekday() - 4)
        await self.session.flush()
        results = {
            "price": await self._compute_price_features(symbol, as_of_date),
            "volume": await self._compute_volume_features(symbol, as_of_date),
            "momentum": await self._compute_momentum_features(symbol, as_of_date),
            "volatility": await self._compute_volatility_features(symbol, as_of_date),
            "financial": await self._compute_financial_features(symbol, as_of_date),
            "news": await self._compute_news_features(symbol, as_of_date),
            "macro": await self._compute_macro_features(symbol, as_of_date),
            "breadth": await self._compute_breadth_features(symbol, as_of_date),
        }
        await self.session.flush()
        self._log.info("all_features_computed", symbol=symbol, date=as_of_date.isoformat(), counts=results)
        return results

    async def compute_feature(self, feature_name: str, symbol: str, as_of_date: date | None = None) -> float | None:
        as_of_date = as_of_date or date.today()
        if as_of_date.weekday() >= 5:
            as_of_date = as_of_date - timedelta(days=as_of_date.weekday() - 4)
        fd = await self.get_feature_definition(feature_name)
        if not fd:
            return None
        category = fd.category
        await self.session.flush()
        if category == "price":
            await self._compute_price_features(symbol, as_of_date)
        elif category == "volume":
            await self._compute_volume_features(symbol, as_of_date)
        elif category == "momentum":
            await self._compute_momentum_features(symbol, as_of_date)
        elif category == "volatility":
            await self._compute_volatility_features(symbol, as_of_date)
        elif category == "financial":
            await self._compute_financial_features(symbol, as_of_date)
        elif category == "news":
            await self._compute_news_features(symbol, as_of_date)
        elif category == "macro":
            await self._compute_macro_features(symbol, as_of_date)
        elif category == "breadth":
            await self._compute_breadth_features(symbol, as_of_date)
        await self.session.flush()
        r = await self.session.execute(
            select(FeatureValue).where(
                FeatureValue.feature_definition_id == FeatureDefinition.id,
                FeatureDefinition.name == feature_name,
                FeatureValue.symbol == symbol,
                FeatureValue.as_of_date == as_of_date,
            ).join(FeatureDefinition)
        )
        fv = r.scalar_one_or_none()
        return fv.value if fv else None

    # ============================================================
    # CLEAR OLD VALUES
    # ============================================================

    async def clear_old_values(self, older_than_days: int = 90) -> int:
        cutoff = date.today() - timedelta(days=older_than_days)
        r = await self.session.execute(
            delete(FeatureValue).where(FeatureValue.as_of_date < cutoff)
        )
        await self.session.flush()
        return r.rowcount or 0
