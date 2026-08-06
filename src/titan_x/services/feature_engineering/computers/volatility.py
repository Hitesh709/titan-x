"""Volatility features (historical vol, ATR, high-low range, Parkinson)."""
import math
import statistics
from datetime import date


class VolatilityFeaturesMixin:
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