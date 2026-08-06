"""Volume features (SMAs, ratios, VWAP, OBV)."""
from datetime import date


class VolumeFeaturesMixin:
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