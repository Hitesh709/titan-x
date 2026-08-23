from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any


class MarketDataNormalizationService:
    """Canonicalize and validate provider quote payloads before ingestion."""

    REQUIRED_PRICE_KEYS = ("last_price", "price", "ltp")

    @staticmethod
    def _number(value: Any, field: str, *, positive: bool = False) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} must be numeric") from exc
        if not math.isfinite(number):
            raise ValueError(f"{field} must be finite")
        if positive and number <= 0:
            raise ValueError(f"{field} must be positive")
        return number

    @staticmethod
    def _timestamp(value: Any) -> str:
        if value is None or value == "":
            return datetime.now(timezone.utc).isoformat()
        if isinstance(value, datetime):
            dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        text = str(value).strip()
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("timestamp must be ISO-8601") from exc
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()

    def normalize(self, symbol: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol cannot be empty")
        if not isinstance(payload, dict):
            raise ValueError(f"invalid quote payload for {normalized_symbol}")

        price = next((payload.get(key) for key in self.REQUIRED_PRICE_KEYS if payload.get(key) is not None), None)
        if price is None:
            raise ValueError(f"missing last price for {normalized_symbol}")

        result: dict[str, Any] = {
            "symbol": normalized_symbol,
            "last_price": self._number(price, "last_price", positive=True),
            "timestamp": self._timestamp(payload.get("timestamp", payload.get("ts"))),
            "exchange": str(payload["exchange"]).upper() if payload.get("exchange") else None,
            "currency": str(payload.get("currency") or "INR").upper(),
            "source": str(payload.get("source") or "live"),
        }

        if payload.get("change") is not None:
            result["change"] = self._number(payload["change"], "change")
        else:
            result["change"] = None

        if payload.get("change_percent") is not None:
            result["change_percent"] = self._number(payload["change_percent"], "change_percent")
        else:
            result["change_percent"] = None

        if payload.get("volume") is not None:
            volume = self._number(payload["volume"], "volume")
            if volume < 0:
                raise ValueError("volume cannot be negative")
            result["volume"] = volume
        else:
            result["volume"] = None

        return result

    def validate(self, quote: dict[str, Any]) -> None:
        symbol = str(quote.get("symbol", "")).strip()
        if not symbol:
            raise ValueError("normalized quote requires symbol")
        self._number(quote.get("last_price"), "last_price", positive=True)
        self._timestamp(quote.get("timestamp"))
        if quote.get("change") is not None:
            self._number(quote["change"], "change")
        if quote.get("change_percent") is not None:
            self._number(quote["change_percent"], "change_percent")
        if quote.get("volume") is not None and self._number(quote["volume"], "volume") < 0:
            raise ValueError("volume cannot be negative")
