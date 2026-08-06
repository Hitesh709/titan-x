"""Financial features (EPS, PE, market cap, growth, margins)."""
from datetime import date

from sqlalchemy import select

from titan_x.models.company import Company
from titan_x.models.financial_analysis import AnnualResult, QuarterlyResult
from titan_x.models.price import DailyPrice


class FinancialFeaturesMixin:
    async def _compute_financial_features(self, symbol: str, as_of_date: date) -> int:
        count = 0

        # Get latest quarter / annual EPS
        qr = await self.session.execute(
            select(QuarterlyResult)
            .where(QuarterlyResult.symbol == symbol)
            .order_by(QuarterlyResult.fiscal_year.desc(), QuarterlyResult.quarter.desc())
            .limit(1)
        )
        latest_q = qr.scalar_one_or_none()

        ar = await self.session.execute(
            select(AnnualResult)
            .where(AnnualResult.symbol == symbol)
            .order_by(AnnualResult.fiscal_year.desc())
            .limit(1)
        )
        latest_a = ar.scalar_one_or_none()

        # Get latest close price
        price_r = await self.session.execute(
            select(DailyPrice)
            .where(DailyPrice.symbol == symbol, DailyPrice.trade_date <= as_of_date)
            .order_by(DailyPrice.trade_date.desc())
            .limit(1)
        )
        latest_price = price_r.scalar_one_or_none()
        current_price = latest_price.close if latest_price else None

        # Get company for market cap
        comp_r = await self.session.execute(
            select(Company).where(Company.symbol == symbol)
        )
        company = comp_r.scalar_one_or_none()

        # eps_diluted
        eps = None
        if latest_q and latest_q.eps_diluted is not None:
            eps = latest_q.eps_diluted
        elif latest_a and latest_a.eps_diluted is not None:
            eps = latest_a.eps_diluted
        if eps is not None:
            fd = await self._get_or_create_definition(
                "eps_diluted", "financial",
                description="Latest diluted earnings per share",
                formula="from QuarterlyResult or AnnualResult", source="quarterly_result,annual_result",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(eps, 4),
                                     {"fiscal_year": latest_q.fiscal_year if latest_q else latest_a.fiscal_year,
                                      "quarter": latest_q.quarter if latest_q else None})
            count += 1

        # pe_ratio
        if current_price and eps and eps > 0:
            pe = current_price / eps
            fd = await self._get_or_create_definition(
                "pe_ratio", "financial",
                description="Price-to-Earnings ratio",
                formula="close / eps_diluted", source="daily_price,quarterly_result",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(pe, 4),
                                     {"price": current_price, "eps": eps})
            count += 1

        # market_cap_crore
        if company and company.market_cap:
            mc_cr = company.market_cap / 1e7
            fd = await self._get_or_create_definition(
                "market_cap_crore", "financial",
                description="Market capitalization in crores",
                formula="market_cap / 1e7", source="company",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(mc_cr, 2))
            count += 1

        # revenue_growth_yoy (from quarterly result)
        if latest_q and latest_q.revenue_yoy_growth is not None:
            fd = await self._get_or_create_definition(
                "revenue_growth_yoy", "financial",
                description="Year-over-year revenue growth",
                formula="from QuarterlyResult", source="quarterly_result",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(latest_q.revenue_yoy_growth, 4),
                                     {"fiscal_year": latest_q.fiscal_year, "quarter": latest_q.quarter})
            count += 1

        # eps_growth_yoy
        if latest_q and latest_q.eps_yoy_growth is not None:
            fd = await self._get_or_create_definition(
                "eps_growth_yoy", "financial",
                description="Year-over-year EPS growth",
                formula="from QuarterlyResult", source="quarterly_result",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(latest_q.eps_yoy_growth, 4))
            count += 1

        # net_margin
        if latest_q and latest_q.net_margin is not None:
            fd = await self._get_or_create_definition(
                "net_margin", "financial",
                description="Net profit margin",
                formula="from QuarterlyResult", source="quarterly_result",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(latest_q.net_margin, 4))
            count += 1

        return count