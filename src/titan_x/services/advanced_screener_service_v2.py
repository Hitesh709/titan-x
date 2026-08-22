from datetime import date
from typing import Any

from sqlalchemy import desc, select

from titan_x.models.company import Company
from titan_x.models.technical import TechnicalIndicator
from titan_x.services.advanced_screener_service import AdvancedScreenerService


class ProductionScreenerService(AdvancedScreenerService):
    """Production screener extensions used by the TITAN X UI.

    Keeps the existing screener implementation intact while correcting SMA
    crossover semantics. A golden/death cross is an actual crossing event,
    not merely the current ordering of two moving averages.
    """

    async def _filter_technical(self, tech: dict[str, Any]) -> set[str]:
        sma_cross = tech.get("sma_cross")
        if not sma_cross:
            return await super()._filter_technical(tech)

        other_filters = dict(tech)
        other_filters.pop("sma_cross", None)
        if other_filters:
            base_set = await super()._filter_technical(other_filters)
        else:
            base_set = await self._get_all_active_symbol_set()

        cross_set = await self._filter_true_sma_cross(
            sma_cross, tech.get("as_of_date")
        )
        return base_set & cross_set

    async def _get_all_active_symbol_set(self) -> set[str]:
        rows = await self._session.execute(
            select(Company.symbol).where(Company.status == "active")
        )
        return {row[0] for row in rows.all()}

    async def _filter_true_sma_cross(
        self,
        sma_cross: dict[str, Any],
        as_of_date: date | None,
    ) -> set[str]:
        as_of = as_of_date or date.today()
        fast_period = int(sma_cross.get("fast", 20))
        slow_period = int(sma_cross.get("slow", 50))
        cross_type = str(sma_cross.get("type", "golden")).lower()

        if fast_period <= 0 or slow_period <= 0 or fast_period == slow_period:
            return set()
        if cross_type not in {"golden", "death"}:
            return set()

        rows = await self._session.execute(
            select(
                TechnicalIndicator.symbol,
                TechnicalIndicator.period,
                TechnicalIndicator.value,
                TechnicalIndicator.trade_date,
            )
            .where(
                TechnicalIndicator.indicator == "sma",
                TechnicalIndicator.period.in_([fast_period, slow_period]),
                TechnicalIndicator.trade_date <= as_of,
                TechnicalIndicator.value.isnot(None),
            )
            .order_by(
                TechnicalIndicator.symbol,
                TechnicalIndicator.period,
                desc(TechnicalIndicator.trade_date),
            )
        )

        observations: dict[str, dict[int, list[tuple[date, float]]]] = {}
        for symbol, period, value, trade_date in rows.all():
            by_period = observations.setdefault(symbol, {})
            values = by_period.setdefault(int(period), [])
            if len(values) < 2:
                values.append((trade_date, float(value)))

        matches: set[str] = set()
        for symbol, by_period in observations.items():
            fast_values = by_period.get(fast_period, [])
            slow_values = by_period.get(slow_period, [])
            if len(fast_values) < 2 or len(slow_values) < 2:
                continue

            latest_fast_date, latest_fast = fast_values[0]
            previous_fast_date, previous_fast = fast_values[1]
            latest_slow_date, latest_slow = slow_values[0]
            previous_slow_date, previous_slow = slow_values[1]

            # A crossover must compare the two SMAs on the same trading dates.
            if latest_fast_date != latest_slow_date or previous_fast_date != previous_slow_date:
                continue

            if cross_type == "golden":
                crossed = previous_fast <= previous_slow and latest_fast > latest_slow
            else:
                crossed = previous_fast >= previous_slow and latest_fast < latest_slow

            if crossed:
                matches.add(symbol)

        return matches
