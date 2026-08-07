from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.core.config import get_settings
from titan_x.db.repository import BaseRepository
from titan_x.infrastructure.market_data_providers import get_market_data_provider
from titan_x.models.company import Company
from titan_x.models.paper_trading import PaperAccount, PaperOrder, PaperPosition, PaperTrade, SimulatedOrder
from titan_x.models.price import DailyPrice
from titan_x.services.market_data_service import MarketDataService
from titan_x.services.price_service import PriceService

logger = structlog.get_logger(__name__)

COMMISSION_RATE = Decimal("0.001")


class PaperTradingError(ValueError):
    pass


class PaperTradingService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._account_repo = BaseRepository(session, PaperAccount)
        self._order_repo = BaseRepository(session, PaperOrder)
        self._position_repo = BaseRepository(session, PaperPosition)
        self._trade_repo = BaseRepository(session, PaperTrade)
        self._simulated_repo = BaseRepository(session, SimulatedOrder)
        self._price_service = PriceService(session)

    # ── Account ──

    async def create_account(
        self, user_id: int, initial_capital: Decimal = Decimal("100000.00"),
    ) -> PaperAccount:
        existing = await self._session.execute(
            select(PaperAccount).where(PaperAccount.user_id == user_id)
        )
        if existing.scalar_one_or_none():
            raise PaperTradingError("Account already exists")
        account = await self._account_repo.create(
            user_id=user_id,
            initial_capital=initial_capital,
            cash_balance=initial_capital,
        )
        return account

    async def get_account(self, user_id: int) -> PaperAccount | None:
        result = await self._session.execute(
            select(PaperAccount).where(PaperAccount.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_account_summary(self, user_id: int) -> dict[str, Any] | None:
        account = await self.get_account(user_id)
        if account is None:
            return None
        positions = (await self._session.execute(
            select(PaperPosition).where(PaperPosition.account_id == account.id)
        )).scalars().all()
        total_invested = Decimal("0")
        total_current = Decimal("0")
        total_unrealized = Decimal("0")
        total_realized = Decimal("0")
        for p in positions:
            cost = p.cost_basis
            total_invested += cost
            total_realized += p.realized_pnl
            if p.current_price and p.quantity:
                mkt_val = p.current_price * p.quantity
                total_current += mkt_val
                total_unrealized += mkt_val - cost
        portfolio_value = account.cash_balance + total_current
        total_pnl = total_realized + total_unrealized
        return {
            "account_id": account.id,
            "initial_capital": float(account.initial_capital),
            "cash_balance": float(account.cash_balance),
            "portfolio_value": float(portfolio_value),
            "total_invested": float(total_invested),
            "total_realized_pnl": float(total_realized),
            "total_unrealized_pnl": float(total_unrealized),
            "total_pnl": float(total_pnl),
            "total_pnl_pct": round(float(total_pnl / account.initial_capital * 100), 2) if account.initial_capital else 0,
            "positions_count": len(positions),
            "is_active": account.is_active,
        }

    # ── Orders ──

    async def place_order(
        self, user_id: int, symbol: str, side: str,
        order_type: str, quantity: int,
        price: Decimal | None = None, stop_price: Decimal | None = None,
        time_in_force: str = "day",
    ) -> PaperOrder:
        account = await self.get_account(user_id)
        if account is None:
            raise PaperTradingError("No paper account")
        if not account.is_active:
            raise PaperTradingError("Account is inactive")
        if quantity <= 0:
            raise PaperTradingError("Quantity must be positive")
        if side not in ("buy", "sell"):
            raise PaperTradingError("Side must be 'buy' or 'sell'")
        if order_type not in ("market", "limit", "stop", "stop_limit"):
            raise PaperTradingError("Invalid order type")

        order = await self._order_repo.create(
            account_id=account.id,
            user_id=user_id,
            symbol=symbol.upper(),
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            time_in_force=time_in_force,
            status="pending",
        )

        latest = await self._price_service.get_latest_price(symbol)
        current_price = Decimal(str(latest.close)) if latest else None

        # A market order with no stored price (e.g. after a fresh deploy before
        # the scan backfills daily prices) could never fill. Try a live quote so
        # it executes immediately at the real market price.
        if current_price is None and order_type == "market":
            current_price = await self._try_fetch_market_price(symbol)

        if order_type == "market" and current_price:
            await self._fill_order(order, account, current_price)
        elif order_type == "limit" and price and current_price:
            if (side == "buy" and current_price <= price) or (side == "sell" and current_price >= price):
                await self._fill_order(order, account, current_price)
            else:
                order.status = "open"
                await self._session.flush()
        elif order_type == "stop" and stop_price and current_price:
            if (side == "buy" and current_price >= stop_price) or (side == "sell" and current_price <= stop_price):
                await self._fill_order(order, account, current_price)
            else:
                order.status = "open"
                await self._session.flush()
        else:
            order.status = "open"
            await self._session.flush()

        await self._session.refresh(order)
        return order

    async def _try_fetch_market_price(self, symbol: str) -> Decimal | None:
        """Fetch a real market quote for ``symbol`` using MarketDataService
        (cached, pooled) so a market order can fill when no daily price stored."""
        try:
            settings = get_settings()
            if settings.market_data_provider.lower() == "mock":
                return None
            market_svc = MarketDataService(self._session)
            quotes = await market_svc.get_quotes([symbol])
            q = (quotes.get("quotes") or [None])[0]
            if not q:
                return None
            source = str(q.get("source") or "").lower()
            if source in ("mock", "yahoo-fallback", "alphavantage-fallback"):
                return None
            last_price = q.get("last_price")
            if last_price is None:
                return None
            price = Decimal(str(last_price))
            if price <= 0:
                return None
            return price
        except Exception:  # noqa: BLE001
            logger.warning("market_quote_unavailable", symbol=symbol)
            return None

    async def cancel_order(self, order_id: int, user_id: int) -> bool:
        order = await self._order_repo.get(order_id)
        if order is None or order.user_id != user_id:
            return False
        if order.status in ("filled", "cancelled", "rejected"):
            return False
        order.status = "cancelled"
        await self._session.flush()
        return True

    async def list_orders(
        self, user_id: int, status: str | None = None,
        skip: int = 0, limit: int = 50,
    ) -> tuple[Sequence[PaperOrder], int]:
        stmt = select(PaperOrder).where(PaperOrder.user_id == user_id)
        count_stmt = select(func.count()).select_from(PaperOrder).where(PaperOrder.user_id == user_id)
        if status:
            stmt = stmt.where(PaperOrder.status == status)
            count_stmt = count_stmt.where(PaperOrder.status == status)
        total = (await self._session.execute(count_stmt)).scalar() or 0
        stmt = stmt.order_by(desc(PaperOrder.created_at)).offset(skip).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows), total

    async def get_order(self, order_id: int, user_id: int) -> PaperOrder | None:
        order = await self._order_repo.get(order_id)
        if order is None or order.user_id != user_id:
            return None
        return order

    async def process_open_orders(self, symbol: str) -> int:
        latest = await self._price_service.get_latest_price(symbol)
        if not latest:
            return 0
        current_price = Decimal(str(latest.close))
        account = None
        filled = 0
        open_orders = (await self._session.execute(
            select(PaperOrder).where(
                PaperOrder.symbol == symbol,
                PaperOrder.status == "open",
            )
        )).scalars().all()
        for order in open_orders:
            if account is None or account.id != order.account_id:
                account = await self._session.get(PaperAccount, order.account_id)
            if not account or not account.is_active:
                continue
            should_fill = False
            if order.order_type == "limit" and order.price:
                if (order.side == "buy" and current_price <= order.price) or (order.side == "sell" and current_price >= order.price):
                    should_fill = True
            elif order.order_type == "stop" and order.stop_price:
                if (order.side == "buy" and current_price >= order.stop_price) or (order.side == "sell" and current_price <= order.stop_price):
                    should_fill = True
            elif order.order_type == "stop_limit" and order.price and order.stop_price:
                if (order.side == "buy" and current_price >= order.stop_price and current_price <= order.price) or (order.side == "sell" and current_price <= order.stop_price and current_price >= order.price):
                    should_fill = True
            if should_fill:
                await self._fill_order(order, account, current_price)
                filled += 1
        return filled

    def _compute_slippage(self, order: PaperOrder, fill_price: Decimal) -> Decimal | None:
        ref_price = None
        if order.order_type == "limit" and order.price:
            ref_price = order.price
        elif order.order_type == "stop" and order.stop_price:
            ref_price = order.stop_price
        elif order.order_type == "stop_limit" and order.stop_price:
            ref_price = order.stop_price
        if ref_price is not None:
            return (fill_price - ref_price).quantize(Decimal("0.01"))
        return None

    async def _fill_order(
        self, order: PaperOrder, account: PaperAccount, fill_price: Decimal,
    ) -> None:
        quantity = order.quantity - order.filled_quantity
        if quantity <= 0:
            return
        commission = (fill_price * quantity * COMMISSION_RATE).quantize(Decimal("0.01"))
        total_cost = fill_price * quantity + commission
        now = datetime.now(timezone.utc)

        position = (await self._session.execute(
            select(PaperPosition).where(
                PaperPosition.account_id == account.id,
                PaperPosition.symbol == order.symbol,
            )
        )).scalar_one_or_none()

        if order.side == "buy":
            if account.cash_balance < total_cost:
                order.status = "rejected"
                order.rejection_reason = "Insufficient cash"
                await self._session.flush()
                return
            account.cash_balance -= total_cost
            if position:
                total_shares = position.quantity + quantity
                total_cost_basis = position.cost_basis + (fill_price * quantity)
                position.average_price = (total_cost_basis / total_shares).quantize(Decimal("0.01"))
                position.quantity = total_shares
                position.cost_basis = total_cost_basis
            else:
                position = await self._position_repo.create(
                    account_id=account.id,
                    user_id=order.user_id,
                    symbol=order.symbol,
                    quantity=quantity,
                    average_price=fill_price,
                    cost_basis=fill_price * quantity,
                )
            realized_pnl = None
        else:
            if not position or position.quantity < quantity:
                order.status = "rejected"
                order.rejection_reason = "Insufficient shares"
                await self._session.flush()
                return
            proceeds = fill_price * quantity - commission
            avg_cost_per_share = position.average_price
            realized = (fill_price - avg_cost_per_share) * quantity
            account.cash_balance += proceeds
            position.quantity -= quantity
            position.realized_pnl += realized
            position.cost_basis = position.average_price * position.quantity
            realized_pnl = realized

        order.slippage = self._compute_slippage(order, fill_price)
        order.filled_quantity += quantity
        order.status = "filled" if order.filled_quantity >= order.quantity else "partially_filled"
        order.filled_at = now

        trade = await self._trade_repo.create(
            order_id=order.id,
            account_id=account.id,
            user_id=order.user_id,
            symbol=order.symbol,
            side=order.side,
            quantity=quantity,
            price=fill_price,
            commission=commission,
            realized_pnl=realized_pnl,
        )

        if position:
            position.current_price = fill_price
        await self._session.flush()

        await self._track_simulated_order(order, account, trade, fill_price, commission, realized_pnl, now)

    async def _track_simulated_order(
        self, order: PaperOrder, account: PaperAccount, trade: PaperTrade,
        fill_price: Decimal, commission: Decimal, realized_pnl: Decimal | None,
        now: datetime,
    ) -> None:
        if order.side == "buy":
            await self._simulated_repo.create(
                account_id=account.id,
                user_id=order.user_id,
                symbol=order.symbol,
                direction="long",
                entry_price=fill_price,
                quantity=order.filled_quantity,
                entry_fee=commission,
                total_fees=commission,
                slippage=order.slippage,
                entry_order_id=order.id,
                entry_trade_id=trade.id,
                entry_date=now,
                status="open",
            )
        else:
            sim = (await self._session.execute(
                select(SimulatedOrder).where(
                    SimulatedOrder.account_id == account.id,
                    SimulatedOrder.symbol == order.symbol,
                    SimulatedOrder.status == "open",
                ).order_by(SimulatedOrder.entry_date).limit(1)
            )).scalar_one_or_none()
            if sim is None:
                return
            qty = min(order.filled_quantity, sim.quantity)
            gross = (fill_price - sim.entry_price) * qty
            entry_fee_portion = (sim.entry_fee / sim.quantity) * qty if sim.quantity else Decimal("0")
            net = gross - entry_fee_portion - commission
            sim.gross_pnl = (sim.gross_pnl or 0) + gross
            sim.net_pnl = (sim.net_pnl or 0) + net
            sim.exit_price = fill_price
            sim.exit_fee = commission
            sim.total_fees += commission
            sim.exit_order_id = order.id
            sim.exit_trade_id = trade.id
            sim.exit_date = now
            sim.quantity -= qty
            sim.entry_fee -= entry_fee_portion
            if sim.quantity <= 0:
                sim.status = "closed"
                sim.outcome = "win" if sim.net_pnl > 0 else "loss" if sim.net_pnl < 0 else "breakeven"
            await self._session.flush()

    # ── Portfolio ──

    async def get_portfolio(
        self, user_id: int,
    ) -> list[dict[str, Any]]:
        account = await self.get_account(user_id)
        if account is None:
            return []
        positions = (await self._session.execute(
            select(PaperPosition).where(PaperPosition.account_id == account.id)
        )).scalars().all()
        result = []
        for p in positions:
            if p.current_price and p.quantity:
                market_value = p.current_price * p.quantity
                unrealized_pnl = market_value - p.cost_basis
                unrealized_pnl_pct = round(float((p.current_price - p.average_price) / p.average_price * 100), 2) if p.average_price else 0
            else:
                market_value = Decimal("0")
                unrealized_pnl = Decimal("0")
                unrealized_pnl_pct = 0
            sector = await self._position_sector(p.symbol)
            result.append({
                "symbol": p.symbol,
                "sector": sector,
                "quantity": p.quantity,
                "average_price": float(p.average_price),
                "current_price": float(p.current_price) if p.current_price else None,
                "cost_basis": float(p.cost_basis),
                "market_value": float(market_value),
                "realized_pnl": float(p.realized_pnl),
                "unrealized_pnl": float(unrealized_pnl),
                "unrealized_pnl_pct": unrealized_pnl_pct,
                "allocation_pct": round(float(p.cost_basis / account.cash_balance * 100), 2) if account.cash_balance else 0,
            })
        return sorted(result, key=lambda x: x["market_value"], reverse=True)

    async def _position_sector(self, symbol: str) -> str | None:
        result = await self._session.execute(
            select(Company.sector).where(Company.symbol == symbol.upper())
        )
        return result.scalar_one_or_none()

    async def get_sector_exposure(self, user_id: int) -> list[dict]:
        portfolio = await self.get_portfolio(user_id)
        total_value = sum(p["market_value"] for p in portfolio) or 1
        exposure: dict[str, dict] = {}
        for p in portfolio:
            sector = p["sector"] or "Unknown"
            entry = exposure.setdefault(sector, {"sector": sector, "market_value": 0.0, "positions": 0})
            entry["market_value"] += p["market_value"]
            entry["positions"] += 1
        for entry in exposure.values():
            entry["allocation_pct"] = round(entry["market_value"] / total_value * 100, 2)
        return sorted(exposure.values(), key=lambda x: x["market_value"], reverse=True)

    async def get_equity_curve(self, user_id: int) -> list[dict]:
        account = await self.get_account(user_id)
        if account is None:
            return []
        closed = (await self._session.execute(
            select(SimulatedOrder)
            .where(SimulatedOrder.user_id == user_id, SimulatedOrder.status == "closed")
            .order_by(SimulatedOrder.exit_date)
        )).scalars().all()
        positions = (await self._session.execute(
            select(PaperPosition).where(PaperPosition.account_id == account.id)
        )).scalars().all()
        unrealized = Decimal("0")
        for p in positions:
            if p.current_price and p.quantity:
                unrealized += p.current_price * p.quantity - p.cost_basis

        curve: list[dict] = []
        running = account.initial_capital
        for sim in closed:
            running += sim.net_pnl or Decimal("0")
            curve.append({
                "date": (sim.exit_date or datetime.now(timezone.utc)).isoformat(),
                "equity": round(float(running), 2),
                "event": f"{sim.symbol} {sim.outcome or 'closed'}",
            })
        running += unrealized
        curve.append({
            "date": datetime.now(timezone.utc).isoformat(),
            "equity": round(float(running), 2),
            "event": "current",
        })
        return curve

    async def refresh_prices(self, user_id: int) -> int:
        account = await self.get_account(user_id)
        if account is None:
            return 0
        positions = (await self._session.execute(
            select(PaperPosition).where(PaperPosition.account_id == account.id)
        )).scalars().all()
        updated = 0
        for p in positions:
            latest = await self._price_service.get_latest_price(p.symbol)
            if latest:
                p.current_price = Decimal(str(latest.close))
                updated += 1
        await self._session.flush()
        return updated

    # ── PnL ──

    async def get_pnl_summary(self, user_id: int) -> dict[str, Any]:
        account = await self.get_account(user_id)
        if account is None:
            return {"total_realized_pnl": 0, "total_unrealized_pnl": 0, "total_pnl": 0, "total_pnl_pct": 0}
        positions = (await self._session.execute(
            select(PaperPosition).where(PaperPosition.account_id == account.id)
        )).scalars().all()
        total_realized = sum(p.realized_pnl for p in positions)
        total_unrealized = Decimal("0")
        total_cost = Decimal("0")
        for p in positions:
            total_cost += p.cost_basis
            if p.current_price and p.quantity:
                mkt_val = p.current_price * p.quantity
                total_unrealized += mkt_val - p.cost_basis
        total_pnl = total_realized + total_unrealized
        pnl_pct = round(float(total_pnl / account.initial_capital * 100), 2) if account.initial_capital else 0
        return {
            "initial_capital": float(account.initial_capital),
            "cash_balance": float(account.cash_balance),
            "total_realized_pnl": float(total_realized),
            "total_unrealized_pnl": float(total_unrealized),
            "total_pnl": float(total_pnl),
            "total_pnl_pct": pnl_pct,
        }

    # ── Reports ──

    async def get_trade_history(
        self, user_id: int, skip: int = 0, limit: int = 50,
    ) -> tuple[Sequence[PaperTrade], int]:
        count_stmt = select(func.count()).select_from(PaperTrade).where(PaperTrade.user_id == user_id)
        total = (await self._session.execute(count_stmt)).scalar() or 0
        stmt = (
            select(PaperTrade)
            .where(PaperTrade.user_id == user_id)
            .order_by(desc(PaperTrade.trade_time))
            .offset(skip).limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows), total

    # ── Simulated Orders ──

    async def list_simulated_orders(
        self, user_id: int, status: str | None = None,
        outcome: str | None = None, skip: int = 0, limit: int = 50,
    ) -> tuple[Sequence[SimulatedOrder], int]:
        stmt = select(SimulatedOrder).where(SimulatedOrder.user_id == user_id)
        count_stmt = select(func.count()).select_from(SimulatedOrder).where(SimulatedOrder.user_id == user_id)
        if status:
            stmt = stmt.where(SimulatedOrder.status == status)
            count_stmt = count_stmt.where(SimulatedOrder.status == status)
        if outcome:
            stmt = stmt.where(SimulatedOrder.outcome == outcome)
            count_stmt = count_stmt.where(SimulatedOrder.outcome == outcome)
        total = (await self._session.execute(count_stmt)).scalar() or 0
        stmt = stmt.order_by(desc(SimulatedOrder.entry_date)).offset(skip).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows), total

    async def get_simulated_order(self, order_id: int, user_id: int) -> SimulatedOrder | None:
        sim = await self._simulated_repo.get(order_id)
        if sim is None or sim.user_id != user_id:
            return None
        return sim

    async def get_performance_report(self, user_id: int) -> dict[str, Any]:
        account = await self.get_account(user_id)
        if account is None:
            return {}
        summary = await self.get_account_summary(user_id)
        trades_count_stmt = select(func.count()).select_from(PaperTrade).where(PaperTrade.user_id == user_id)
        total_trades = (await self._session.execute(trades_count_stmt)).scalar() or 0
        filled_orders_stmt = select(func.count()).select_from(PaperOrder).where(
            PaperOrder.user_id == user_id, PaperOrder.status == "filled",
        )
        filled_count = (await self._session.execute(filled_orders_stmt)).scalar() or 0
        cancelled_stmt = select(func.count()).select_from(PaperOrder).where(
            PaperOrder.user_id == user_id, PaperOrder.status == "cancelled",
        )
        cancelled_count = (await self._session.execute(cancelled_stmt)).scalar() or 0
        win_stmt = select(func.count()).select_from(PaperTrade).where(
            PaperTrade.user_id == user_id,
            PaperTrade.side == "sell",
            PaperTrade.realized_pnl.isnot(None),
            PaperTrade.realized_pnl > 0,
        )
        win_count = (await self._session.execute(win_stmt)).scalar() or 0
        loss_stmt = select(func.count()).select_from(PaperTrade).where(
            PaperTrade.user_id == user_id,
            PaperTrade.side == "sell",
            PaperTrade.realized_pnl.isnot(None),
            PaperTrade.realized_pnl < 0,
        )
        loss_count = (await self._session.execute(loss_stmt)).scalar() or 0
        total_closed = win_count + loss_count
        win_rate = round(win_count / total_closed * 100, 2) if total_closed else 0
        return {
            "account": summary,
            "total_trades": total_trades,
            "filled_orders": filled_count,
            "cancelled_orders": cancelled_count,
            "winning_trades": win_count,
            "losing_trades": loss_count,
            "win_rate": win_rate,
        }
