"""Point-in-time data policy for the existing prediction engine.

This is deliberately a thin policy layer over ``PredictionEngine``. It does
not introduce another prediction algorithm; it prevents the existing engine
from accidentally reading data that was not available at the requested
``as_of_date``.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.fundamental import FundamentalMetric
from titan_x.models.historical_similarity import SimilarityAnalysis
from titan_x.models.price import DailyPrice
from titan_x.services.prediction_engine import PredictionEngine


class PointInTimePredictionEngine(PredictionEngine):
    """Existing prediction engine with leakage-safe historical data access."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._prediction_as_of_date: date | None = None

    @staticmethod
    def _as_of_datetime(as_of_date: date) -> datetime:
        return datetime.combine(as_of_date, time.max, tzinfo=timezone.utc)

    def _cutoff(self, as_of_date: date | None) -> date | None:
        return as_of_date if as_of_date is not None else self._prediction_as_of_date

    async def _get_similarities(
        self, symbol: str, as_of_date: date | None = None
    ) -> list[SimilarityAnalysis]:
        """Use the newest similarity analysis whose query ended by the cutoff."""
        cutoff = self._cutoff(as_of_date)
        query = (
            select(SimilarityAnalysis)
            .where(SimilarityAnalysis.symbol == symbol.upper())
            .order_by(desc(SimilarityAnalysis.query_end_date), desc(SimilarityAnalysis.created_at))
            .limit(1)
        )
        if cutoff is not None:
            query = query.where(SimilarityAnalysis.query_end_date <= cutoff)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def _get_latest_price(
        self, symbol: str, as_of_date: date | None = None
    ) -> DailyPrice | None:
        """Never use a price after the prediction cutoff date."""
        cutoff = self._cutoff(as_of_date)
        query = (
            select(DailyPrice)
            .where(DailyPrice.symbol == symbol.upper())
            .order_by(desc(DailyPrice.trade_date))
            .limit(1)
        )
        if cutoff is not None:
            query = query.where(DailyPrice.trade_date <= cutoff)
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def _get_fundamentals(
        self, symbol: str, as_of_date: date | None = None
    ) -> list[FundamentalMetric]:
        """Use only filings published on or before the requested cutoff."""
        cutoff = self._cutoff(as_of_date)
        query = (
            select(FundamentalMetric)
            .where(
                FundamentalMetric.symbol == symbol.upper(),
                FundamentalMetric.period_type == "annual",
                FundamentalMetric.metric_name.in_(["PE_RATIO", "QUALITY_SCORE", "ROE"]),
            )
            .order_by(desc(FundamentalMetric.fiscal_year), desc(FundamentalMetric.published_at))
            .limit(10)
        )
        if cutoff is not None:
            query = query.where(
                FundamentalMetric.published_at <= self._as_of_datetime(cutoff)
            )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def predict(
        self, symbol: str, as_of_date: date | None = None, store: bool = True
    ) -> dict:
        """Run the existing engine with point-in-time-safe inputs."""
        if as_of_date is None:
            as_of_date = date.today()
        previous_cutoff = self._prediction_as_of_date
        self._prediction_as_of_date = as_of_date
        try:
            return await super().predict(symbol, as_of_date, store=store)
        finally:
            self._prediction_as_of_date = previous_cutoff
