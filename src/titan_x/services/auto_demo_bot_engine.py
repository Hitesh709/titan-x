from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.core.config import get_settings
from titan_x.infrastructure.market_data_providers import get_market_data_provider
from titan_x.services.advanced_strategy_engine import AdvancedStrategyEngine
from titan_x.services.paper_trading_service import PaperTradingService


class AutoDemoBotEngine:
    """15-minute paper-only execution engine using real reference prices when available."""

    MAX_CYCLES = 15
    DEFAULT_CAPITAL = Decimal("100000")

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.paper = PaperTradingService(session)
        self.strategy = AdvancedStrategyEngine()

    async def _market_snapshot(self, symbol: str, cycle: int) -> tuple[float, list[dict[str, Any]], str]:
        settings = get_settings()
        provider_name = str(getattr(settings, "market_data_provider", "yahoo") or "yahoo").lower()
        provider = get_market_data_provider(provider_name, getattr(settings, "market_data_api_key", None))
        try:
            quote: dict[str, Any] | None = None
            try:
                quote = await provider.get_quote(symbol)
            except Exception:
                quote = None
            points = []
            try:
                end = date.today()
                start = end - timedelta(days=10)
                points = await provider.get_historical_prices(symbol, interval="5m", start=start, end=end)
            except Exception:
                points = []

            ltp = quote.get("last_price") if quote else None
            if ltp is not None and float(ltp) > 0:
                base = float(ltp)
                source = "LIVE_REFERENCE"
            else:
                latest = await self.paper._price_service.get_latest_price(symbol)
                base = float(latest.close) if latest else 150.0
                source = "STORED_REFERENCE"

            if provider_name == "mock" or not quote or not quote.get("last_price"):
                base *= 1.0 + 0.0015 * math.sin(cycle * 1.7)
                source = "DEMO_MARKET"

            if len(points) < 35:
                closes = [base * (1.0 + 0.003 * math.sin((i + cycle) / 3.2)) for i in range(60)]
                points = [{"close": p, "high": p * 1.002, "low": p * 0.998, "date": str(i)} for i, p in enumerate(closes)]
            else:
                points = [{"close": float(p.close), "high": float(p.high), "low": float(p.low), "date": str(p.trade_date)} for p in points[-120:]]
            return base, points, source
        finally:
            close = getattr(provider, "close", None)
            if close:
                try:
                    await close()
                except Exception:
                    pass

    async def _execute_at_price(self, user_id: int, symbol: str, side: str, quantity: int, price: float) -> dict[str, Any]:
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

    async def run_cycle(self, user_id: int, symbol: str, cycle: int, trade_amount: float = 10000.0) -> dict[str, Any]:
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
        signals = self.strategy.generate_signals(candles, {
            "fast_period": 10, "slow_period": 30, "rsi_period": 14, "atr_period": 14,
            "min_confirmations": 2, "stop_loss_pct": 1.0, "take_profit_pct": 1.5,
            "trailing_stop_pct": 0.8,
        })
        latest_signal = signals[-1] if signals else {"action": "hold", "confidence": 0.0, "metadata": {}}

        positions = await self.paper.get_portfolio(user_id)
        held = next((p for p in positions if str(p.get("symbol", "")).upper() == symbol), None)
        held_qty = int(float((held or {}).get("quantity", 0)))

        # Demo cadence is deliberately long/flat: BUY on odd cycles and SELL
        # on even cycles. The advanced strategy supplies confidence/risk data.
        if cycle % 2 == 1:
            if held_qty > 0:
                return {"cycle": cycle, "action": "HOLD", "reason": "existing demo position", "price": price, "price_source": price_source, "strategy": latest_signal}
            confidence = max(0.5, min(1.0, float(latest_signal.get("confidence", 0.5) or 0.5)))
            quantity = max(1, int((trade_amount * confidence) // price))
            order = await self._execute_at_price(user_id, symbol, "buy", quantity, price)
            return {"cycle": cycle, "action": "BUY", "price": price, "price_source": price_source, "quantity": quantity, "order": order, "strategy": latest_signal}

        if held_qty <= 0:
            return {"cycle": cycle, "action": "HOLD", "reason": "no demo position to sell", "price": price, "price_source": price_source, "strategy": latest_signal}
        order = await self._execute_at_price(user_id, symbol, "sell", held_qty, price)
        return {"cycle": cycle, "action": "SELL", "price": price, "price_source": price_source, "quantity": held_qty, "order": order, "strategy": latest_signal}
