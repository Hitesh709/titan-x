from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.core.config import get_settings
from titan_x.infrastructure.jugaad_nse_provider import JugaadNSEProvider
from titan_x.infrastructure.market_data_providers import get_market_data_provider
from titan_x.services.advanced_strategy_engine import AdvancedStrategyEngine
from titan_x.services.demo_risk_engine import DemoRiskEngine
from titan_x.services.market_data_gateway_service import MarketDataGateway
from titan_x.services.paper_trading_service import PaperTradingService


class AutoDemoBotEngine:
    """15-cycle paper-only execution using validated current NSE market data.

    Prices are always read from the configured provider and passed through the
    freshness gate. Synthetic/demo prices are never used for execution.
    """

    MAX_CYCLES = 15
    DEFAULT_CAPITAL = Decimal("100000")
    MAX_POSITION_PCT = 20.0

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.paper = PaperTradingService(session)
        self.strategy = AdvancedStrategyEngine()
        self.risk = DemoRiskEngine(stop_loss_pct=1.0, take_profit_pct=1.5, max_position_pct=self.MAX_POSITION_PCT)

    async def _market_snapshot(self, symbol: str, cycle: int) -> tuple[float | None, list[dict[str, Any]], str]:
        settings = get_settings()
        provider_name = str(getattr(settings, "market_data_provider", "jugaad") or "jugaad").lower()
        provider = JugaadNSEProvider() if provider_name in {"jugaad", "jugaad_nse", "nse_public"} else get_market_data_provider(provider_name, getattr(settings, "market_data_api_key", None))

        async def fetch_quote(name: str) -> dict[str, Any]:
            return await provider.get_quote(name)

        gateway = MarketDataGateway(fetch_quote, provider_name=provider_name, stale_after_seconds=15.0)
        try:
            try:
                quote = await gateway.quote(symbol, refresh=True)
            except Exception:
                return None, [], "UNAVAILABLE"
            base = float(quote["last_price"])
            if base <= 0 or gateway.is_stale(quote):
                return None, [], "UNAVAILABLE"

            candles: list[dict[str, Any]] = []
            try:
                if isinstance(provider, JugaadNSEProvider):
                    candles = await provider.get_candles(symbol, interval="5m", period="1d")
                else:
                    end = date.today()
                    start = end - timedelta(days=10)
                    points = await provider.get_historical_prices(symbol, interval="5m", start=start, end=end, synthetic_ok=False)
                    candles = [{"close": float(p.close), "high": float(p.high), "low": float(p.low), "date": str(p.trade_date)} for p in points[-120:]]
            except Exception:
                candles = []
            if len(candles) < 35:
                return base, [], "LIVE_MARKET_REFERENCE"
            return base, candles[-120:], "LIVE_MARKET_REFERENCE"
        finally:
            close = getattr(provider, "close", None)
            if close:
                try:
                    await close()
                except Exception:
                    pass
            await gateway.close()

    async def _execute_at_price(self, user_id: int, symbol: str, side: str, quantity: int, price: float) -> dict[str, Any]:
        account = await self.paper.get_account(user_id)
        if account is None or not account.is_active:
            raise ValueError("Paper account is not active")
        order = await self.paper._order_repo.create(account_id=account.id, user_id=user_id, symbol=symbol.upper(), side=side, order_type="market", quantity=quantity, price=None, stop_price=None, time_in_force="day", status="pending")
        await self.paper._fill_order(order, account, Decimal(str(price)))
        await self.session.refresh(order)
        return {"id": order.id, "status": order.status, "filled_quantity": order.filled_quantity, "price": float(price), "rejection_reason": order.rejection_reason}

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
        if price is None:
            return {"cycle": cycle, "action": "HOLD", "reason": "current market price unavailable or stale; no synthetic price used", "price": None, "price_source": price_source, "strategy": {"action": "hold", "confidence": 0.0, "metadata": {}}, "risk": self.risk.metadata()}
        if len(candles) < 35:
            return {"cycle": cycle, "action": "HOLD", "reason": "insufficient real market history for strategy", "price": price, "price_source": price_source, "strategy": {"action": "hold", "confidence": 0.0, "metadata": {}}, "risk": self.risk.metadata()}

        positions = await self.paper.get_portfolio(user_id)
        held = next((p for p in positions if str(p.get("symbol", "")).upper() == symbol), None)
        held_qty = int(float((held or {}).get("quantity", 0)))

        if held_qty > 0:
            average_price = float((held or {}).get("average_price", 0) or 0)
            if average_price > 0:
                risk_decision = self.risk.exit_decision(average_price, price)
                if risk_decision.action == "sell":
                    order = await self._execute_at_price(user_id, symbol, "sell", held_qty, price)
                    return {"cycle": cycle, "action": "SELL", "reason": risk_decision.reason, "price": price, "price_source": price_source, "quantity": held_qty, "order": order, "strategy": {"action": "risk_exit", "confidence": 1.0, "metadata": {}}, "risk": {**self.risk.metadata(), "stop_loss": risk_decision.stop_loss, "take_profit": risk_decision.take_profit}}

        signals = self.strategy.generate_signals(candles, {"fast_period": 10, "slow_period": 30, "rsi_period": 14, "atr_period": 14, "min_confirmations": 2, "stop_loss_pct": 1.0, "take_profit_pct": 1.5, "trailing_stop_pct": 0.8})
        latest_signal = signals[-1] if signals else {"action": "hold", "confidence": 0.0, "metadata": {}}
        strategy_action = str(latest_signal.get("action", "hold")).lower()

        if strategy_action in {"buy", "long"} and held_qty <= 0:
            account_summary = await self.paper.get_account_summary(user_id)
            portfolio_value = Decimal(str((account_summary or {}).get("portfolio_value", self.DEFAULT_CAPITAL)))
            requested = Decimal(str(trade_amount))
            if not self.risk.position_allowed(requested, portfolio_value):
                return {"cycle": cycle, "action": "HOLD", "reason": "risk position-size limit exceeded", "price": price, "price_source": price_source, "strategy": latest_signal, "risk": self.risk.metadata()}
            confidence = max(0.0, min(1.0, float(latest_signal.get("confidence", 0.0) or 0.0)))
            if confidence < 0.50:
                return {"cycle": cycle, "action": "HOLD", "reason": "strategy confidence below execution threshold", "price": price, "price_source": price_source, "strategy": latest_signal, "risk": self.risk.metadata()}
            quantity = max(1, int((trade_amount * confidence) // price))
            order = await self._execute_at_price(user_id, symbol, "buy", quantity, price)
            return {"cycle": cycle, "action": "BUY", "price": price, "price_source": price_source, "quantity": quantity, "order": order, "strategy": latest_signal, "risk": self.risk.metadata()}

        if strategy_action in {"sell", "short", "exit"} and held_qty > 0:
            order = await self._execute_at_price(user_id, symbol, "sell", held_qty, price)
            return {"cycle": cycle, "action": "SELL", "price": price, "price_source": price_source, "quantity": held_qty, "order": order, "strategy": latest_signal, "risk": self.risk.metadata()}

        return {"cycle": cycle, "action": "HOLD", "reason": "strategy has no executable position change", "price": price, "price_source": price_source, "strategy": latest_signal, "risk": self.risk.metadata()}
