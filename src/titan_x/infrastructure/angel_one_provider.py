from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, time as dt_time, timedelta
from typing import Any

import httpx
import pyotp

from titan_x.core.config import get_settings
from titan_x.infrastructure.market_data_providers import MarketDataPoint, MarketDataProvider


class AngelOneProvider(MarketDataProvider):
    """Angel One SmartAPI market-data adapter.

    Credentials are read from the application settings. A SmartAPI session is
    created lazily on first use and reused for the lifetime of this provider.
    Symbol tokens are resolved through the official Search Scrip endpoint.
    """

    BASE_URL = "https://apiconnect.angelone.in"
    LOGIN_PATH = "/rest/auth/angelbroking/user/v1/loginByPassword"
    SEARCH_PATH = "/rest/secure/angelbroking/order/v1/searchScrip"
    LTP_PATH = "/rest/secure/angelbroking/order/v1/getLtpData"
    CANDLE_PATH = "/rest/secure/angelbroking/historical/v1/getCandleData"

    INTERVALS = {
        "1m": "ONE_MINUTE",
        "3m": "THREE_MINUTE",
        "5m": "FIVE_MINUTE",
        "10m": "TEN_MINUTE",
        "15m": "FIFTEEN_MINUTE",
        "30m": "THIRTY_MINUTE",
        "1h": "ONE_HOUR",
        "60m": "ONE_HOUR",
        "1d": "ONE_DAY",
    }

    MAX_DAYS = {
        "ONE_MINUTE": 30,
        "THREE_MINUTE": 60,
        "FIVE_MINUTE": 100,
        "TEN_MINUTE": 100,
        "FIFTEEN_MINUTE": 200,
        "THIRTY_MINUTE": 200,
        "ONE_HOUR": 400,
        "ONE_DAY": 2000,
    }

    def __init__(self, api_key: str | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key or (settings.angel_one_api_key or "")
        self.client_id = settings.angel_one_client_id or ""
        self.pin = settings.angel_one_pin or ""
        self.totp_secret = settings.angel_one_totp_secret or ""
        self._jwt: str | None = None
        self._client = httpx.AsyncClient(timeout=25.0, follow_redirects=True)
        self._token_cache: dict[str, tuple[str, str]] = {}
        self._public_ip: str | None = None

    def _validate_credentials(self) -> None:
        missing = []
        if not self.api_key:
            missing.append("ANGEL_ONE_API_KEY")
        if not self.client_id:
            missing.append("ANGEL_ONE_CLIENT_ID")
        if not self.pin:
            missing.append("ANGEL_ONE_PIN")
        if not self.totp_secret:
            missing.append("ANGEL_ONE_TOTP_SECRET")
        if missing:
            raise RuntimeError(
                "Angel One SmartAPI credentials are not configured: " + ", ".join(missing)
            )

    async def _get_public_ip(self) -> str:
        if self._public_ip:
            return self._public_ip
        try:
            response = await self._client.get("https://api.ipify.org", timeout=5.0)
            response.raise_for_status()
            self._public_ip = response.text.strip()
        except Exception:
            self._public_ip = "127.0.0.1"
        return self._public_ip

    async def _base_headers(self, authorization: str | None = None) -> dict[str, str]:
        headers = {
            "X-PrivateKey": self.api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-SourceID": "WEB",
            "X-UserType": "USER",
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": await self._get_public_ip(),
            "X-MACAddress": f"{uuid.getnode():012x}"[:2] + ":" + ":".join(
                f"{(uuid.getnode() >> (8 * i)) & 0xff:02x}" for i in range(4, -1, -1)
            ),
        }
        if authorization:
            headers["Authorization"] = authorization
        return headers

    async def _login(self) -> None:
        self._validate_credentials()
        totp = pyotp.TOTP(self.totp_secret).now()
        headers = await self._base_headers()
        response = await self._client.post(
            self.BASE_URL + self.LOGIN_PATH,
            headers=headers,
            json={"clientcode": self.client_id, "password": self.pin, "totp": totp},
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") or {}
        jwt = data.get("jwtToken")
        if not payload.get("status") or not jwt:
            raise RuntimeError(
                f"Angel One login failed: {payload.get('message') or payload.get('errorcode') or 'unknown error'}"
            )
        self._jwt = jwt if str(jwt).lower().startswith("bearer ") else f"Bearer {jwt}"

    async def _ensure_session(self) -> None:
        if self._jwt:
            return
        await self._login()

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        await self._ensure_session()
        headers = await self._base_headers(self._jwt)
        response = await self._client.post(self.BASE_URL + path, headers=headers, json=payload)
        if response.status_code in {401, 403}:
            self._jwt = None
            await self._login()
            headers = await self._base_headers(self._jwt)
            response = await self._client.post(self.BASE_URL + path, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        if data.get("status") is False or data.get("success") is False:
            raise RuntimeError(
                f"Angel One API error: {data.get('message') or data.get('errorcode') or data.get('errorCode') or 'unknown error'}"
            )
        return data

    async def _search_token(self, symbol: str) -> tuple[str, str]:
        clean = symbol.strip().upper().replace(".NS", "").replace(".BO", "")
        cached = self._token_cache.get(clean)
        if cached:
            return cached
        payload = await self._post(self.SEARCH_PATH, {"exchange": "NSE", "searchscrip": clean})
        rows = (payload.get("data") or [])
        candidates = [row for row in rows if str(row.get("exchange", "")).upper() == "NSE"]
        exact = next(
            (
                row
                for row in candidates
                if str(row.get("tradingsymbol", "")).upper() in {f"{clean}-EQ", clean}
            ),
            None,
        )
        row = exact or (candidates[0] if candidates else None)
        if not row or not row.get("symboltoken"):
            raise ValueError(f"Angel One could not resolve NSE symbol token for {clean}")
        result = (str(row["symboltoken"]), str(row.get("tradingsymbol") or f"{clean}-EQ"))
        self._token_cache[clean] = result
        return result

    async def get_quote(self, symbol: str) -> dict:
        clean = symbol.strip().upper().replace(".NS", "").replace(".BO", "")
        token, trading_symbol = await self._search_token(clean)
        payload = await self._post(
            self.LTP_PATH,
            {"exchange": "NSE", "tradingsymbol": trading_symbol, "symboltoken": token},
        )
        data = payload.get("data") or {}
        last = float(data.get("ltp") or 0)
        prev_close = float(data.get("close") or 0) if data.get("close") is not None else None
        change = last - prev_close if last and prev_close else None
        return {
            "symbol": clean,
            "last_price": last,
            "change": change,
            "change_percent": (change / prev_close * 100.0) if change is not None and prev_close else None,
            "prev_close": prev_close,
            "day_high": float(data["high"]) if data.get("high") is not None else None,
            "day_low": float(data["low"]) if data.get("low") is not None else None,
            "volume": None,
            "timestamp": datetime.now().astimezone().isoformat(),
            "exchange": "NSE",
            "currency": "INR",
            "source": "angel-one-smartapi",
            "symbol_token": token,
            "trading_symbol": trading_symbol,
        }

    async def get_candles(
        self,
        symbol: str,
        interval: str = "5m",
        period: str = "5d",
    ) -> list[dict[str, Any]]:
        interval_key = interval.lower()
        api_interval = self.INTERVALS.get(interval_key)
        if not api_interval:
            raise ValueError(f"Unsupported Angel One candle interval: {interval}")
        end = datetime.now().astimezone()
        days = {"1d": 1, "3d": 3, "5d": 5, "1mo": 30, "3mo": 92, "6mo": 183, "1y": 365, "max": 2000}.get(period, 5)
        start = end - timedelta(days=days)
        token, _ = await self._search_token(symbol)
        rows: list[Any] = []
        max_days = self.MAX_DAYS[api_interval]
        cursor = start
        while cursor < end:
            chunk_end = min(cursor + timedelta(days=max_days), end)
            payload = await self._post(
                self.CANDLE_PATH,
                {
                    "exchange": "NSE",
                    "symboltoken": token,
                    "interval": api_interval,
                    "fromdate": cursor.strftime("%Y-%m-%d %H:%M"),
                    "todate": chunk_end.strftime("%Y-%m-%d %H:%M"),
                },
            )
            rows.extend(payload.get("data") or [])
            cursor = chunk_end
            if cursor < end:
                await asyncio.sleep(0.35)
        candles = []
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) < 6:
                continue
            try:
                candles.append(
                    {
                        "time": datetime.fromisoformat(str(row[0]).replace("Z", "+00:00")).astimezone().isoformat(),
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
                        "close": float(row[4]),
                        "volume": int(float(row[5] or 0)),
                        "symbol": symbol.strip().upper(),
                    }
                )
            except (TypeError, ValueError):
                continue
        candles.sort(key=lambda item: item["time"])
        return candles

    async def get_historical_prices(
        self,
        symbol: str,
        interval: str = "1d",
        start: date | None = None,
        end: date | None = None,
        synthetic_ok: bool = False,
    ) -> list[MarketDataPoint]:
        if synthetic_ok:
            raise ValueError("Synthetic market data is not permitted for Angel One")
        interval_key = interval.lower()
        api_interval = self.INTERVALS.get(interval_key)
        if not api_interval:
            raise ValueError(f"Unsupported Angel One historical interval: {interval}")
        start_date = start or date.today() - timedelta(days=365)
        end_date = end or date.today()
        token, _ = await self._search_token(symbol)
        max_days = self.MAX_DAYS[api_interval]
        cursor = datetime.combine(start_date, dt_time(9, 15))
        end_dt = datetime.combine(end_date, dt_time(15, 30))
        result: list[MarketDataPoint] = []
        while cursor <= end_dt:
            chunk_end = min(cursor + timedelta(days=max_days - 1), end_dt)
            payload = await self._post(
                self.CANDLE_PATH,
                {
                    "exchange": "NSE",
                    "symboltoken": token,
                    "interval": api_interval,
                    "fromdate": cursor.strftime("%Y-%m-%d %H:%M"),
                    "todate": chunk_end.strftime("%Y-%m-%d %H:%M"),
                },
            )
            for row in payload.get("data") or []:
                try:
                    result.append(
                        MarketDataPoint(
                            symbol=symbol.strip().upper(),
                            trade_date=datetime.fromisoformat(str(row[0]).replace("Z", "+00:00")).date(),
                            open=float(row[1]),
                            high=float(row[2]),
                            low=float(row[3]),
                            close=float(row[4]),
                            volume=int(float(row[5] or 0)),
                        )
                    )
                except (TypeError, ValueError, IndexError):
                    continue
            cursor = chunk_end + timedelta(minutes=1)
            if cursor <= end_dt:
                await asyncio.sleep(0.35)
        return [p for p in result if start_date <= p.trade_date <= end_date and p.close > 0]

    async def get_company_profile(self, symbol: str) -> dict:
        quote = await self.get_quote(symbol)
        return {
            "symbol": quote["symbol"],
            "name": quote.get("trading_symbol"),
            "sector": None,
            "industry": None,
            "market_cap": None,
            "exchange": "NSE",
            "currency": "INR",
        }

    async def close(self) -> None:
        await self._client.aclose()
        self._jwt = None
        self._token_cache.clear()
