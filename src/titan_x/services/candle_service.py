from __future__ import annotations

from datetime import datetime

from titan_x.infrastructure.jugaad_nse_provider import JugaadNSEProvider


class CandleService:
    """NSE candle facade used by charts, analysis and strategy features.

    The service deliberately has no Yahoo/dummy fallback. If NSE candle data
    is unavailable, callers receive an error instead of fabricated prices.
    """

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        return symbol.strip().upper().replace(".NS", "")

    @staticmethod
    def _interval(value: str) -> str:
        aliases = {"1h": "60m", "1w": "1wk", "1m": "1mo"}
        return aliases.get(value, value)

    async def get_candles(
        self,
        symbol: str,
        interval: str = "1d",
        period: str = "5d",
    ) -> list[dict]:
        interval = self._interval(interval)
        allowed = {"5m", "15m", "30m", "60m", "1d", "1wk", "1mo"}
        if interval not in allowed:
            raise ValueError(f"Unsupported candle interval: {interval}")
        provider = JugaadNSEProvider()
        try:
            candles = await provider.get_candles(self.normalize_symbol(symbol), interval, period)
        finally:
            await provider.close()
        if not candles:
            raise ValueError(f"No NSE candle data returned for {self.normalize_symbol(symbol)}")
        return candles

    @staticmethod
    def resample_4h(candles: list[dict]) -> list[dict]:
        if not candles:
            return []
        result: list[dict] = []
        bucket: list[dict] = []
        block = None
        for candle in candles:
            dt = datetime.fromisoformat(candle["time"].replace("Z", "+00:00"))
            key = (dt.date(), dt.hour // 4)
            if block is None:
                block = key
            if key != block:
                if bucket:
                    result.append(CandleService._aggregate(bucket))
                bucket = []
                block = key
            bucket.append(candle)
        if bucket:
            result.append(CandleService._aggregate(bucket))
        return result

    @staticmethod
    def _aggregate(rows: list[dict]) -> dict:
        return {
            "time": rows[0]["time"],
            "open": rows[0]["open"],
            "high": max(r["high"] for r in rows),
            "low": min(r["low"] for r in rows),
            "close": rows[-1]["close"],
            "volume": sum(r["volume"] for r in rows),
        }
