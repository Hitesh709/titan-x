from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.infrastructure.market_data_providers import YahooFinanceProvider
from titan_x.models.recommendation import Recommendation
from titan_x.services.advanced_strategy_engine import AdvancedStrategyEngine
from titan_x.services.market_data_service import MarketDataService
from titan_x.services.paper_trading_service import PaperTradingService

logger = structlog.get_logger(__name__)


class AutoDemoBotEngine:
    """Continuous paper bot.

    Fast-gate candidates are re-confirmed on a short intraday window
    (trend + momentum + ATR). Every entry carries a live-managed stop-loss and
    take-profit so open positions are actively risk-managed instead of
    buy-and-hold. Stopping the bot squares off every holding at the live
    market price.
    """

    DEFAULT_CAPITAL = Decimal("100000")
    STRATEGY_WINDOW_HOURS = 3
    MAX_CANDIDATES = 100
    MAX_INTRADAY_EVAL = 24
    MAX_TRADES_PER_BURST = 8
    MAX_ACCOUNT_LOSS_PCT = Decimal("40")
    STOP_LOSS_PCT = Decimal("3")
    TAKE_PROFIT_PCT = Decimal("6")
    TRAILING_STOP_PCT = Decimal("1.5")
    FALLBACK_MIN_TECH_SCORE = 80.0
    MIN_INTRADAY_CANDLES = 20

    STRATEGY_PARAMS = {
        "fast_period": 5,
        "slow_period": 15,
        "rsi_period": 14,
        "atr_period": 14,
        "min_confirmations": 1,
        "max_atr_pct": 3.0,
        "stop_loss_pct": float(STOP_LOSS_PCT),
        "take_profit_pct": float(TAKE_PROFIT_PCT),
        "trailing_stop_pct": float(TRAILING_STOP_PCT),
    }

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.paper = PaperTradingService(session)
        self.strategy = AdvancedStrategyEngine()

    # ---------- price plumbing ----------

    async def _refresh_live_quotes(self, symbols: list[str]) -> dict[str, Decimal]:
        if not symbols:
            return {}
        quotes = (await MarketDataService(self.session).get_quotes(symbols)).get("quotes", [])
        out: dict[str, Decimal] = {}
        for q in quotes:
            raw = q.get("last_price")
            if raw is None:
                continue
            try:
                price = Decimal(str(raw))
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            out[str(q.get("symbol", "")).replace(".NS", "").replace(".BO", "").upper()] = price
        return out

    async def _live_snapshot(self, symbol: str) -> tuple[float | None, list[dict[str, Any]], str]:
        """Latest intraday 3-hour window, falling back to a live quote."""
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
            if valid:
                price = float(valid[-1].close)
                candles = [
                    {
                        "close": float(p.close),
                        "high": float(p.high),
                        "low": float(p.low),
                        "date": str(p.trade_date),
                    }
                    for p in valid[-36:]
                ]
                return price, candles, "YAHOO_LIVE_INTRADAY_3H"
        except Exception as exc:  # noqa: BLE001
            logger.warning("intraday_window_unavailable", symbol=symbol, error=str(exc))
        finally:
            await provider.close()

        # Fallback: a live regular-market quote when intraday candles are
        # unavailable (rate-limited/blocked) keeps the bot trading instead of stalling.
        live = await self._refresh_live_quotes([symbol])
        price = live.get(symbol.upper())
        if price is None:
            return None, [], "UNAVAILABLE"
        return float(price), [], "YAHOO_LIVE_QUOTE"

    # ---------- candidate ranking ----------

    async def _rank_candidates(self) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(Recommendation)
            .where(
                Recommendation.status == "active",
                Recommendation.recommendation_type == "LIVE_SCAN",
                Recommendation.source.ilike("%yahoo%"),
                Recommendation.direction.in_(["BUY", "buy"]),
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
                technical = float(
                    gate.get("selected_score", gate.get("delivery_score", rec.score or 0))
                )
            except (TypeError, ValueError):
                technical = float(rec.score or 0)
            predicted = float(rec.predicted_return_pct or 0)
            confidence = float(rec.confidence or 0)
            score = (
                max(0.0, technical) * 0.55
                + max(0.0, confidence * 100.0) * 0.25
                + max(0.0, predicted) * 0.20
            )
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

    async def _execute_market(
        self,
        user_id: int,
        symbol: str,
        side: str,
        quantity: int,
        live_price: Decimal | None = None,
    ) -> dict[str, Any]:
        order = await self.paper.place_order(
            user_id=user_id,
            symbol=symbol,
            side=side,
            order_type="market",
            quantity=quantity,
            price=None,
            time_in_force="day",
            market_price=live_price,
        )
        return {
            "id": order.id,
            "status": order.status,
            "filled_quantity": order.filled_quantity,
            "price": float(live_price)
            if live_price is not None
            else (float(order.price) if order.price is not None else None),
            "rejection_reason": order.rejection_reason,
        }

    # ---------- risk management ----------

    async def _manage_positions(self, user_id: int) -> dict[str, Any]:
        """Mark open positions to live price and trigger stop-loss / take-profit orders."""
        portfolio = await self.paper.get_portfolio(user_id)
        positions = [p for p in portfolio if int(p.get("quantity") or 0) > 0]
        if not positions:
            return {"symbols": 0, "orders_filled": 0, "positions": 0}
        symbols = [str(p["symbol"]) for p in positions]
        live = await self._refresh_live_quotes(symbols)
        filled = 0
        for symbol in symbols:
            price = live.get(symbol.upper())
            if price is None:
                continue
            try:
                filled += await self.paper.process_open_orders(symbol, force_price=price)
            except Exception as exc:  # noqa: BLE001
                logger.warning("position_order_process_failed", symbol=symbol, error=str(exc))
        return {"symbols": len(symbols), "orders_filled": filled, "positions": len(positions)}

    async def _protect_positions(self, user_id: int) -> list[dict[str, Any]]:
        """Hard circuit breaker for bot positions (those carrying a stop order).

        Manual quick-trade positions are never touched. A -40% move counts only
        for positions the bot risk-manages, i.e. which already have a stop order.
        """
        portfolio = await self.paper.get_portfolio(user_id)
        positions = [p for p in portfolio if int(p.get("quantity") or 0) > 0]
        if not positions:
            return []
        open_orders, _ = await self.paper.list_orders(user_id, status="open")
        protected = {
            str(o.symbol).upper()
            for o in open_orders
            if o.side == "sell" and o.order_type in ("stop", "stop_limit")
        }
        live = await self._refresh_live_quotes([str(p["symbol"]) for p in positions])
        exited: list[dict[str, Any]] = []
        for p in positions:
            symbol = str(p["symbol"]).upper()
            if symbol not in protected:
                continue
            price = live.get(symbol)
            average = float(p.get("average_price") or 0)
            if price is None or average <= 0:
                continue
            loss_pct = (float(price) - average) / average * 100
            if loss_pct <= -float(self.MAX_ACCOUNT_LOSS_PCT):
                order = await self._execute_market(
                    user_id, symbol, "sell", int(p["quantity"]), live_price=price
                )
                exited.append({**p, "fill": order, "loss_pct": round(loss_pct, 2)})
        return exited

    # ---------- bot run ----------

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
            await self.paper.create_account(user_id, self.DEFAULT_CAPITAL)

        managed = await self._manage_positions(user_id)
        protected = await self._protect_positions(user_id)
        candidates = await self._rank_candidates()
        base = {
            "strategy_window": "3h",
            "continuous": True,
            "stop_loss_pct": float(self.STOP_LOSS_PCT),
            "take_profit_pct": float(self.TAKE_PROFIT_PCT),
            "stop_loss_max_pct": float(self.MAX_ACCOUNT_LOSS_PCT),
            "managed": managed,
            "protected_positions": protected,
        }
        if not candidates:
            return {
                "action": "WAIT",
                "reason": "No active algorithmic candidates are currently qualified",
                **base,
                "trades": [],
            }

        current = {str(p["symbol"]).upper(): p for p in await self.paper.get_portfolio(user_id)}
        eligible: list[dict[str, Any]] = []
        for candidate in candidates[: self.MAX_INTRADAY_EVAL]:
            symbol = candidate["symbol"]
            if symbol in current:
                continue
            price, candles, source = await self._live_snapshot(symbol)
            if price is None:
                continue
            fallback = len(candles) < self.MIN_INTRADAY_CANDLES
            if fallback:
                # No intraday window (quote fallback): require a strong fast-gate candidate.
                if float(candidate["technical_score"] or 0) < self.FALLBACK_MIN_TECH_SCORE:
                    continue
                signal_action = "BUY"
                signal_confidence = 0.0
            else:
                signals = self.strategy.generate_signals(candles, self.STRATEGY_PARAMS)
                last_signal = signals[-1] if signals else {"action": "hold", "confidence": 0}
                signal_action = str(last_signal.get("action", "hold")).upper()
                signal_confidence = float(last_signal.get("confidence", 0) or 0)
                if signal_action != "BUY":
                    continue
            candidate = {
                **candidate,
                "price": price,
                "price_source": source,
                "signal": signal_action,
                "signal_confidence": signal_confidence,
                "data_fallback": fallback,
            }
            candidate["rank_score"] = candidate["score"] + signal_confidence * 100.0
            eligible.append(candidate)

        eligible.sort(key=lambda item: item["rank_score"], reverse=True)
        trade_count = max(
            1,
            min(self.MAX_TRADES_PER_BURST, int(round(5 * profile_ratio)), len(eligible)),
        )
        selected = eligible[:trade_count]
        total_weight = sum(max(1.0, item["rank_score"]) for item in selected) or 1.0
        trades: list[dict[str, Any]] = []

        for item in selected:
            allocation = trade_amount * max(1.0, item["rank_score"]) / total_weight
            quantity = int(Decimal(str(allocation)) // Decimal(str(item["price"])))
            if quantity <= 0:
                continue
            live_map = await self._refresh_live_quotes([item["symbol"]])
            live_price = live_map.get(item["symbol"])
            order = await self._execute_market(
                user_id, item["symbol"], "buy", quantity, live_price=live_price
            )
            filled = int(order.get("filled_quantity") or 0)
            fill_price = float(order.get("price") or item["price"])
            if filled <= 0 or order.get("status") != "filled":
                continue

            stop_price = round(fill_price * (1 - float(self.STOP_LOSS_PCT) / 100.0), 2)
            take_price = round(fill_price * (1 + float(self.TAKE_PROFIT_PCT) / 100.0), 2)
            stop_order = await self.paper.place_order(
                user_id=user_id,
                symbol=item["symbol"],
                side="sell",
                order_type="stop",
                quantity=filled,
                stop_price=Decimal(str(stop_price)),
                time_in_force="day",
                defer_evaluation=True,
            )
            take_order = await self.paper.place_order(
                user_id=user_id,
                symbol=item["symbol"],
                side="sell",
                order_type="limit",
                quantity=filled,
                price=Decimal(str(take_price)),
                time_in_force="day",
                defer_evaluation=True,
            )
            trades.append({
                "symbol": item["symbol"],
                "action": "BUY",
                "quantity": filled,
                "price": fill_price,
                "allocated_amount": round(allocation, 2),
                "stop_loss_price": stop_price,
                "take_profit_price": take_price,
                "stop_loss_pct": float(self.STOP_LOSS_PCT),
                "take_profit_pct": float(self.TAKE_PROFIT_PCT),
                "score": round(item["rank_score"], 2),
                "technical_score": round(item["technical_score"], 2),
                "predicted_return_pct": round(item["predicted_return_pct"], 2),
                "price_source": item["price_source"],
                "data_fallback": item.get("data_fallback", False),
                "order": order,
                "stop_order_id": stop_order.id,
                "stop_order_status": stop_order.status,
                "take_order_id": take_order.id,
                "take_order_status": take_order.status,
            })

        return {
            "action": "TRADE" if trades else "WAIT",
            **base,
            "universe_candidates": len(candidates),
            "eligible_candidates": len(eligible),
            "selected_candidates": len(selected),
            "profile_ratio": profile_ratio,
            "max_trades_per_burst": self.MAX_TRADES_PER_BURST,
            "trades": trades,
        }

    # ---------- live overview / square-off ----------

    async def get_overview(self, user_id: int) -> dict[str, Any]:
        """Live mark-to-market of the paper account (holdings P&L + cumulative P&L)."""
        account = await self.paper.get_account(user_id)
        empty_summary = {
            "initial_capital": 0.0,
            "cash_balance": 0.0,
            "portfolio_value": 0.0,
            "total_invested": 0.0,
            "total_realized_pnl": 0.0,
            "total_unrealized_pnl": 0.0,
            "total_pnl": 0.0,
            "total_pnl_pct": 0.0,
            "positions_count": 0,
        }
        if account is None:
            return {"account": None, "positions": [], "summary": empty_summary}

        portfolio = await self.paper.get_portfolio(user_id)
        symbols = [str(p["symbol"]) for p in portfolio if int(p.get("quantity") or 0) > 0]
        live = await self._refresh_live_quotes(symbols)

        positions: list[dict[str, Any]] = []
        invested = Decimal("0")
        unrealized = Decimal("0")
        for p in portfolio:
            quantity = int(p.get("quantity") or 0)
            if quantity <= 0:
                continue
            live_price = live.get(str(p["symbol"]).upper())
            if live_price is not None:
                price = live_price
                price_source = "live"
            else:
                if p.get("current_price") is not None:
                    price = Decimal(str(p["current_price"]))
                else:
                    price = None
                price_source = "eod"
            avg = Decimal(str(p["average_price"]))
            market_value = (
                price * quantity if price is not None else Decimal(str(p["market_value"]))
            )
            positions.append({
                "symbol": p["symbol"],
                "quantity": quantity,
                "average_price": float(avg),
                "current_price": float(price) if price is not None else None,
                "price_source": price_source,
                "market_value": round(float(market_value), 2),
                "unrealized_pnl": round(float(market_value - Decimal(str(p["cost_basis"]))), 2),
                "unrealized_pnl_pct": round(float((price - avg) / avg * 100), 2)
                if price and avg
                else 0.0,
            })
            invested += Decimal(str(p["cost_basis"]))
            if price is not None:
                unrealized += market_value - Decimal(str(p["cost_basis"]))

        summary = await self.paper.get_account_summary(user_id) or {}
        realized = Decimal(str(summary.get("total_realized_pnl", 0)))
        cash = account.cash_balance
        portfolio_value = cash + invested + unrealized
        total = realized + unrealized
        initial = account.initial_capital
        return {
            "account": {"account_id": account.id, "is_active": account.is_active},
            "positions": positions,
            "summary": {
                "initial_capital": float(initial),
                "cash_balance": float(cash),
                "portfolio_value": round(float(portfolio_value), 2),
                "total_invested": round(float(invested), 2),
                "total_realized_pnl": round(float(realized), 2),
                "total_unrealized_pnl": round(float(unrealized), 2),
                "total_pnl": round(float(total), 2),
                "total_pnl_pct": round(float(total / initial * 100), 2) if initial else 0.0,
                "positions_count": len(positions),
            },
        }

    async def square_off_all(self, user_id: int) -> dict[str, Any]:
        """Sell every open holding at the live market price and cancel open orders."""
        account = await self.paper.get_account(user_id)
        if account is None:
            return {
                "positions_closed": [],
                "sold": 0,
                "failed": [],
                "realized_pnl": 0.0,
                "remaining": 0,
                "message": "No paper account to square off",
            }

        open_orders, _ = await self.paper.list_orders(user_id, status="open")
        for order in open_orders:
            await self.paper.cancel_order(order.id, user_id)

        portfolio = await self.paper.get_portfolio(user_id)
        positions = [p for p in portfolio if int(p.get("quantity") or 0) > 0]
        if not positions:
            return {
                "positions_closed": [],
                "sold": 0,
                "failed": [],
                "realized_pnl": 0.0,
                "remaining": 0,
                "message": "No open holdings to square off",
            }

        before_summary = await self.paper.get_account_summary(user_id) or {}
        before = Decimal(str(before_summary.get("total_realized_pnl", 0)))
        live = await self._refresh_live_quotes([str(p["symbol"]) for p in positions])
        closed: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        for p in positions:
            symbol = str(p["symbol"]).upper()
            quantity = int(p["quantity"])
            live_price = live.get(symbol)
            try:
                order = await self._execute_market(
                    user_id, symbol, "sell", quantity, live_price=live_price
                )
                if order.get("status") != "filled":
                    failed.append({**p, "fill": order})
                    continue
                fill_price = order.get("price")
                closed.append({
                    "symbol": symbol,
                    "quantity": quantity,
                    "fill_price": fill_price,
                    "average_price": p["average_price"],
                    "realized_pnl": round((float(fill_price) - p["average_price"]) * quantity, 2)
                    if fill_price is not None
                    else None,
                })
            except Exception as exc:  # noqa: BLE001
                failed.append({**p, "error": str(exc)})
        await self.session.flush()
        after_summary = await self.paper.get_account_summary(user_id) or {}
        after = Decimal(str(after_summary.get("total_realized_pnl", 0)))
        remaining = [
            r
            for r in await self.paper.get_portfolio(user_id)
            if int(r.get("quantity") or 0) > 0
        ]
        return {
            "positions_closed": closed,
            "sold": len(closed),
            "failed": failed,
            "realized_pnl": round(float(after - before), 2),
            "remaining": len(remaining),
            "message": (
                f"Squared off {len(closed)} holding(s) at market price"
                + (f"; {len(failed)} failed to fill" if failed else "")
            ),
        }