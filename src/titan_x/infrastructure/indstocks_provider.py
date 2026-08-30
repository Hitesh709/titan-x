"""INDstocks market-data adapter for Titan-X.

Read-only market-data integration only. Real order placement is intentionally
not implemented here; the Titan-X demo engine remains paper-only.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any

import httpx


class INDstocksProvider:
    BASE_URL = "https://api.indstocks.com"
    WS_URL = "wss://ws-prices.indstocks.com/api/v1/ws/prices"

    def __init__(self) -> None:
        self.client_id = os.getenv("INDSTOCKS_CLIENT_ID")
        self.mpin = os.getenv("INDSTOCKS_MPIN")
        self.totp_secret = os.getenv("INDSTOCKS_TOTP_SECRET")
        self.access_token = os.getenv("INDSTOCKS_ACCESS_TOKEN")
        self._token_lock = asyncio.Lock()
        self._token_generated_at: datetime | None = None

    async def _ensure_token(self) -> str:
        if self.access_token:
            return self.access_token
        if not (self.client_id and self.mpin and self.totp_secret):
            raise RuntimeError(
                "INDstocks credentials missing. Set INDSTOCKS_CLIENT_ID, "
                "INDSTOCKS_MPIN and INDSTOCKS_TOTP_SECRET, or INDSTOCKS_ACCESS_TOKEN."
            )

        async with self._token_lock:
            if self.access_token:
                return self.access_token
            try:
                import pyotp
            except ImportError as exc:
                raise RuntimeError("pyotp is required for INDstocks TOTP authentication") from exc

            code = pyotp.TOTP(self.totp_secret).now()
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    f"{self.BASE_URL}/generate/token",
                    headers={"x-api-key": self.client_id},
                    json={"mpin": self.mpin, "totp": code},
                )
                response.raise_for_status()
                payload = response.json()

            token = payload.get("token") or (payload.get("data") or {}).get("token")
            if not token:
                raise RuntimeError("INDstocks token response did not contain a token")
            self.access_token = token
            self._token_generated_at = datetime.now(timezone.utc)
            return token

    async def get_quote(self, instrument: str) -> dict[str, Any]:
        token = await self._ensure_token()
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{self.BASE_URL}/market/quotes",
                headers={"Authorization": token},
                params={"instrument": instrument},
            )
            response.raise_for_status()
            payload = response.json()

        return self._normalize_quote(instrument, payload)

    @staticmethod
    def _normalize_quote(instrument: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get("data") if isinstance(payload, dict) else payload
        data = data or {}
        ltp = data.get("ltp") or data.get("last_price") or data.get("lastPrice")
        timestamp = data.get("timestamp") or data.get("exchange_timestamp")
        if timestamp and isinstance(timestamp, (int, float)):
            timestamp = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).isoformat()
        return {
            "symbol": instrument,
            "last_price": float(ltp) if ltp is not None else None,
            "open": data.get("open"),
            "high": data.get("high"),
            "low": data.get("low"),
            "prev_close": data.get("prev_close") or data.get("previous_close"),
            "volume": data.get("volume"),
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
            "source": "indstocks",
        }
