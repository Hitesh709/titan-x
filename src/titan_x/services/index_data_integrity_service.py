from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class IndexDefinition:
    canonical: str
    exchange: str
    provider_symbols: tuple[str, ...]


INDEX_REGISTRY: dict[str, IndexDefinition] = {
    "NIFTY_50": IndexDefinition("NIFTY_50", "NSE", ("NIFTY 50", "NIFTY50", "NIFTY_50", "NSE:NIFTY50")),
    "NIFTY_BANK": IndexDefinition("NIFTY_BANK", "NSE", ("NIFTY BANK", "NIFTYBANK", "NIFTY_BANK", "NSE:NIFTYBANK")),
    "NIFTY_IT": IndexDefinition("NIFTY_IT", "NSE", ("NIFTY IT", "NIFTYIT", "NIFTY_IT", "NSE:NIFTYIT")),
    "INDIA_VIX": IndexDefinition("INDIA_VIX", "NSE", ("INDIA VIX", "INDIAVIX", "INDIA_VIX", "NSE:INDIAVIX")),
    "SENSEX": IndexDefinition("SENSEX", "BSE", ("SENSEX", "BSE SENSEX", "BSE:SENSEX")),
    "BANKEX": IndexDefinition("BANKEX", "BSE", ("BANKEX", "BSE:BANKEX")),
    "BSE_500": IndexDefinition("BSE_500", "BSE", ("BSE 500", "BSE500", "BSE_500", "BSE:BSE500")),
}

_ALIAS_TO_CANONICAL = {alias.upper(): key for key, item in INDEX_REGISTRY.items() for alias in item.provider_symbols}


class IndexDataIntegrityService:
    """Canonicalize and reject mismatched NSE/BSE index market data."""

    @staticmethod
    def canonicalize(symbol: str) -> str:
        value = symbol.strip().upper()
        if value in INDEX_REGISTRY:
            return value
        if value in _ALIAS_TO_CANONICAL:
            return _ALIAS_TO_CANONICAL[value]
        raise ValueError(f"unsupported index symbol: {symbol}")

    def normalize(self, symbol: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("index payload must be an object")
        canonical = self.canonicalize(symbol)
        definition = INDEX_REGISTRY[canonical]
        provider_symbol = str(payload.get("provider_symbol") or payload.get("symbol") or symbol).strip().upper()
        if provider_symbol not in definition.provider_symbols and provider_symbol != canonical:
            raise ValueError(f"index identity mismatch: {symbol} vs {provider_symbol}")
        exchange = str(payload.get("exchange") or definition.exchange).strip().upper()
        if exchange != definition.exchange:
            raise ValueError(f"exchange mismatch for {canonical}: expected {definition.exchange}, got {exchange}")

        result: dict[str, Any] = {
            "index": canonical,
            "symbol": canonical,
            "provider_symbol": provider_symbol,
            "exchange": exchange,
            "source": str(payload.get("source") or "live"),
            "currency": str(payload.get("currency") or "INR").upper(),
        }
        for field in ("last_price", "open", "high", "low", "close", "previous_close", "change", "change_percent"):
            if payload.get(field) is not None:
                try:
                    value = float(payload[field])
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"{field} must be numeric") from exc
                if not math.isfinite(value):
                    raise ValueError(f"{field} must be finite")
                result[field] = value

        if "last_price" not in result:
            raise ValueError(f"missing last_price for {canonical}")
        if result["last_price"] <= 0:
            raise ValueError("last_price must be positive")
        if "open" in result and result["open"] <= 0: raise ValueError("open must be positive")
        if "high" in result and result["high"] <= 0: raise ValueError("high must be positive")
        if "low" in result and result["low"] <= 0: raise ValueError("low must be positive")
        if "close" in result and result["close"] <= 0: raise ValueError("close must be positive")
        if "previous_close" in result and result["previous_close"] <= 0: raise ValueError("previous_close must be positive")

        high = result.get("high")
        low = result.get("low")
        if high is not None and low is not None and high < low:
            raise ValueError("high cannot be below low")
        for field in ("open", "close", "last_price"):
            value = result.get(field)
            if value is not None and high is not None and value > high:
                raise ValueError(f"{field} cannot exceed high")
            if value is not None and low is not None and value < low:
                raise ValueError(f"{field} cannot be below low")

        if "previous_close" in result:
            calculated_change = result["last_price"] - result["previous_close"]
            calculated_pct = calculated_change / result["previous_close"] * 100
            if "change" in result and not math.isclose(result["change"], calculated_change, rel_tol=0, abs_tol=0.05):
                raise ValueError("change does not match last_price and previous_close")
            if "change_percent" in result and not math.isclose(result["change_percent"], calculated_pct, rel_tol=0, abs_tol=0.05):
                raise ValueError("change_percent does not match last_price and previous_close")
            result["change"] = calculated_change
            result["change_percent"] = calculated_pct

        timestamp = payload.get("timestamp", payload.get("ts"))
        if timestamp:
            try:
                dt = timestamp if isinstance(timestamp, datetime) else datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
                dt = dt.astimezone(timezone.utc)
                if dt > datetime.now(timezone.utc):
                    raise ValueError("index timestamp cannot be in the future")
                result["timestamp"] = dt.isoformat()
            except ValueError as exc:
                raise ValueError("invalid index timestamp") from exc
        else:
            result["timestamp"] = datetime.now(timezone.utc).isoformat()
        return result
