import csv
import io
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.company import Company
from titan_x.models.order import Order, OrderFill, Position
from titan_x.models.portfolio import Portfolio, PortfolioHolding, PortfolioTransaction
from titan_x.models.price import DailyPrice


class DataImportExportService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def import_daily_prices_csv(self, content: str) -> dict:
        reader = csv.DictReader(io.StringIO(content))
        inserted = 0
        skipped = 0
        for row in reader:
            symbol = row.get("symbol", "").upper()
            trade_date_str = row.get("trade_date", "")
            if not symbol or not trade_date_str:
                skipped += 1
                continue
            try:
                trade_date = datetime.strptime(trade_date_str.strip(), "%Y-%m-%d").date()
            except ValueError:
                skipped += 1
                continue

            existing = await self.session.execute(
                select(DailyPrice).where(
                    DailyPrice.symbol == symbol,
                    DailyPrice.trade_date == trade_date,
                )
            )
            if existing.scalar_one_or_none() is not None:
                skipped += 1
                continue

            dp = DailyPrice(
                symbol=symbol,
                trade_date=trade_date,
                open=float(row.get("open", 0)),
                high=float(row.get("high", 0)),
                low=float(row.get("low", 0)),
                close=float(row.get("close", 0)),
                volume=int(float(row.get("volume", 0))),
            )
            self.session.add(dp)
            inserted += 1

        await self.session.flush()
        return {"inserted": inserted, "skipped": skipped}

    async def import_companies_csv(self, content: str) -> dict:
        reader = csv.DictReader(io.StringIO(content))
        inserted = 0
        skipped = 0
        for row in reader:
            symbol = row.get("symbol", "").upper()
            if not symbol:
                skipped += 1
                continue
            existing = await self.session.execute(
                select(Company).where(Company.symbol == symbol)
            )
            if existing.scalar_one_or_none() is not None:
                skipped += 1
                continue

            company = Company(
                symbol=symbol,
                company_name=row.get("company_name", symbol),
                isin=row.get("isin", f"IN{symbol}001"),
                sector=row.get("sector", ""),
                industry=row.get("industry", ""),
                exchange=row.get("exchange", "NSE"),
                market_cap=int(float(row["market_cap"])) if row.get("market_cap") else None,
            )
            self.session.add(company)
            inserted += 1

        await self.session.flush()
        return {"inserted": inserted, "skipped": skipped}

    async def export_daily_prices_csv(self, symbol: str, start: date | None = None, end: date | None = None) -> str:
        q = select(DailyPrice).where(DailyPrice.symbol == symbol.upper()).order_by(DailyPrice.trade_date)
        if start:
            q = q.where(DailyPrice.trade_date >= start)
        if end:
            q = q.where(DailyPrice.trade_date <= end)
        result = await self.session.execute(q)
        prices = result.scalars().all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["symbol", "trade_date", "open", "high", "low", "close", "volume"])
        for p in prices:
            writer.writerow([p.symbol, p.trade_date, p.open, p.high, p.low, p.close, p.volume])
        return output.getvalue()

    async def export_positions_csv(self, user_id: int) -> str:
        result = await self.session.execute(
            select(Position).where(Position.user_id == user_id).order_by(Position.symbol)
        )
        positions = result.scalars().all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["symbol", "quantity", "average_price", "cost_basis", "realized_pnl", "unrealized_pnl"])
        for p in positions:
            writer.writerow([p.symbol, p.quantity, p.average_price, p.cost_basis, p.realized_pnl, p.unrealized_pnl])
        return output.getvalue()

    async def export_orders_csv(self, user_id: int) -> str:
        result = await self.session.execute(
            select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc())
        )
        orders = result.scalars().all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "symbol", "side", "order_type", "quantity", "filled_quantity", "price", "status", "created_at"])
        for o in orders:
            writer.writerow([o.id, o.symbol, o.side, o.order_type, o.quantity, o.filled_quantity, o.price, o.status, o.created_at])
        return output.getvalue()

    async def export_portfolio_csv(self, portfolio_id: int) -> str:
        result = await self.session.execute(
            select(PortfolioHolding).where(PortfolioHolding.portfolio_id == portfolio_id)
        )
        holdings = result.scalars().all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["symbol", "quantity", "average_price", "current_price", "weight", "pnl"])
        for h in holdings:
            writer.writerow([h.symbol, h.quantity, h.average_price, h.current_price, h.weight, h.pnl])
        return output.getvalue()
