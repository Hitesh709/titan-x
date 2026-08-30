from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.paper_trading import PaperAccount, PaperPosition
from titan_x.services.market_data_service import MarketDataService


class LivePortfolioMarkService:
    """Mark paper positions from the configured real market-data provider.

    This service deliberately has no synthetic-price fallback. If a live quote
    cannot be obtained, that position is left unchanged and the caller can
    surface the unavailable feed rather than presenting a fabricated price.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.market_data = MarketDataService(session)

    async def refresh_user(self, user_id: int) -> dict:
        account = (
            await self.session.execute(
                select(PaperAccount).where(PaperAccount.user_id == user_id)
            )
        ).scalar_one_or_none()
        if account is None:
            return {"updated_positions": 0, "failed_symbols": [], "live": True}

        positions = (
            await self.session.execute(
                select(PaperPosition).where(
                    PaperPosition.account_id == account.id,
                    PaperPosition.quantity > 0,
                )
            )
        ).scalars().all()
        if not positions:
            return {"updated_positions": 0, "failed_symbols": [], "live": True}

        symbols = [p.symbol for p in positions]
        response = await self.market_data.get_quotes(symbols)
        quotes = {
            str(q.get("symbol", "")).upper(): q
            for q in response.get("quotes", [])
            if q.get("last_price") is not None and float(q["last_price"]) > 0
        }

        updated = 0
        failed: list[str] = []
        for position in positions:
            quote = quotes.get(position.symbol.upper())
            if quote is None:
                failed.append(position.symbol.upper())
                continue
            position.current_price = Decimal(str(quote["last_price"]))
            updated += 1

        await self.session.flush()
        return {
            "updated_positions": updated,
            "failed_symbols": failed,
            "live": True,
            "provider": response.get("provider"),
            "source": response.get("source"),
        }
