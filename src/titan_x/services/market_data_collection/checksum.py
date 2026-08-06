"""Checksum computation and verification for stored market data."""
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.market_data_collector import DataChecksum
from titan_x.models.price import DailyPrice

logger = structlog.get_logger(__name__)


class ChecksumService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self._log = logger.bind(service="checksum")

    async def compute(
        self, symbol: str, trade_date: date, data_type: str = "daily_price"
    ) -> DataChecksum:
        stmt = select(DailyPrice).where(
            DailyPrice.symbol == symbol, DailyPrice.trade_date == trade_date
        )
        r = await self.session.execute(stmt)
        rows = r.scalars().all()

        raw = json.dumps(
            [{"o": p.open, "h": p.high, "l": p.low, "c": p.close, "v": p.volume} for p in rows],
            sort_keys=True, default=str,
        )
        sha = hashlib.sha256(raw.encode()).hexdigest()

        existing = await self.session.execute(
            select(DataChecksum).where(
                DataChecksum.symbol == symbol,
                DataChecksum.trade_date == trade_date,
                DataChecksum.data_type == data_type,
            )
        )
        chk = existing.scalar_one_or_none()
        if chk:
            chk.checksum_sha256 = sha
            chk.row_count = len(rows)
            chk.verified_at = None
            chk.is_verified = False
        else:
            chk = DataChecksum(
                symbol=symbol,
                trade_date=trade_date,
                data_type=data_type,
                checksum_sha256=sha,
                row_count=len(rows),
            )
            self.session.add(chk)
        await self.session.flush()
        await self.session.refresh(chk)
        return chk

    async def verify(
        self, symbol: str, trade_date: date, data_type: str = "daily_price"
    ) -> bool:
        stmt = select(DataChecksum).where(
            DataChecksum.symbol == symbol,
            DataChecksum.trade_date == trade_date,
            DataChecksum.data_type == data_type,
        ).order_by(DataChecksum.created_at.desc()).limit(1)
        r = await self.session.execute(stmt)
        stored = r.scalar_one_or_none()
        if not stored:
            return False

        fresh = await self.compute(symbol, trade_date, data_type)
        matches = fresh.checksum_sha256 == stored.checksum_sha256

        stored.is_verified = matches
        stored.verified_at = datetime.now(timezone.utc)
        await self.session.flush()

        if not matches:
            self._log.warning("checksum_mismatch", symbol=symbol, trade_date=trade_date.isoformat())
        return matches

    async def verify_batch(
        self, symbol: str, start: date, end: date, data_type: str = "daily_price"
    ) -> dict[str, Any]:
        results = {"verified": 0, "mismatched": 0, "missing": 0, "total": 0}
        current = start
        while current <= end:
            if current.weekday() < 5:
                results["total"] += 1
                ok = await self.verify(symbol, current, data_type)
                if ok:
                    results["verified"] += 1
                else:
                    stmt = select(DataChecksum).where(
                        DataChecksum.symbol == symbol,
                        DataChecksum.trade_date == current,
                        DataChecksum.data_type == data_type,
                    )
                    r = await self.session.execute(stmt)
                    exists = r.scalar_one_or_none()
                    if exists:
                        results["mismatched"] += 1
                    else:
                        results["missing"] += 1
            current += timedelta(days=1)
        return results