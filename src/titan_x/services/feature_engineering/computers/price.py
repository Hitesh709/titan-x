"""Price features (returns, log returns, moving averages, Bollinger, position)."""
import math
import statistics
from datetime import date


class PriceFeaturesMixin:
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