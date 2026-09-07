from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.infrastructure.market_data_providers import YahooFinanceProvider
from titan_x.models.recommendation import Recommendation
from titan_x.services.advanced_strategy_engine import AdvancedStrategyEngine
from titan_x.services.paper_trading_service import PaperTradingService


class AutoDemoBotEngine:
    """Continuous paper bot that ranks multiple stocks using a 3-hour strategy window."""

    DEFAULT_CAPITAL = Decimal("100000")
    STRATEGY_WINDOW_HOURS = 3
    MAX_CANDIDATES = 50
    MAX_TRADES_PER_BURST = 50
    MAX_STOP_LOSS_PCT = Decimal("40")

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.paper = PaperTradingService(session)
        self.strategy = AdvancedStrategyEngine()

    async def _live_snapshot(self, symbol: str) -> tuple[float | None, list[dict[str, Any]], str]:
        provider = YahooFinanceProvider()
        try:
            live_points = await provider.get_historical_prices(
                symbol,
                interval="5m",
                start=date.today() - timedelta(days=2),
                end=date.today() + timedelta(days=1),
                synthetic_ok=False,
            )
            valid = [p for p in live_points if p.close and float(p.close) > 0]
            if not valid:
                return None, [], "UNAVAILABLE"
            price = float(valid[-1].close)
            cutoff = valid[-1].trade_date
            candles = [
                {
                    "close": float(p.close),
                    "high": float(p.high),
                    "low": float(p.low),
                    "date": str(p.trade_date),
                }
                for p in valid
            ]
            # 5-minute bars × 36 = 3-hour strategy window.
            return price, candles[-36:], "YAHOO_LIVE_INTRADAY_3H"
        except Exception:
            return None, [], "UNAVAILABLE"
        finally:
            await provider.close()

    async def _rank_candidates(self) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(Recommendation)
            .where(
                Recommendation.status == "active",
                Recommendation.recommendation_type == "LIVE_SCAN",
                Recommendation.source == "yahoo",
                Recommendation.direction.in_(["BUY", "SELL", "buy", "sell"]),
            )
            .order_by(Recommendation.score.desc(), Recommendation.generated_at.desc())
            .limit(300),
        )
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for rec in result.scalars().all():
            symbol = str(rec.symbol or "").strip().upper()
            if not symbol or symbol in seen:
                continue
            try:
                metadata = json.loads(rec.metadata_json or "{}")
            except Exception:
                metadata = {}
            gate = metadata.get("fast_technical_gate") or {}
            try:
                technical = float(gate.get("selected_score", gate.get("delivery_score", rec.score or 0)))
            except (TypeError, ValueError):
                technical = float(rec.score or 0)
            predicted = float(rec.predicted_return_pct or 0)
            confidence = float(rec.confidence or 0)
            score = max(0.0, technical) * 0.55 + max(0.0, confidence * 100.0) * 0.25 + max(0.0, predicted) * 0.20
            candidates.append({
                "symbol": symbol,
                "direction": str(rec.direction).upper(),
                "score": score,
                "technical_score": technical,
                "confidence": confidence,
                "predicted_return_pct": predicted,
            })
            seen.add(symbol)
            if len(candidates) >= self.MAX_CANDIDATES:
                break
        return sorted(candidates, key=lambda item: item["score"], reverse=True)

    async def _execute_at_price(
        self, user_id: int, symbol: str, side: str, quantity: int, price: float
    ) -> dict[str, Any]:
        order = await self.paper.place_order(
            user_id=user_id,
            symbol=symbol,
            side=side,
            order_type="market",
            quantity=quantity,
            price=None,
            time_in_force="day",
        )
        return {
            "id": order.id,
            "status": order.status,
            "filled_quantity": order.filled_quantity,
            "price": float(price),
            "rejection_reason": order.rejection_reason,
        }

    async def _protect_positions(self, user_id: int) -> list[dict[str, Any]]:
        """Exit any auto-bot position after a 40% loss from its entry price."""
        positions = await self.paper.get_portfolio(user_id)
        exits: list[dict[str, Any]] = []
        for position in positions:
            quantity = int(position.get("quantity", 0))
            average = float(position.get("average_price", 0) or 0)
            if quantity <= 0 or average <= 0:
                continue
            price, _, source = await self._live_snapshot(str(position["symbol"]))
            if price is None or price > average * 0.60:
                continue
            order = await self._execute_at_price(user_id, str(position["symbol"]), "sell", quantity, price)
            exits.append({
                "symbol": str(position["symbol"]),
                "action": "STOP_LOSS",
                "quantity": quantity,
                "price": price,
                "price_source": source,
                "max_loss_pct": float(self.MAX_STOP_LOSS_PCT),
                "order": order,
            })
        return exits

    async def run_once(
        self,
        user_id: int,
        trade_amount: float = 10000.0,
        profile_ratio: float = 1.0,
    ) -> dict[str, Any]:
        if trade_amount <= 0:
            raise ValueError("trade_amount must be positive")
        if profile_ratio <= 0:
            raise ValueError("profile_ratio must be positive")

        account = await self.paper.get_account(user_id)
        if account is None:
            account = await self.paper.create_account(user_id, self.DEFAULT_CAPITAL)

        protected = await self._protect_positions(user_id)
        candidates = await self._rank_candidates()
        if not candidates:
            return {
                "action": "WAIT",
                "reason": "No active algorithmic candidates are currently qualified",
                "strategy_window": "3h",
                "continuous": True,
                "stop_loss_max_pct": 40,
                "trades": [],
                "protected_positions": protected,
            }

        current = {str(p["symbol"]).upper(): p for p in await self.paper.get_portfolio(user_id)}
        eligible: list[dict[str, Any]] = []
        for candidate in candidates:
            if candidate["symbol"] in current:
                continue
            price, candles, source = await self._live_snapshot(candidate["symbol"])
            if price is None or len(candles) < 20:
                continue
            signals = self.strategy.generate_signals(
                candles,
                {
                    "fast_period": 6,
                    "slow_period": 18,
                    "rsi_period": 14,
                    "atr_period": 14,
                    "min_confirmations": 2,
                    "stop_loss_pct": 40.0,
                    "take_profit_pct": 2.0,
                    "trailing_stop_pct": 1.0,
                },
            )
            signal = signals[-1] if signals else {"action": "hold", "confidence": 0}
            direction = str(signal.get("action", "hold")).upper()
            if direction not in {"BUY", "SELL"} or direction != candidate["direction"]:
                continue
            candidate = {**candidate, "price": price, "price_source": source, "signal": direction, "signal_confidence": float(signal.get("confidence", 0) or 0)}
            candidate["rank_score"] = candidate["score"] + candidate["signal_confidence"] * 100.0
            eligible.append(candidate)

        eligible.sort(key=lambda item: item["rank_score"], reverse=True)
        trade_count = max(1, min(self.MAX_TRADES_PER_BURST, int(round(5 * profile_ratio)), len(eligible)))
        selected = eligible[:trade_count]
        total_weight = sum(max(1.0, item["rank_score"]) for item in selected) or 1.0
        trades: list[dict[str, Any]] = []

        for item in selected:
            allocation = trade_amount * max(1.0, item["rank_score"]) / total_weight
            quantity = int(Decimal(str(allocation)) // Decimal(str(item["price"])))
            if quantity <= 0:
                continue
            # The paper engine supports long equity positions. SELL signals are
            # represented as WAIT unless a corresponding position exists.
            if item["signal"] != "BUY":
                continue
            order = await self._execute_at_price(user_id, item["symbol"], "buy", quantity, item["price"])
            trades.append({
                "symbol": item["symbol"],
                "action": "BUY",
                "quantity": quantity,
                "price": item["price"],
                "allocated_amount": round(allocation, 2),
                "stop_loss_price": round(item["price"] * 0.60, 2),
                "max_loss_pct": 40,
                "score": round(item["rank_score"], 2),
                "technical_score": round(item["technical_score"], 2),
                "predicted_return_pct": round(item["predicted_return_pct"], 2),
                "price_source": item["price_source"],
                "order": order,
            })

        return {
            "action": "TRADE" if trades else "WAIT",
            "strategy_window": "3h",
            "continuous": True,
            "universe_candidates": len(candidates),
            "eligible_candidates": len(eligible),
            "selected_candidates": len(selected),
            "profile_ratio": profile_ratio,
            "max_trades_per_burst": self.MAX_TRADES_PER_BURST,
            "stop_loss_max_pct": 40,
            "protected_positions": protected,
            "trades": trades,
        }
