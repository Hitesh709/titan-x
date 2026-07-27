import math
from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.intraday import IntradayPrice
from titan_x.models.price import DailyPrice

logger = structlog.get_logger(__name__)

RESOLUTIONS: list[str] = ["1min", "5min", "15min", "hourly"]
RESOLUTION_MINUTES: dict[str, int] = {"1min": 1, "5min": 5, "15min": 15, "hourly": 60}


def _round_timestamp(dt: datetime, resolution: str) -> datetime:
    minutes: int = RESOLUTION_MINUTES[resolution]
    ts_minutes: int = dt.minute
    rounded_minutes: int = (ts_minutes // minutes) * minutes
    return dt.replace(minute=rounded_minutes, second=0, microsecond=0)


def _validate(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for i, row in enumerate(bars):
        row_errors: list[str] = []
        if row.get("high", 0) < row.get("low", 0):
            row_errors.append("high must be >= low")
        if not (row.get("low", 0) <= row.get("open", 0) <= row.get("high", 0)):
            row_errors.append("open must be between low and high")
        if not (row.get("low", 0) <= row.get("close", 0) <= row.get("high", 0)):
            row_errors.append("close must be between low and high")
        if row.get("volume", 0) < 0:
            row_errors.append("volume must be non-negative")
        if row.get("open", 0) <= 0 or row.get("high", 0) <= 0 or row.get("low", 0) <= 0 or row.get("close", 0) <= 0:
            row_errors.append("prices must be positive")
        if row_errors:
            errors.append({"row": i, "errors": row_errors, "data": row})
    return errors


class IntradayService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = BaseRepository(session, IntradayPrice)

    async def create_bar(
        self, symbol: str, timestamp: datetime, resolution: str,
        open: float, high: float, low: float, close: float, volume: int,
    ) -> IntradayPrice:
        symbol = symbol.upper()
        errors = _validate([{"open": open, "high": high, "low": low, "close": close, "volume": volume}])
        if errors:
            raise ValueError(f"Validation error: {errors[0]['errors']}")

        ts = _round_timestamp(timestamp, resolution)
        existing = await self._session.execute(
            select(IntradayPrice).where(
                IntradayPrice.symbol == symbol,
                IntradayPrice.timestamp == ts,
                IntradayPrice.resolution == resolution,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError(f"Bar already exists for {symbol} at {ts} ({resolution})")

        return await self._repo.create(
            symbol=symbol, timestamp=ts, resolution=resolution,
            open=open, high=high, low=low, close=close, volume=volume,
        )

    async def get_bars(
        self, symbol: str, resolution: str,
        start: datetime | None = None, end: datetime | None = None,
        skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[IntradayPrice], int]:
        symbol = symbol.upper()
        stmt = select(IntradayPrice).where(
            IntradayPrice.symbol == symbol,
            IntradayPrice.resolution == resolution,
        )
        if start:
            stmt = stmt.where(IntradayPrice.timestamp >= start)
        if end:
            stmt = stmt.where(IntradayPrice.timestamp <= end)
        count_stmt = stmt
        total_result = await self._session.execute(count_stmt)
        total = len(total_result.scalars().all())
        stmt = stmt.order_by(IntradayPrice.timestamp.desc())
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    async def bulk_import(
        self, symbol: str, resolution: str, records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        symbol = symbol.upper()
        validation_errors = _validate(records)
        if validation_errors:
            return {"total": len(records), "created": 0, "skipped_duplicates": 0, "errors": validation_errors}

        created: int = 0
        skipped: int = 0
        errors: list[dict[str, Any]] = []

        for i, row in enumerate(records):
            try:
                ts: datetime = row["timestamp"] if isinstance(row["timestamp"], datetime) else datetime.fromisoformat(str(row["timestamp"]))
                ts = _round_timestamp(ts, resolution)
            except (ValueError, KeyError) as exc:
                errors.append({"row": i, "errors": [f"invalid timestamp: {exc}"], "data": row})
                continue

            existing = await self._session.execute(
                select(IntradayPrice).where(
                    IntradayPrice.symbol == symbol,
                    IntradayPrice.timestamp == ts,
                    IntradayPrice.resolution == resolution,
                )
            )
            if existing.scalar_one_or_none() is not None:
                skipped += 1
                continue

            try:
                await self._repo.create(
                    symbol=symbol, timestamp=ts, resolution=resolution,
                    open=float(row["open"]), high=float(row["high"]),
                    low=float(row["low"]), close=float(row["close"]),
                    volume=int(row["volume"]),
                )
                created += 1
            except Exception as exc:
                errors.append({"row": i, "errors": [str(exc)], "data": row})

        return {"total": len(records), "created": created, "skipped_duplicates": skipped, "errors": errors}

    async def aggregate_resolution(
        self, symbol: str, source_resolution: str, target_resolution: str,
        start: datetime | None = None, end: datetime | None = None,
    ) -> int:
        symbol = symbol.upper()
        source_minutes: int = RESOLUTION_MINUTES.get(source_resolution, 1)
        target_minutes: int = RESOLUTION_MINUTES.get(target_resolution, 60)
        bars_per_group: int = target_minutes // source_minutes

        if bars_per_group < 1:
            raise ValueError(f"Cannot aggregate {source_resolution} to {target_resolution}")

        stmt = select(IntradayPrice).where(
            IntradayPrice.symbol == symbol,
            IntradayPrice.resolution == source_resolution,
        )
        if start:
            stmt = stmt.where(IntradayPrice.timestamp >= start)
        if end:
            stmt = stmt.where(IntradayPrice.timestamp <= end)
        stmt = stmt.order_by(IntradayPrice.timestamp.asc())
        result = await self._session.execute(stmt)
        source_bars: list[IntradayPrice] = list(result.scalars().all())

        if not source_bars:
            return 0

        await self._session.execute(
            delete(IntradayPrice).where(
                IntradayPrice.symbol == symbol,
                IntradayPrice.resolution == target_resolution,
            )
        )
        if start:
            await self._session.execute(
                delete(IntradayPrice).where(
                    IntradayPrice.symbol == symbol,
                    IntradayPrice.resolution == target_resolution,
                    IntradayPrice.timestamp >= start,
                )
            )
        if end:
            await self._session.execute(
                delete(IntradayPrice).where(
                    IntradayPrice.symbol == symbol,
                    IntradayPrice.resolution == target_resolution,
                    IntradayPrice.timestamp <= end,
                )
            )

        created: int = 0
        for i in range(0, len(source_bars), bars_per_group):
            group = source_bars[i:i + bars_per_group]
            if len(group) < bars_per_group:
                continue
            first_ts: datetime = _round_timestamp(group[0].timestamp, target_resolution)
            agg = IntradayPrice(
                symbol=symbol, timestamp=first_ts, resolution=target_resolution,
                open=group[0].open,
                high=max(b.high for b in group),
                low=min(b.low for b in group),
                close=group[-1].close,
                volume=sum(b.volume for b in group),
            )
            self._session.add(agg)
            created += 1

        await self._session.flush()
        logger.info("aggregation_complete", symbol=symbol, source=source_resolution, target=target_resolution, bars=created)
        return created

    async def aggregate_to_daily(
        self, symbol: str, trade_date: date | None = None,
    ) -> int:
        symbol = symbol.upper()
        stmt = select(IntradayPrice).where(
            IntradayPrice.symbol == symbol,
            IntradayPrice.resolution == "hourly",
        )
        if trade_date:
            day_start = datetime(trade_date.year, trade_date.month, trade_date.day, tzinfo=timezone.utc)
            day_end = day_start + timedelta(days=1)
            stmt = stmt.where(IntradayPrice.timestamp >= day_start, IntradayPrice.timestamp < day_end)
        stmt = stmt.order_by(IntradayPrice.timestamp.asc())
        result = await self._session.execute(stmt)
        hourly_bars: list[IntradayPrice] = list(result.scalars().all())

        if not hourly_bars:
            return 0

        if trade_date is None:
            trade_date = hourly_bars[0].timestamp.date()

        existing = await self._session.execute(
            select(DailyPrice).where(
                DailyPrice.symbol == symbol, DailyPrice.trade_date == trade_date,
            )
        )
        if existing.scalar_one_or_none() is None:
            dp = DailyPrice(
                symbol=symbol, trade_date=trade_date,
                open=hourly_bars[0].open,
                high=max(b.high for b in hourly_bars),
                low=min(b.low for b in hourly_bars),
                close=hourly_bars[-1].close,
                volume=sum(b.volume for b in hourly_bars),
            )
            self._session.add(dp)
            await self._session.flush()
            logger.info("daily_aggregation_complete", symbol=symbol, date=trade_date)
            return 1

        logger.info("daily_aggregation_skipped", symbol=symbol, date=trade_date, reason="already exists")
        return 0

    async def delete_bars(self, symbol: str, resolution: str | None = None) -> int:
        symbol = symbol.upper()
        stmt = delete(IntradayPrice).where(IntradayPrice.symbol == symbol)
        if resolution:
            stmt = stmt.where(IntradayPrice.resolution == resolution)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount
