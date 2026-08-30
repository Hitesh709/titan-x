import csv
import io
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.price import AdjustedPrice, CorporateAction, DailyPrice

logger = structlog.get_logger(__name__)


class PriceValidationError(ValueError):
    pass


@dataclass
class LivePriceSnapshot:
    id: int | None
    symbol: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


class BulkImportResult:
    def __init__(self) -> None:
        self.total = 0
        self.created = 0
        self.skipped_duplicates = 0
        self.errors: list[dict[str, Any]] = []
        self.warnings: list[str] = []


def validate_ohlcv(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if row.get("high", 0) < row.get("low", 0):
        errors.append("high must be >= low")
    if not (row.get("low", 0) <= row.get("open", 0) <= row.get("high", 0)):
        errors.append("open must be between low and high")
    if not (row.get("low", 0) <= row.get("close", 0) <= row.get("high", 0)):
        errors.append("close must be between low and high")
    if row.get("volume", 0) < 0:
        errors.append("volume must be non-negative")
    if any(row.get(k, 0) <= 0 for k in ("open", "high", "low", "close")):
        errors.append("open, high, low, close must be positive")
    return errors


class PriceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._price_repo = BaseRepository(session, DailyPrice)
        self._ca_repo = BaseRepository(session, CorporateAction)
        self._adj_repo = BaseRepository(session, AdjustedPrice)

    async def create_price(
        self,
        symbol: str,
        trade_date: date,
        open: float,
        high: float,
        low: float,
        close: float,
        volume: int,
    ) -> DailyPrice:
        errors = validate_ohlcv(
            {"open": open, "high": high, "low": low, "close": close, "volume": volume}
        )
        if errors:
            raise PriceValidationError("; ".join(errors))
        existing = await self._session.execute(
            select(DailyPrice).where(
                DailyPrice.symbol == symbol.upper(),
                DailyPrice.trade_date == trade_date,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError(f"Price already exists for {symbol.upper()} on {trade_date}")
        return await self._price_repo.create(
            symbol=symbol.upper(),
            trade_date=trade_date,
            open=open,
            high=high,
            low=low,
            close=close,
            volume=volume,
        )

    async def get_prices(
        self,
        symbol: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        skip: int = 0,
        limit: int = 100,
        order_by: str = "trade_date",
        descending: bool = True,
    ) -> tuple[Sequence[DailyPrice], int]:
        stmt = select(DailyPrice).where(DailyPrice.symbol == symbol.upper())
        if start_date:
            stmt = stmt.where(DailyPrice.trade_date >= start_date)
        if end_date:
            stmt = stmt.where(DailyPrice.trade_date <= end_date)
        total = len((await self._session.execute(stmt)).scalars().all())
        order_column = getattr(DailyPrice, order_by, DailyPrice.trade_date)
        result = await self._session.execute(
            stmt.order_by(order_column.desc() if descending else order_column.asc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def delete_price(self, price_id: int) -> bool:
        return await self._price_repo.delete(price_id)

    async def bulk_import(
        self, symbol: str, records: list[dict[str, Any]]
    ) -> BulkImportResult:
        result = BulkImportResult()
        result.total = len(records)
        symbol = symbol.upper()
        for i, row in enumerate(records):
            row_errors = validate_ohlcv(row)
            if row_errors:
                result.errors.append({"row": i, "errors": row_errors, "data": row})
                continue
            try:
                trade_date = (
                    row["trade_date"]
                    if isinstance(row["trade_date"], date)
                    else date.fromisoformat(str(row["trade_date"]))
                )
            except (ValueError, KeyError) as exc:
                result.errors.append(
                    {"row": i, "errors": [f"invalid trade_date: {exc}"], "data": row}
                )
                continue
            existing = await self._session.execute(
                select(DailyPrice).where(
                    DailyPrice.symbol == symbol,
                    DailyPrice.trade_date == trade_date,
                )
            )
            if existing.scalar_one_or_none() is not None:
                result.skipped_duplicates += 1
                continue
            try:
                await self._price_repo.create(
                    symbol=symbol,
                    trade_date=trade_date,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row["volume"]),
                )
                result.created += 1
            except Exception as exc:
                result.errors.append(
                    {"row": i, "errors": [str(exc)], "data": row}
                )
        return result

    async def bulk_import_csv(
        self, symbol: str, csv_content: str
    ) -> BulkImportResult:
        reader = csv.DictReader(io.StringIO(csv_content))
        records = [
            {
                "trade_date": row.get("trade_date", row.get("date", "")),
                "open": float(row.get("open", 0)),
                "high": float(row.get("high", 0)),
                "low": float(row.get("low", 0)),
                "close": float(row.get("close", 0)),
                "volume": int(row.get("volume", 0)),
            }
            for row in reader
        ]
        return await self.bulk_import(symbol, records)

    async def get_latest_price(
        self, symbol: str
    ) -> LivePriceSnapshot | DailyPrice | None:
        """Return current NSE LTP as a detached snapshot; never overwrite history."""
        result = await self._session.execute(
            select(DailyPrice)
            .where(DailyPrice.symbol == symbol.upper())
            .order_by(DailyPrice.trade_date.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        try:
            from titan_x.services.market_data_service import MarketDataService

            quote = await MarketDataService(self._session).get_quote(symbol)
            live_price = quote.get("last_price")
            if live_price is not None and float(live_price) > 0:
                live = float(live_price)
                return LivePriceSnapshot(
                    id=getattr(latest, "id", None),
                    symbol=symbol.upper(),
                    trade_date=getattr(latest, "trade_date", date.today()),
                    open=float(getattr(latest, "open", live)),
                    high=max(float(getattr(latest, "high", live)), live),
                    low=min(float(getattr(latest, "low", live)), live),
                    close=live,
                    volume=int(
                        quote.get("volume") or getattr(latest, "volume", 0) or 0
                    ),
                )
        except Exception as exc:
            logger.warning("live_price_unavailable", symbol=symbol, error=str(exc))
        return latest

    async def compute_adjusted_prices(self, symbol: str) -> int:
        symbol = symbol.upper()
        actions = await self._session.execute(
            select(CorporateAction)
            .where(CorporateAction.symbol == symbol)
            .order_by(CorporateAction.action_date.asc())
        )
        corp_actions = list(actions.scalars().all())
        prices = await self._session.execute(
            select(DailyPrice)
            .where(DailyPrice.symbol == symbol)
            .order_by(DailyPrice.trade_date.desc())
        )
        all_prices = list(prices.scalars().all())
        if not all_prices:
            return 0
        cum_factor = 1.0
        action_map = {
            ca.action_date: ca.adjustment_factor
            for ca in corp_actions
            if ca.adjustment_factor
        }
        await self._session.execute(
            delete(AdjustedPrice).where(AdjustedPrice.symbol == symbol)
        )
        count = 0
        for price in reversed(all_prices):
            if price.trade_date in action_map:
                cum_factor *= action_map[price.trade_date]
            self._session.add(
                AdjustedPrice(
                    symbol=symbol,
                    trade_date=price.trade_date,
                    open=round(price.open * cum_factor, 2),
                    high=round(price.high * cum_factor, 2),
                    low=round(price.low * cum_factor, 2),
                    close=round(price.close * cum_factor, 2),
                    volume=price.volume,
                    adjustment_factor=cum_factor,
                )
            )
            count += 1
        await self._session.flush()
        logger.info("adjusted_prices_computed", symbol=symbol, count=count)
        return count


class CorporateActionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = BaseRepository(session, CorporateAction)

    async def create(
        self,
        symbol: str,
        action_date: date,
        action_type: str,
        description: str | None = None,
        ratio_numerator: float | None = None,
        ratio_denominator: float | None = None,
        dividend_amount: float | None = None,
        adjustment_factor: float | None = None,
    ) -> CorporateAction:
        existing = await self._session.execute(
            select(CorporateAction).where(
                CorporateAction.symbol == symbol.upper(),
                CorporateAction.action_date == action_date,
                CorporateAction.action_type == action_type,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError(
                f"Corporate action already exists for {symbol.upper()} on {action_date}"
            )
        return await self._repo.create(
            symbol=symbol.upper(),
            action_date=action_date,
            action_type=action_type,
            description=description,
            ratio_numerator=ratio_numerator,
            ratio_denominator=ratio_denominator,
            dividend_amount=dividend_amount,
            adjustment_factor=adjustment_factor,
        )

    async def list_for_symbol(
        self, symbol: str, *, skip: int = 0, limit: int = 100
    ) -> tuple[Sequence[CorporateAction], int]:
        stmt = (
            select(CorporateAction)
            .where(CorporateAction.symbol == symbol.upper())
            .order_by(CorporateAction.action_date.desc())
        )
        total = len((await self._session.execute(stmt)).scalars().all())
        result = await self._session.execute(stmt.offset(skip).limit(limit))
        return list(result.scalars().all()), total

    async def delete(self, action_id: int) -> bool:
        return await self._repo.delete(action_id)
