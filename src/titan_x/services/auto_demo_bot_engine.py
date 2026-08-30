from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.core.config import get_settings
from titan_x.infrastructure.market_data_providers import get_market_data_provider
from titan_x.services.advanced_strategy_engine import AdvancedStrategyEngine
from titan_x.services.paper_trading_service import PaperTradingService


class AutoDemoBotEngine:
    """15-minute paper-only execution using the provider's current market quote.

    The account and orders are virtual. Execution prices are never synthetic:
    a BUY/SELL is allowed only when a valid current provider quote is available.
    """

    MAX_CYCLES = 15
    DEFAULT_CAPITAL = Decimal("100000")

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.paper = PaperTradingService(session)
        self.strategy = AdvancedStrategyEngine()

    async def _market_snapshot(self, symbol: str, cycle: int) -> tuple[float | None, list[dict[str, Any]], str]:
        settings = get_settings()
        provider_name = str(getattr(settings, "market_data_provider", "yahoo") or "yahoo").lower()
        provider = get_market_data_provider(provider_name, getattr(settings, "market_data_api_key", None))
        try:
            quote: dict[str, Any] | None = None
            try:
                quote = await provider.get_quote(symbol)
            except Exception:
                quote = None

            # The execution price MUST come from the configured market-data
            # provider. Stored/synthetic/demo prices are never used for fills.
            ltp = quote.get("last_price") if quote else None
            if ltp is None:
                return None, [], "UNAVAILABLE"
            try:
                base = float(ltp)
            except (TypeError, ValueError):
                return None, [], "UNAVAILABLE"
            if base <= 0:
                return None, [], "UNAVAILABLE"

            points: list[Any] = []
            try:
                end = date.today()
                start = end - timedelta(days=10)
                points = await provider.get_historical_prices(symbol, interval="5m", start=start, end=end)
            except Exception:
                points = []

            if len(points) < 35:
                # No fabricated candles. The strategy may not trade until
                # enough real market history is available.
                return base, [], "LIVE_MARKET_REFERENCE"

            candles = [
                {
                    "close": float(p.close),
                    "high": float(p.high),
                    "low": float(p.low),
                    "date": str(p.trade_date),
                }
                for p in points[-120:]
            ]
            return base, candles, "LIVE_MARKET_REFERENCE"
        finally:
            close = getattr(provider, "close", None)
            if close:
                try:
                    await close()
                except Exception:
                    pass

    async def _execute_at_price(
        self, user_id: int, symbol: str, side: str, quantity: int, price: float
    ) -> dict[str, Any]:
        account = await self.paper.get_account(user_id)
        if account is None or not account.is_active:
            raise ValueError("Paper account is not active")
        order = await self.paper._order_repo.create(
            account_id=account.id,
            user_id=user_id,
            symbol=symbol.upper(),
            side=side,
            order_type="market",
            quantity=quantity,
            price=None,
            stop_price=None,
            time_in_force="day",
            status="pending",
        )
        await self.paper._fill_order(order, account, Decimal(str(price)))
        await self.session.refresh(order)
        return {
            "id": order.id,
            "status": order.status,
            "filled_quantity": order.filled_quantity,
            "price": float(price),
            "rejection_reason": order.rejection_reason,
        }

    async def run_cycle(
        self, user_id: int, symbol: str, cycle: int, trade_amount: float = 10000.0
    ) -> dict[str, Any]:
        if not 1 <= cycle <= self.MAX_CYCLES:
            raise ValueError("cycle must be between 1 and 15")
        symbol = symbol.strip().upper()
        if not symbol:
            raise ValueError("symbol is required")
        if trade_amount <= 0:
            raise ValueError("trade_amount must be positive")

        if await self.paper.get_account(user_id) is None:
            await self.paper.create_account(user_id, self.DEFAULT_CAPITAL)

        price, candles, price_source = await self._market_snapshot(symbol, cycle)
        if price is None:
            return {
                "cycle": cycle,
                "action": "HOLD",
                "reason": "current market price unavailable; no synthetic price used",
                "price": None,
                "price_source": price_source,
                "strategy": {"action": "hold", "confidence": 0.0, "metadata": {}},
            }

        if len(candles) < 35:
            return {
                "cycle": cycle,
                "action": "HOLD",
                "reason": "insufficient real market history for strategy",
                "price": price,
                "price_source": price_source,
                "strategy": {"action": "hold", "confidence": 0.0, "metadata": {}},
            }

        signals = self.strategy.generate_signals(
            candles,
            {
                "fast_period": 10,
                "slow_period": 30,
                "rsi_period": 14,
                "atr_period": 14,
                "min_confirmations": 2,
                "stop_loss_pct": 1.0,
                "take_profit_pct": 1.5,
                "trailing_stop_pct": 0.8,
            },
        )
        latest_signal = signals[-1] if signals else {"action": "hold", "confidence": 0.0, "metadata": {}}
        strategy_action = str(latest_signal.get("action", "hold")).lower()

        positions = await self.paper.get_portfolio(user_id)
        held = next((p for p in positions if str(p.get("symbol", "")).upper() == symbol), None)
        held_qty = int(float((held or {}).get("quantity", 0)))

        # Follow the strategy signal. The bot never alternates BUY/SELL merely
        # because a cycle number changed. A SELL is only possible with holdings.
        if strategy_action in {"buy", "long"} and held_qty <= 0:
            confidence = max(0.0, min(1.0, float(latest_signal.get("confidence", 0.0) or 0.0)))
            if confidence < 0.50:
                return {
                    "cycle": cycle,
                    "action": "HOLD",
                    "reason": "strategy confidence below execution threshold",
                    "price": price,
                    "price_source": price_source,
                    "strategy": latest_signal,
                }
            quantity = max(1, int((trade_amount * confidence) // price))
            order = await self._execute_at_price(user_id, symbol, "buy", quantity, price)
            return {
                "cycle": cycle,
                "action": "BUY",
                "price": price,
                "price_source": price_source,
                "quantity": quantity,
                "order": order,
                "strategy": latest_signal,
            }

        if strategy_action in {"sell", "short", "exit"} and held_qty > 0:
            order = await self._execute_at_price(user_id, symbol, "sell", held_qty, price)
            return {
                "cycle": cycle,
                "action": "SELL",
                "price": price,
                "price_source": price_source,
                "quantity": held_qty,
                "order": order,
                "strategy": latest_signal,
            }

        return {
            "cycle": cycle,
            "action": "HOLD",
            "reason": "strategy has no executable position change",
            "price": price,
            "price_source": price_source,
            "strategy": latest_signal,
        }
