from __future__ import annotations

from datetime import datetime, timezone

import httpx


class CandleService:
    """Real OHLCV candles from Yahoo Finance's public chart endpoint.

    Intraday history is limited by Yahoo's retention windows. The service never
    creates synthetic candles; an unavailable interval/range returns an error.
    """

    BASES = (
        "https://query1.finance.yahoo.com/v8/finance/chart",
        "https://query2.finance.yahoo.com/v8/finance/chart",
    )
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )

    RANGE_BY_INTERVAL = {
        "5m": "5d",
        "15m": "30d",
        "30m": "60d",
        "60m": "1y",
        "1h": "1y",
        "1d": "max",
        "1wk": "max",
        "1mo": "max",
    }

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        value = symbol.strip().upper()
        if "." not in value:
            value = f"{value}.NS"
        return value

    @staticmethod
    def _interval(value: str) -> str:
        aliases = {"1h": "60m", "1w": "1wk", "1m": "1mo"}
        return aliases.get(value, value)

    async def get_candles(
        self,
        symbol: str,
        interval: str = "1d",
        period: str = "max",
    ) -> list[dict]:
        interval = self._interval(interval)
        allowed = {"5m", "15m", "30m", "60m", "1d", "1wk", "1mo"}
        if interval not in allowed:
            raise ValueError(f"Unsupported candle interval: {interval}")

        if period == "from_beginning":
            period = "max"
        allowed_periods = {"1d", "5d", "1mo", "3mo", "6mo", "ytd", "1y", "5y", "10y", "max"}
        if period not in allowed_periods:
            raise ValueError(f"Unsupported candle period: {period}")

        # Yahoo does not provide useful max history for intraday intervals.
        # Use the largest valid retention window for the selected interval.
        if interval in {"5m", "15m", "30m"}:
            max_period = self.RANGE_BY_INTERVAL[interval]
            if period in {"max", "10y", "5y", "1y", "6mo", "3mo"}:
                period = max_period
        elif interval == "60m" and period in {"max", "10y", "5y"}:
            period = "1y"

        sym = self.normalize_symbol(symbol)
        params = {"range": period, "interval": interval, "events": "history", "includeAdjustedClose": "true"}
        headers = {"User-Agent": self.USER_AGENT}
        last_error: Exception | None = None

        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=headers) as client:
            for base in self.BASES:
                try:
                    response = await client.get(f"{base}/{sym}", params=params)
                    response.raise_for_status()
                    payload = response.json()
                    result = ((payload.get("chart") or {}).get("result") or [])
                    if not result:
                        raise ValueError(f"No candle data returned for {sym}")
                    chart = result[0]
                    timestamps = chart.get("timestamp") or []
                    quote = ((chart.get("indicators") or {}).get("quote") or [{}])[0]
                    opens = quote.get("open") or []
                    highs = quote.get("high") or []
                    lows = quote.get("low") or []
                    closes = quote.get("close") or []
                    volumes = quote.get("volume") or []
                    candles: list[dict] = []
                    for i, ts in enumerate(timestamps):
                        o = opens[i] if i < len(opens) else None
                        h = highs[i] if i < len(highs) else None
                        l = lows[i] if i < len(lows) else None
                        c = closes[i] if i < len(closes) else None
                        if None in (o, h, l, c):
                            continue
                        candles.append({
                            "time": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
                            "open": float(o),
                            "high": float(h),
                            "low": float(l),
                            "close": float(c),
                            "volume": int(volumes[i]) if i < len(volumes) and volumes[i] else 0,
                        })
                    if not candles:
                        raise ValueError(f"No parseable candle data returned for {sym}")
                    if interval == "60m" and str(self._interval("1h")) == "60m":
                        # Keep native 60m data for 1h; 4h is resampled below in
                        # the endpoint/service caller.
                        pass
                    return candles
                except Exception as exc:  # noqa: BLE001
                    last_error = exc

        raise ValueError(f"Live candle data unavailable for {sym}: {last_error}")

    @staticmethod
    def resample_4h(candles: list[dict]) -> list[dict]:
        if not candles:
            return []
        result: list[dict] = []
        bucket: list[dict] = []
        last_day = None
        block = None
        for candle in candles:
            dt = datetime.fromisoformat(candle["time"].replace("Z", "+00:00"))
            day = dt.date()
            hour_block = dt.hour // 4
            key = (day, hour_block)
            if block is None:
                block = key
            if key != block:
                if bucket:
                    result.append(CandleService._aggregate(bucket))
                bucket = []
                block = key
            bucket.append(candle)
            last_day = day
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
