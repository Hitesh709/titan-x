"""Market breadth features (A/D ratio, new highs/lows, oscillator, A/D line)."""
from datetime import date

from sqlalchemy import select

from titan_x.models.market_breadth import MarketBreadth


class BreadthFeaturesMixin:
    async def _compute_breadth_features(self, symbol: str, as_of_date: date) -> int:
        count = 0

        r = await self.session.execute(
            select(MarketBreadth)
            .where(MarketBreadth.trade_date <= as_of_date)
            .order_by(MarketBreadth.trade_date.desc())
            .limit(20)
        )
        breadths = list(reversed(r.scalars().all()))

        if not breadths:
            return count

        latest = breadths[-1]

        # advance_decline_ratio
        if latest.declining and latest.declining > 0:
            ad_ratio = latest.advancing / latest.declining
            fd = await self._get_or_create_definition(
                "advance_decline_ratio", "breadth",
                description="Advance/Decline ratio",
                formula="advancing / declining", source="market_breadth",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(ad_ratio, 4),
                                     {"advancing": latest.advancing, "declining": latest.declining})
            count += 1

        # new_highs_lows_ratio
        if latest.new_lows and latest.new_lows > 0:
            nhl_ratio = latest.new_highs / latest.new_lows
            fd = await self._get_or_create_definition(
                "new_highs_lows_ratio", "breadth",
                description="New Highs / New Lows ratio",
                formula="new_highs / new_lows", source="market_breadth",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(nhl_ratio, 4),
                                     {"new_highs": latest.new_highs, "new_lows": latest.new_lows})
            count += 1
        elif latest.new_lows == 0 and latest.new_highs > 0:
            fd = await self._get_or_create_definition(
                "new_highs_lows_ratio", "breadth",
                description="New Highs / New Lows ratio",
                formula="new_highs / new_lows", source="market_breadth",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, latest.new_highs * 100.0,
                                     {"new_highs": latest.new_highs, "new_lows": 0, "note": "no new_lows"})
            count += 1

        # breadth_oscillator
        if latest.breadth_oscillator is not None:
            fd = await self._get_or_create_definition(
                "breadth_oscillator", "breadth",
                description="Market breadth oscillator value",
                formula="from MarketBreadth", source="market_breadth",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(latest.breadth_oscillator, 4))
            count += 1

        # advance_decline_line (cumulative A/D)
        ad_line = 0
        for b in breadths:
            ad_line += (b.advancing - b.declining)
        fd = await self._get_or_create_definition(
            "advance_decline_line", "breadth",
            description="Cumulative Advance-Decline line (20-day)",
            formula="sum(advancing - declining)", source="market_breadth",
        )
        await self._upsert_value(fd.id, symbol, as_of_date, ad_line, {"period_days": 20})
        count += 1

        # breadth_momentum: change in A/D ratio over 5 days
        if len(breadths) >= 6:
            recent_ad = self._safe_div(breadths[-1].advancing, max(breadths[-1].declining, 1))
            prev_ad = self._safe_div(breadths[-6].advancing, max(breadths[-6].declining, 1))
            if recent_ad is not None and prev_ad is not None and prev_ad != 0:
                bm = self._safe_div(recent_ad - prev_ad, prev_ad)
                if bm is not None:
                    fd = await self._get_or_create_definition(
                        "breadth_momentum_5d", "breadth",
                        description="5-day change in Advance/Decline ratio",
                        formula="(ad_ratio[t] - ad_ratio[t-5]) / ad_ratio[t-5]",
                        source="market_breadth",
                    )
                    await self._upsert_value(fd.id, symbol, as_of_date, round(bm * 100, 4))
                    count += 1

        return count