from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.portfolio import Portfolio, PortfolioHolding, PortfolioTransaction
from titan_x.models.order import Order, OrderFill, Position


class ReportGenerator:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def generate_portfolio_report(self, portfolio_id: int) -> str:
        portfolio = await self.session.get(Portfolio, portfolio_id)
        if portfolio is None:
            raise ValueError("Portfolio not found")

        result = await self.session.execute(
            select(PortfolioHolding).where(PortfolioHolding.portfolio_id == portfolio_id)
        )
        holdings = result.scalars().all()

        result = await self.session.execute(
            select(PortfolioTransaction).where(
                PortfolioTransaction.portfolio_id == portfolio_id
            ).order_by(PortfolioTransaction.created_at.desc()).limit(20)
        )
        transactions = result.scalars().all()

        total_value = sum(float(h.average_price or 0) * h.quantity for h in holdings)
        total_pnl = 0

        html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Portfolio Report - {portfolio.name}</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 20px; }}
h1 {{ color: #333; }}
table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background-color: #4CAF50; color: white; }}
tr:nth-child(even) {{ background-color: #f2f2f2; }}
.section {{ margin: 20px 0; }}
.summary {{ background: #f9f9f9; padding: 15px; border-radius: 5px; }}
</style></head>
<body>
<h1>Portfolio Report: {portfolio.name}</h1>
<p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
<div class="summary">
<p><strong>Total Value:</strong> ${total_value:,.2f}</p>
<p><strong>Total P&L:</strong> ${total_pnl:,.2f}</p>
<p><strong>Holdings:</strong> {len(holdings)}</p>
</div>
<div class="section">
<h2>Holdings</h2>
<table>
<tr><th>Symbol</th><th>Quantity</th><th>Avg Price</th><th>Current Price</th><th>P&L</th></tr>
"""
        for h in holdings:
            html += f"<tr><td>{h.symbol}</td><td>{h.quantity}</td><td>${h.average_price:,.2f}</td><td>${float(h.cost_basis or 0) / max(h.quantity, 1):,.2f}</td><td>-</td></tr>\n"

        html += """</table></div>"""

        if transactions:
            html += """<div class="section"><h2>Recent Transactions</h2><table><tr><th>Date</th><th>Symbol</th><th>Type</th><th>Quantity</th><th>Price</th></tr>"""
            for t in transactions:
                html += f"<tr><td>{t.created_at.strftime('%Y-%m-%d') if t.created_at else ''}</td><td>{t.symbol}</td><td>{t.transaction_type}</td><td>{t.quantity}</td><td>${t.price or 0:,.2f}</td></tr>\n"
            html += "</table></div>"

        html += "</body></html>"
        return html

    async def generate_pnl_statement(self, user_id: int, start: date | None = None, end: date | None = None) -> str:
        q = select(Order).where(Order.user_id == user_id, Order.status == "filled").order_by(Order.created_at.desc())
        if start:
            q = q.where(Order.created_at >= datetime.combine(start, datetime.min.time()))
        if end:
            q = q.where(Order.created_at <= datetime.combine(end, datetime.max.time()))
        result = await self.session.execute(q)
        orders = result.scalars().all()

        total_realized = sum(
            sum(f.realized_pnl or 0 for f in o.fills)
            for o in orders if o.fills
        )

        result = await self.session.execute(
            select(Position).where(Position.user_id == user_id)
        )
        positions = result.scalars().all()

        html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>P&L Statement</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 20px; }}
h1 {{ color: #333; }}
table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background-color: #2196F3; color: white; }}
.positive {{ color: green; }} .negative {{ color: red; }}
</style></head>
<body>
<h1>P&L Statement</h1>
<p>User ID: {user_id} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
<p><strong>Total Realized P&L:</strong> <span class="{'positive' if total_realized >= 0 else 'negative'}">${total_realized:,.2f}</span></p>

<h2>Open Positions</h2>
<table><tr><th>Symbol</th><th>Qty</th><th>Avg Price</th><th>Cost Basis</th><th>Unrealized P&L</th><th>Realized P&L</th></tr>
"""
        for p in positions:
            sign = "positive" if p.unrealized_pnl >= 0 else "negative"
            html += f"<tr><td>{p.symbol}</td><td>{p.quantity}</td><td>${p.average_price:,.2f}</td><td>${p.cost_basis:,.2f}</td><td class='{sign}'>${p.unrealized_pnl:,.2f}</td><td>${p.realized_pnl:,.2f}</td></tr>\n"

        html += """</table></body></html>"""
        return html

    async def generate_tax_report(self, user_id: int, fiscal_year: int) -> str:
        result = await self.session.execute(
            select(OrderFill).where(
                OrderFill.realized_pnl.isnot(None)
            ).order_by(OrderFill.fill_time.desc())
        )
        fills = result.scalars().all()

        total_gain = sum(f.realized_pnl or 0 for f in fills if (f.realized_pnl or 0) > 0)
        total_loss = sum(f.realized_pnl or 0 for f in fills if (f.realized_pnl or 0) < 0)

        html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Tax Report FY {fiscal_year}</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 20px; }}
h1 {{ color: #333; }}
table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background-color: #FF9800; color: white; }}
</style></head>
<body>
<h1>Tax Report - Fiscal Year {fiscal_year}</h1>
<p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
<p><strong>Total Realized Gains:</strong> ${total_gain:,.2f}</p>
<p><strong>Total Realized Losses:</strong> ${total_loss:,.2f}</p>
<p><strong>Net P&L:</strong> ${total_gain + total_loss:,.2f}</p>

<h2>Realized Trades</h2>
<table><tr><th>Date</th><th>Symbol</th><th>Side</th><th>Qty</th><th>Price</th><th>P&L</th></tr>
"""
        for f in fills:
            html += f"<tr><td>{f.fill_time.strftime('%Y-%m-%d')}</td><td>{f.symbol}</td><td>{f.side}</td><td>{f.quantity}</td><td>${f.price:,.2f}</td><td>${f.realized_pnl or 0:,.2f}</td></tr>\n"

        html += "</table></body></html>"
        return html
