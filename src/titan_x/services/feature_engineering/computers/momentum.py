"""Momentum features (RSI, MACD family, stochastic, ROC)."""
from datetime import date


class MomentumFeaturesMixin:
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