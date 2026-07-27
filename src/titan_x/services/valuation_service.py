import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.company import Company
from titan_x.models.price import DailyPrice
from titan_x.models.valuation import DCFValuation, RelativeValuation, SectorValuation, ValuationReport


class ValuationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ============================================================
    # DCF VALUATION
    # ============================================================

    async def compute_dcf(
        self,
        symbol: str,
        free_cash_flow: float | None = None,
        growth_rate_5y: float | None = None,
        terminal_growth_rate: float = 0.025,
        wacc: float | None = None,
        projection_years: int = 5,
        shares_outstanding: float | None = None,
        net_debt: float | None = None,
        cash_and_equivalents: float | None = None,
        current_price: float | None = None,
    ) -> DCFValuation:
        symbol = symbol.upper()

        if current_price is None:
            price_result = await self.session.execute(
                select(DailyPrice).where(DailyPrice.symbol == symbol)
                .order_by(DailyPrice.trade_date.desc()).limit(1)
            )
            latest = price_result.scalar_one_or_none()
            current_price = latest.close if latest else None

        if wacc is None:
            wacc = 0.10
        if growth_rate_5y is None:
            growth_rate_5y = 0.10
        if free_cash_flow is None:
            free_cash_flow = 0

        pv_fcf_total = 0.0
        projected_fcf = free_cash_flow
        for yr in range(1, projection_years + 1):
            projected_fcf *= (1 + growth_rate_5y)
            pv_fcf_total += projected_fcf / ((1 + wacc) ** yr)

        terminal_fcf = projected_fcf * (1 + terminal_growth_rate)
        terminal_value = terminal_fcf / (wacc - terminal_growth_rate) if wacc > terminal_growth_rate else 0
        pv_tv = terminal_value / ((1 + wacc) ** projection_years)

        enterprise_value = pv_fcf_total + pv_tv
        equity_value = enterprise_value - (net_debt or 0) + (cash_and_equivalents or 0)
        intrinsic_value = equity_value / shares_outstanding if shares_outstanding and shares_outstanding > 0 else 0
        upside = round((intrinsic_value - current_price) / current_price * 100, 2) if current_price and current_price > 0 else None

        dcf = DCFValuation(
            symbol=symbol,
            valuation_date=datetime.now(timezone.utc),
            current_price=current_price,
            free_cash_flow=free_cash_flow,
            growth_rate_5y=growth_rate_5y,
            terminal_growth_rate=terminal_growth_rate,
            wacc=wacc,
            projection_years=projection_years,
            shares_outstanding=shares_outstanding,
            net_debt=net_debt,
            cash_and_equivalents=cash_and_equivalents,
            present_value_fcf=round(pv_fcf_total, 2),
            terminal_value=round(terminal_value, 2),
            present_value_tv=round(pv_tv, 2),
            enterprise_value=round(enterprise_value, 2),
            equity_value=round(equity_value, 2),
            intrinsic_value=round(intrinsic_value, 2),
            upside_pct=upside,
        )
        self.session.add(dcf)
        await self.session.flush()
        await self.session.refresh(dcf)
        return dcf

    async def get_dcf(self, symbol: str) -> DCFValuation | None:
        result = await self.session.execute(
            select(DCFValuation).where(DCFValuation.symbol == symbol.upper())
            .order_by(DCFValuation.valuation_date.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    # ============================================================
    # RELATIVE VALUATION
    # ============================================================

    async def compute_relative(
        self,
        symbol: str,
        eps: float | None = None,
        book_value_per_share: float | None = None,
        revenue_per_share: float | None = None,
        ebitda: float | None = None,
        current_price: float | None = None,
        industry_avg_pe: float | None = None,
        industry_avg_pb: float | None = None,
        industry_avg_ps: float | None = None,
        industry_avg_ev_ebitda: float | None = None,
    ) -> RelativeValuation:
        symbol = symbol.upper()

        if current_price is None:
            price_result = await self.session.execute(
                select(DailyPrice).where(DailyPrice.symbol == symbol)
                .order_by(DailyPrice.trade_date.desc()).limit(1)
            )
            latest = price_result.scalar_one_or_none()
            current_price = latest.close if latest else None

        pe = round(current_price / eps, 2) if current_price and eps else None
        pb = round(current_price / book_value_per_share, 2) if current_price and book_value_per_share else None
        ps = round(current_price / revenue_per_share, 2) if current_price and revenue_per_share else None
        ev_ebitda = None

        pe_fv = round(eps * (industry_avg_pe or 0), 2) if eps and industry_avg_pe else None
        pb_fv = round(book_value_per_share * (industry_avg_pb or 0), 2) if book_value_per_share and industry_avg_pb else None
        ps_fv = round(revenue_per_share * (industry_avg_ps or 0), 2) if revenue_per_share and industry_avg_ps else None
        ev_fv = None

        fvs = [v for v in [pe_fv, pb_fv, ps_fv] if v is not None]
        composite = round(sum(fvs) / len(fvs), 2) if fvs else None
        upside = round((composite - current_price) / current_price * 100, 2) if composite and current_price else None

        rv = RelativeValuation(
            symbol=symbol,
            valuation_date=datetime.now(timezone.utc),
            current_price=current_price,
            eps=eps, book_value_per_share=book_value_per_share,
            revenue_per_share=revenue_per_share, ebitda=ebitda,
            pe_ratio=pe, pb_ratio=pb, ps_ratio=ps, ev_ebitda=ev_ebitda,
            industry_avg_pe=industry_avg_pe, industry_avg_pb=industry_avg_pb,
            industry_avg_ps=industry_avg_ps, industry_avg_ev_ebitda=industry_avg_ev_ebitda,
            pe_fair_value=pe_fv, pb_fair_value=pb_fv, ps_fair_value=ps_fv,
            ev_ebitda_fair_value=ev_fv,
            composite_fair_value=composite, upside_pct=upside,
        )
        self.session.add(rv)
        await self.session.flush()
        await self.session.refresh(rv)
        return rv

    async def get_relative(self, symbol: str) -> RelativeValuation | None:
        result = await self.session.execute(
            select(RelativeValuation).where(RelativeValuation.symbol == symbol.upper())
            .order_by(RelativeValuation.valuation_date.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    # ============================================================
    # SECTOR VALUATION
    # ============================================================

    async def compute_sector(
        self,
        symbol: str,
        sector_pe_data: list[dict] | None = None,
    ) -> SectorValuation:
        symbol = symbol.upper()
        company_result = await self.session.execute(
            select(Company).where(Company.symbol == symbol)
        )
        company = company_result.scalar_one_or_none()
        sector = company.sector if company else None

        peer_values = sector_pe_data or []

        if not peer_values and sector:
            peers_result = await self.session.execute(
                select(Company).where(Company.sector == sector, Company.symbol != symbol)
            )
            peers = peers_result.scalars().all()
            for p in peers:
                rv = await self.get_relative(p.symbol)
                if rv and rv.pe_ratio:
                    peer_values.append({"symbol": p.symbol, "pe": rv.pe_ratio, "pb": rv.pb_ratio, "ps": rv.ps_ratio})

        peer_count = len(peer_values)
        pe_list = [p.get("pe") for p in peer_values if p.get("pe")]
        pb_list = [p.get("pb") for p in peer_values if p.get("pb")]
        ps_list = [p.get("ps") for p in peer_values if p.get("ps")]

        avg_pe = sum(pe_list) / len(pe_list) if pe_list else None
        med_pe = sorted(pe_list)[len(pe_list) // 2] if pe_list else None
        avg_pb = sum(pb_list) / len(pb_list) if pb_list else None
        avg_ps = sum(ps_list) / len(ps_list) if ps_list else None

        my_rv = await self.get_relative(symbol)
        my_pe = my_rv.pe_ratio if my_rv else None
        pe_pctl = None
        pb_pctl = None
        if my_pe and pe_list:
            below = sum(1 for v in pe_list if v <= my_pe)
            pe_pctl = round(below / len(pe_list) * 100, 1)
        if my_rv and my_rv.pb_ratio and pb_list:
            below = sum(1 for v in pb_list if v <= my_rv.pb_ratio)
            pb_pctl = round(below / len(pb_list) * 100, 1)

        current_price = my_rv.current_price if my_rv else None
        sector_fv = None
        if avg_pe and my_rv and my_rv.pe_ratio and current_price:
            pe_discount = avg_pe / my_rv.pe_ratio if my_rv.pe_ratio > 0 else 1
            sector_fv = round(current_price * pe_discount, 2)

        upside = round((sector_fv - current_price) / current_price * 100, 2) if sector_fv and current_price else None
        grade = "Undervalued" if pe_pctl and pe_pctl < 33 else "Overvalued" if pe_pctl and pe_pctl > 66 else "Fair"

        sv = SectorValuation(
            symbol=symbol,
            valuation_date=datetime.now(timezone.utc),
            sector=sector,
            peer_count=peer_count,
            peer_avg_pe=avg_pe, peer_median_pe=med_pe,
            peer_avg_pb=avg_pb, peer_avg_ps=avg_ps,
            pe_percentile=pe_pctl, pb_percentile=pb_pctl,
            sector_grade=grade,
            sector_fair_value=sector_fv, upside_pct=upside,
        )
        self.session.add(sv)
        await self.session.flush()
        await self.session.refresh(sv)
        return sv

    async def get_sector(self, symbol: str) -> SectorValuation | None:
        result = await self.session.execute(
            select(SectorValuation).where(SectorValuation.symbol == symbol.upper())
            .order_by(SectorValuation.valuation_date.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    # ============================================================
    # VALUATION REPORT
    # ============================================================

    async def generate_report(self, symbol: str) -> ValuationReport:
        symbol = symbol.upper()

        dcf = await self.get_dcf(symbol) or await self.compute_dcf(symbol)
        rel = await self.get_relative(symbol) or await self.compute_relative(symbol)
        sec = await self.get_sector(symbol) or await self.compute_sector(symbol)

        current_price = dcf.current_price or rel.current_price or 0

        dcf_fv = dcf.intrinsic_value
        rel_fv = rel.composite_fair_value
        sec_fv = sec.sector_fair_value

        fvs = [v for v in [dcf_fv, rel_fv, sec_fv] if v is not None and v > 0]
        composite = round(sum(fvs) / len(fvs), 2) if fvs else None

        margin = round((composite - current_price) / composite * 100, 2) if composite and composite > 0 else None
        dcf_upside = round((dcf_fv - current_price) / current_price * 100, 2) if dcf_fv and current_price else None
        rel_upside = rel.upside_pct
        sec_upside = sec.upside_pct

        if margin and margin >= 30:
            rec = "strong_buy"
        elif margin and margin >= 15:
            rec = "buy"
        elif margin and margin >= 0:
            rec = "hold"
        elif margin and margin >= -15:
            rec = "sell"
        else:
            rec = "strong_sell"

        report_data = {
            "symbol": symbol,
            "current_price": current_price,
            "dcf": {
                "intrinsic_value": dcf_fv,
                "upside_pct": dcf_upside,
                "wacc": dcf.wacc,
                "growth_rate_5y": dcf.growth_rate_5y,
                "terminal_growth": dcf.terminal_growth_rate,
                "free_cash_flow": dcf.free_cash_flow,
                "enterprise_value": dcf.enterprise_value,
                "equity_value": dcf.equity_value,
            },
            "relative": {
                "composite_fair_value": rel_fv,
                "pe_ratio": rel.pe_ratio,
                "pb_ratio": rel.pb_ratio,
                "ps_ratio": rel.ps_ratio,
                "pe_fair_value": rel.pe_fair_value,
                "pb_fair_value": rel.pb_fair_value,
                "ps_fair_value": rel.ps_fair_value,
            },
            "sector": {
                "sector_fair_value": sec_fv,
                "sector": sec.sector,
                "peer_count": sec.peer_count,
                "avg_pe": sec.peer_avg_pe,
                "pe_percentile": sec.pe_percentile,
                "grade": sec.sector_grade,
            },
            "composite_fair_value": composite,
            "margin_of_safety_pct": margin,
            "recommendation": rec,
        }

        vr = ValuationReport(
            symbol=symbol,
            report_date=datetime.now(timezone.utc),
            current_price=current_price,
            dcf_fair_value=dcf_fv,
            relative_fair_value=rel_fv,
            sector_fair_value=sec_fv,
            composite_fair_value=composite,
            margin_of_safety_pct=margin,
            dcf_upside=dcf_upside,
            relative_upside=rel_upside,
            sector_upside=sec_upside,
            recommendation=rec,
            report_json=json.dumps(report_data, default=str),
        )
        self.session.add(vr)
        await self.session.flush()
        await self.session.refresh(vr)
        return vr

    async def get_report(self, symbol: str) -> ValuationReport | None:
        result = await self.session.execute(
            select(ValuationReport).where(ValuationReport.symbol == symbol.upper())
            .order_by(ValuationReport.report_date.desc()).limit(1)
        )
        return result.scalar_one_or_none()
