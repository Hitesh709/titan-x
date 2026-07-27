from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.price import AdjustedPrice, CorporateAction, DailyPrice

logger = structlog.get_logger(__name__)


class AdjustmentEngine:
    """Pure computation of adjustment factors for each corporate action type."""

    @staticmethod
    def split_factor(numerator: float, denominator: float) -> float:
        if denominator <= 0 or numerator <= 0:
            raise ValueError("Split ratio must be positive")
        return denominator / numerator

    @staticmethod
    def bonus_factor(numerator: float, denominator: float) -> float:
        if denominator <= 0 or numerator <= 0:
            raise ValueError("Bonus ratio must be positive")
        return denominator / (denominator + numerator)

    @staticmethod
    def rights_factor(numerator: float, denominator: float, premium: float, issue_price: float) -> float:
        if denominator <= 0 or numerator <= 0:
            raise ValueError("Rights ratio must be positive")
        if premium <= 0:
            raise ValueError("Premium must be positive")
        total_shares = denominator + numerator
        total_value = (denominator * premium) + (numerator * issue_price)
        theoretical_price = total_value / total_shares
        return theoretical_price / premium

    @staticmethod
    def dividend_factor(close_price: float, dividend_amount: float) -> float:
        if close_price <= 0:
            raise ValueError("Close price must be positive")
        if dividend_amount < 0:
            raise ValueError("Dividend cannot be negative")
        return (close_price - dividend_amount) / close_price

    @staticmethod
    def merger_factor(numerator: float, denominator: float) -> float:
        if denominator <= 0 or numerator <= 0:
            raise ValueError("Merger ratio must be positive")
        return denominator / numerator

    @staticmethod
    def acquisition_factor(numerator: float, denominator: float) -> float:
        if denominator <= 0 or numerator <= 0:
            raise ValueError("Acquisition ratio must be positive")
        return denominator / numerator


class CorporateActionEngine:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = BaseRepository(session, CorporateAction)

    async def record_split(
        self, symbol: str, action_date: date, numerator: float, denominator: float,
        description: str | None = None,
    ) -> CorporateAction:
        factor = AdjustmentEngine.split_factor(numerator, denominator)
        return await self._create_action(
            symbol=symbol, action_date=action_date, action_type="split",
            ratio_numerator=numerator, ratio_denominator=denominator,
            adjustment_factor=factor, description=description,
        )

    async def record_bonus(
        self, symbol: str, action_date: date, numerator: float, denominator: float,
        description: str | None = None,
    ) -> CorporateAction:
        factor = AdjustmentEngine.bonus_factor(numerator, denominator)
        return await self._create_action(
            symbol=symbol, action_date=action_date, action_type="bonus",
            ratio_numerator=numerator, ratio_denominator=denominator,
            adjustment_factor=factor, description=description,
        )

    async def record_dividend(
        self, symbol: str, action_date: date, dividend_amount: float,
        description: str | None = None,
    ) -> CorporateAction:
        prev_close = await self._get_prev_close(symbol, action_date)
        factor = AdjustmentEngine.dividend_factor(prev_close, dividend_amount) if prev_close else 1.0
        return await self._create_action(
            symbol=symbol, action_date=action_date, action_type="dividend",
            dividend_amount=dividend_amount, adjustment_factor=factor,
            description=description,
        )

    async def record_rights(
        self, symbol: str, action_date: date,
        numerator: float, denominator: float,
        premium: float, issue_price: float,
        description: str | None = None,
    ) -> CorporateAction:
        factor = AdjustmentEngine.rights_factor(numerator, denominator, premium, issue_price)
        return await self._create_action(
            symbol=symbol, action_date=action_date, action_type="rights",
            ratio_numerator=numerator, ratio_denominator=denominator,
            rights_premium=premium, rights_issue_price=issue_price,
            adjustment_factor=factor, description=description,
        )

    async def record_merger(
        self, symbol: str, action_date: date,
        numerator: float, denominator: float,
        new_symbol: str, description: str | None = None,
    ) -> CorporateAction:
        factor = AdjustmentEngine.merger_factor(numerator, denominator)
        return await self._create_action(
            symbol=symbol, action_date=action_date, action_type="merger",
            ratio_numerator=numerator, ratio_denominator=denominator,
            adjustment_factor=factor, new_symbol=new_symbol,
            description=description,
        )

    async def record_acquisition(
        self, symbol: str, action_date: date,
        numerator: float, denominator: float,
        old_symbol: str, description: str | None = None,
    ) -> CorporateAction:
        factor = AdjustmentEngine.acquisition_factor(numerator, denominator)
        return await self._create_action(
            symbol=symbol, action_date=action_date, action_type="acquisition",
            ratio_numerator=numerator, ratio_denominator=denominator,
            adjustment_factor=factor, old_symbol=old_symbol,
            description=description,
        )

    async def adjust_prices(self, symbol: str) -> dict[str, Any]:
        symbol = symbol.upper()
        actions = await self._session.execute(
            select(CorporateAction)
            .where(CorporateAction.symbol == symbol)
            .order_by(CorporateAction.action_date.asc())
        )
        corp_actions: list[CorporateAction] = list(actions.scalars().all())

        prices = await self._session.execute(
            select(DailyPrice)
            .where(DailyPrice.symbol == symbol)
            .order_by(DailyPrice.trade_date.desc())
        )
        all_prices: list[DailyPrice] = list(prices.scalars().all())

        if not all_prices:
            return {"symbol": symbol, "actions_used": len(corp_actions), "prices_adjusted": 0}

        cum_factor: float = 1.0
        action_map: dict[date, tuple[float, str]] = {}
        for ca in corp_actions:
            if ca.adjustment_factor:
                action_map[ca.action_date] = (ca.adjustment_factor, ca.action_type)

        await self._session.execute(
            delete(AdjustedPrice).where(AdjustedPrice.symbol == symbol)
        )

        count: int = 0
        for price in reversed(all_prices):
            if price.trade_date in action_map:
                factor, atype = action_map[price.trade_date]
                cum_factor *= factor
                logger.debug("adjustment_applied", symbol=symbol, date=price.trade_date,
                             type=atype, factor=factor, cumulative=cum_factor)

            adjusted = AdjustedPrice(
                symbol=symbol, trade_date=price.trade_date,
                open=round(price.open * cum_factor, 2),
                high=round(price.high * cum_factor, 2),
                low=round(price.low * cum_factor, 2),
                close=round(price.close * cum_factor, 2),
                volume=price.volume,
                adjustment_factor=round(cum_factor, 6),
            )
            self._session.add(adjusted)
            count += 1

        await self._session.flush()
        logger.info("prices_adjusted", symbol=symbol, count=count, actions=len(corp_actions))
        return {"symbol": symbol, "actions_used": len(corp_actions), "prices_adjusted": count}

    async def list_actions(
        self, symbol: str, *, skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[CorporateAction], int]:
        stmt = select(CorporateAction).where(
            CorporateAction.symbol == symbol.upper()
        ).order_by(CorporateAction.action_date.desc())
        count_stmt = stmt
        total_result = await self._session.execute(count_stmt)
        total = len(total_result.scalars().all())
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    async def list_all_by_type(
        self, action_type: str, *, skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[CorporateAction], int]:
        stmt = select(CorporateAction).where(
            CorporateAction.action_type == action_type
        ).order_by(CorporateAction.action_date.desc())
        count_stmt = stmt
        total_result = await self._session.execute(count_stmt)
        total = len(total_result.scalars().all())
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    async def get_action(self, action_id: int) -> CorporateAction | None:
        return await self._repo.get(action_id)

    async def delete_action(self, action_id: int) -> bool:
        return await self._repo.delete(action_id)

    async def _create_action(
        self, symbol: str, action_date: date, action_type: str,
        **kwargs: Any,
    ) -> CorporateAction:
        symbol = symbol.upper()
        existing = await self._session.execute(
            select(CorporateAction).where(
                CorporateAction.symbol == symbol,
                CorporateAction.action_date == action_date,
                CorporateAction.action_type == action_type,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError(f"{action_type} already recorded for {symbol} on {action_date}")
        return await self._repo.create(
            symbol=symbol, action_date=action_date, action_type=action_type,
            **{k: v for k, v in kwargs.items() if v is not None},
        )

    async def _get_prev_close(self, symbol: str, trade_date: date) -> float | None:
        result = await self._session.execute(
            select(DailyPrice)
            .where(
                DailyPrice.symbol == symbol.upper(),
                DailyPrice.trade_date < trade_date,
            )
            .order_by(DailyPrice.trade_date.desc())
            .limit(1)
        )
        price = result.scalar_one_or_none()
        return price.close if price else None
