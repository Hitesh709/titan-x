import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.chart_pattern import SupportResistance
from titan_x.models.company import Company
from titan_x.models.company_research import CompanyResearch
from titan_x.models.corporate_tracking import ShareholdingPattern
from titan_x.models.financial import FinancialLineItem, FinancialStatement
from titan_x.models.fundamental import FundamentalMetric
from titan_x.models.knowledge_graph import CompanyPromoter, EntityEvent, Promoter, Subsidiary
from titan_x.models.microstructure import MarketMicrostructure
from titan_x.models.news import NewsArticle
from titan_x.models.news_nlp import NewsNLPAnalysis
from titan_x.models.price import DailyPrice
from titan_x.models.regime import MarketRegime
from titan_x.models.risk import RiskMetrics
from titan_x.models.sector import SectorPerformance
from titan_x.models.technical import TechnicalIndicator


class CompanyResearchService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def generate(self, symbol: str) -> CompanyResearch:
        symbol = symbol.upper()
        today = date.today()

        business = await self._build_business(symbol)
        financials = await self._build_financials(symbol)
        risks = await self._build_risks(symbol, today)
        growth = await self._build_growth(symbol)
        competition = await self._build_competition(symbol)
        ai_summary = await self._build_ai_summary(
            symbol, business, financials, risks, growth, competition,
        )

        html = self._build_html(
            symbol, today, business, financials, risks, growth, competition, ai_summary,
        )

        record = CompanyResearch(
            symbol=symbol,
            as_of_date=today,
            business_json=json.dumps(business),
            financials_json=json.dumps(financials),
            risks_json=json.dumps(risks),
            growth_json=json.dumps(growth),
            competition_json=json.dumps(competition),
            ai_summary=ai_summary,
            html_content=html,
        )
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def get_research(self, research_id: int) -> CompanyResearch | None:
        r = await self.session.execute(
            select(CompanyResearch).where(CompanyResearch.id == research_id)
        )
        return r.scalar_one_or_none()

    async def get_research_by_symbol(self, symbol: str) -> CompanyResearch | None:
        r = await self.session.execute(
            select(CompanyResearch).where(CompanyResearch.symbol == symbol.upper())
            .order_by(desc(CompanyResearch.as_of_date)).limit(1)
        )
        return r.scalar_one_or_none()

    async def list_research(self, symbol: str, limit: int = 10, offset: int = 0) -> list[CompanyResearch]:
        r = await self.session.execute(
            select(CompanyResearch).where(CompanyResearch.symbol == symbol.upper())
            .order_by(desc(CompanyResearch.as_of_date))
            .offset(offset).limit(limit)
        )
        return list(r.scalars().all())

    # ---- section builders ----

    async def _build_business(self, symbol: str) -> dict[str, Any]:
        company = await self.session.execute(
            select(Company).where(Company.symbol == symbol).limit(1)
        )
        c = company.scalar_one_or_none()
        if not c:
            return {"available": False}

        # Subsidiaries
        sub = await self.session.execute(
            select(Subsidiary).where(Subsidiary.parent_company_id == c.id, Subsidiary.is_active == True)
        )
        subsidiaries = sub.scalars().all()
        sub_names = []
        for s in subsidiaries:
            sc = await self.session.get(Company, s.subsidiary_company_id)
            if sc:
                sub_names.append({"name": sc.company_name, "symbol": sc.symbol, "ownership_pct": s.ownership_pct})

        # Promoters
        cp = await self.session.execute(
            select(CompanyPromoter).where(CompanyPromoter.company_id == c.id, CompanyPromoter.is_active == True)
        )
        comp_prom = cp.scalars().all()
        promoters = []
        for cp_row in comp_prom:
            p = await self.session.get(Promoter, cp_row.promoter_id)
            if p:
                promoters.append({"name": p.name, "type": p.promoter_type, "ownership_pct": cp_row.ownership_pct, "role": cp_row.role})

        # Recent entity events
        ev = await self.session.execute(
            select(EntityEvent).where(EntityEvent.company_id == c.id)
            .order_by(desc(EntityEvent.event_date)).limit(5)
        )
        events = ev.scalars().all()
        event_list = []
        for e in events:
            event_list.append({
                "event_type": e.event_type,
                "event_date": e.event_date.isoformat(),
                "title": e.title,
                "description": e.description,
                "impact_score": e.impact_score,
            })

        return {
            "available": True,
            "symbol": symbol,
            "company_name": c.company_name,
            "isin": c.isin,
            "sector": c.sector,
            "industry": c.industry,
            "exchange": c.exchange,
            "market_cap": c.market_cap,
            "listing_date": c.listing_date.isoformat() if c.listing_date else None,
            "status": c.status,
            "description": c.description,
            "website": c.website,
            "subsidiaries": sub_names,
            "promoters": promoters,
            "recent_events": event_list,
        }

    async def _build_financials(self, symbol: str) -> dict[str, Any]:
        # Financial statements
        stmt = await self.session.execute(
            select(FinancialStatement).where(
                FinancialStatement.symbol == symbol,
            ).order_by(desc(FinancialStatement.fiscal_year), desc(FinancialStatement.fiscal_period)).limit(3)
        )
        statements = stmt.scalars().all()

        stmt_list = []
        for s in statements:
            items = await self.session.execute(
                select(FinancialLineItem).where(FinancialLineItem.statement_id == s.id)
                .order_by(FinancialLineItem.order)
            )
            line_items = items.scalars().all()
            stmt_list.append({
                "fiscal_year": s.fiscal_year,
                "fiscal_period": s.fiscal_period,
                "period_type": s.period_type,
                "statement_type": s.statement_type,
                "filing_date": s.filing_date.isoformat(),
                "currency": s.currency,
                "line_items": [
                    {"concept": li.concept, "label": li.label, "value": li.value, "unit": li.unit}
                    for li in line_items
                ],
            })

        # Key metrics from FundamentalMetric
        metric_names = ["pe_ratio", "pb_ratio", "debt_to_equity", "current_ratio",
                        "profit_margin", "revenue_growth", "eps_growth", "roe",
                        "roa", "dividend_yield", "market_cap"]

        fund = await self.session.execute(
            select(FundamentalMetric).where(
                FundamentalMetric.symbol == symbol,
                FundamentalMetric.metric_name.in_(metric_names),
            ).order_by(desc(FundamentalMetric.fiscal_year), desc(FundamentalMetric.fiscal_period))
        )
        fm = fund.scalars().all()
        metrics: dict[str, Any] = {}
        for row in fm:
            if row.metric_name not in metrics:
                metrics[row.metric_name] = row.value

        return {
            "available": True,
            "statements": stmt_list,
            "key_metrics": metrics,
        }

    async def _build_risks(self, symbol: str, today: date) -> dict[str, Any]:
        risk = await self.session.execute(
            select(RiskMetrics).where(RiskMetrics.symbol == symbol)
            .order_by(desc(RiskMetrics.as_of_date)).limit(1)
        )
        rm = risk.scalar_one_or_none()

        liq = await self.session.execute(
            select(MarketMicrostructure).where(MarketMicrostructure.symbol == symbol)
            .order_by(desc(MarketMicrostructure.as_of_date)).limit(1)
        )
        liq_row = liq.scalar_one_or_none()

        regime = await self.session.execute(
            select(MarketRegime).where(MarketRegime.symbol == symbol)
            .order_by(desc(MarketRegime.as_of_date)).limit(1)
        )
        reg = regime.scalar_one_or_none()

        risk_dict: dict[str, Any] = {"available": True}
        if rm:
            risk_dict.update({
                "composite_risk_score": rm.composite_risk_score,
                "risk_rating": rm.risk_rating,
                "volatility_20d": rm.volatility_20d,
                "volatility_60d": rm.volatility_60d,
                "max_drawdown_1m": rm.max_drawdown_1m,
                "max_drawdown_3m": rm.max_drawdown_3m,
                "max_drawdown_6m": rm.max_drawdown_6m,
                "event_risk_score": rm.event_risk_score,
                "news_count_30d": rm.news_count_30d,
                "gap_frequency_20d": rm.gap_frequency_20d,
            })
        if liq_row:
            risk_dict.update({
                "liquidity_score": liq_row.liquidity_score,
                "liquidity_rating": liq_row.liquidity_rating,
            })
        if reg:
            risk_dict.update({
                "trend_regime": reg.trend_regime,
                "volatility_regime": reg.volatility_regime,
            })
        return risk_dict

    async def _build_growth(self, symbol: str) -> dict[str, Any]:
        # Fundamental metrics over multiple periods
        fund = await self.session.execute(
            select(FundamentalMetric).where(
                FundamentalMetric.symbol == symbol,
                FundamentalMetric.metric_name.in_(["revenue_growth", "eps_growth", "profit_margin", "roe", "roa"]),
            ).order_by(desc(FundamentalMetric.fiscal_year), desc(FundamentalMetric.fiscal_period))
        )
        rows = fund.scalars().all()

        growth_metrics: dict[str, list[dict]] = {}
        for row in rows:
            name = row.metric_name
            if name not in growth_metrics:
                growth_metrics[name] = []
            growth_metrics[name].append({
                "fiscal_year": row.fiscal_year,
                "fiscal_period": row.fiscal_period,
                "value": row.value,
            })

        # Price performance
        prices = await self.session.execute(
            select(DailyPrice).where(DailyPrice.symbol == symbol)
            .order_by(desc(DailyPrice.trade_date)).limit(252)
        )
        price_list = list(prices.scalars().all())
        price_list.reverse()

        returns: dict[str, float | None] = {}
        if len(price_list) >= 2:
            returns["1d"] = round(
                (price_list[-1].close - price_list[-2].close) / price_list[-2].close * 100, 2,
            )
        if len(price_list) >= 21:
            returns["1m"] = round(
                (price_list[-1].close - price_list[-21].close) / price_list[-21].close * 100, 2,
            )
        if len(price_list) >= 63:
            returns["3m"] = round(
                (price_list[-1].close - price_list[-63].close) / price_list[-63].close * 100, 2,
            )
        if len(price_list) >= 252:
            returns["1y"] = round(
                (price_list[-1].close - price_list[0].close) / price_list[0].close * 100, 2,
            )

        # Sector comparison
        company = await self.session.execute(
            select(Company).where(Company.symbol == symbol).limit(1)
        )
        c = company.scalar_one_or_none()
        sector_data = None
        if c and c.sector:
            sec = await self.session.execute(
                select(SectorPerformance).where(SectorPerformance.sector == c.sector)
                .order_by(desc(SectorPerformance.as_of_date)).limit(1)
            )
            sp = sec.scalar_one_or_none()
            if sp:
                sector_data = {
                    "sector": sp.sector,
                    "return_pct": sp.return_pct,
                    "momentum_score": sp.momentum_score,
                    "relative_strength": sp.relative_strength,
                    "rank": sp.rank,
                }

        return {
            "available": bool(price_list),
            "fundamental_growth": growth_metrics,
            "price_returns": returns,
            "current_price": price_list[-1].close if price_list else None,
            "sector_comparison": sector_data,
        }

    async def _build_competition(self, symbol: str) -> dict[str, Any]:
        company = await self.session.execute(
            select(Company).where(Company.symbol == symbol).limit(1)
        )
        c = company.scalar_one_or_none()
        if not c or not c.sector:
            return {"available": False, "note": "No sector information available for comparison"}

        # Peers in same sector
        peers = await self.session.execute(
            select(Company).where(
                Company.sector == c.sector,
                Company.symbol != symbol,
                Company.status == "active",
            ).order_by(desc(Company.market_cap)).limit(20)
        )
        peer_list = peers.scalars().all()

        # Get metrics for peers
        peer_metrics = []
        for p in peer_list:
            pm = {
                "symbol": p.symbol,
                "company_name": p.company_name,
                "market_cap": p.market_cap,
                "exchange": p.exchange,
            }
            # Fetch PE for peer
            pe = await self.session.execute(
                select(FundamentalMetric).where(
                    FundamentalMetric.symbol == p.symbol,
                    FundamentalMetric.metric_name == "pe_ratio",
                ).order_by(desc(FundamentalMetric.fiscal_year)).limit(1)
            )
            pe_row = pe.scalar_one_or_none()
            if pe_row:
                pm["pe_ratio"] = pe_row.value
            peer_metrics.append(pm)

        return {
            "available": True,
            "sector": c.sector,
            "industry": c.industry,
            "company_market_cap": c.market_cap,
            "peer_count": len(peer_list),
            "peers": peer_metrics,
        }

    async def _build_ai_summary(
        self, symbol: str, business: dict, financials: dict,
        risks: dict, growth: dict, competition: dict,
    ) -> str:
        parts: list[str] = []

        if business.get("available"):
            name = business.get("company_name", symbol)
            sector = business.get("sector", "N/A")
            industry = business.get("industry", "N/A")
            parts.append(f"{name} ({symbol}) operates in the {sector} sector, {industry} industry.")

            desc = business.get("description")
            if desc:
                parts.append(desc[:200])

            if business.get("subsidiaries"):
                parts.append(f"The company has {len(business['subsidiaries'])} active subsidiaries.")

            if business.get("promoters"):
                total_own = sum(p.get("ownership_pct") or 0 for p in business["promoters"])
                parts.append(f"Promoter holding is approximately {total_own:.1f}%.")

        if financials.get("available"):
            metrics = financials.get("key_metrics", {})
            pe = metrics.get("pe_ratio")
            if pe is not None:
                label = "elevated" if pe > 30 else "reasonable" if pe > 15 else "attractive"
                parts.append(f"The P/E ratio of {pe:.1f}x is {label}.")
            de = metrics.get("debt_to_equity")
            if de is not None:
                label = "low" if de < 0.5 else "moderate" if de < 1.5 else "high"
                parts.append(f"Debt-to-equity at {de:.2f}x is {label}.")
            pm = metrics.get("profit_margin")
            if pm is not None:
                parts.append(f"Profit margin is {pm*100:.1f}%.")

            if business.get("market_cap"):
                mc = business["market_cap"]
                tier = "large-cap" if mc >= 1e10 else "mid-cap" if mc >= 2e9 else "small-cap"
                parts.append(f"Market capitalization places it as a {tier}.")

        if risks.get("available"):
            rs = risks.get("composite_risk_score")
            if rs is not None:
                level = "low" if rs < 30 else "moderate" if rs < 60 else "high"
                parts.append(f"The composite risk score of {rs:.0f}/100 is {level}.")
            rr = risks.get("risk_rating")
            if rr:
                parts.append(f"Risk rating: {rr}.")
            liq = risks.get("liquidity_rating")
            if liq:
                parts.append(f"Liquidity is rated as '{liq}'.")

        if growth.get("available"):
            ret = growth.get("price_returns", {})
            yr = ret.get("1y")
            if yr is not None:
                desc = "strong" if yr > 20 else "moderate" if yr > 5 else "flat" if yr > -5 else "negative"
                parts.append(f"Over the past year, the stock returned {yr:+.1f}% ({desc}).")

            fg = growth.get("fundamental_growth", {})
            rg = fg.get("revenue_growth", [])
            if rg:
                latest = rg[0].get("value")
                if latest is not None:
                    d = "growing" if latest > 0 else "declining"
                    parts.append(f"Revenue growth of {latest*100:.1f}% indicates {d} revenue.")

        if competition.get("available"):
            pc = competition.get("peer_count", 0)
            parts.append(f"Within its sector, {symbol} competes with {pc} other companies.")
            peers = competition.get("peers", [])
            if peers and competition.get("company_market_cap"):
                our_mc = competition["company_market_cap"]
                larger = sum(1 for p in peers if (p.get("market_cap") or 0) > our_mc)
                smaller = sum(1 for p in peers if (p.get("market_cap") or 0) < our_mc and (p.get("market_cap") or 0) > 0)
                if larger > 0:
                    parts.append(f"There are {larger} larger and {smaller} smaller peers by market cap.")

        return " ".join(parts) if parts else f"Insufficient data to generate a summary for {symbol}."

    # ---- HTML builder ----

    def _build_html(
        self, symbol: str, as_of_date: date,
        business: dict, financials: dict, risks: dict,
        growth: dict, competition: dict, ai_summary: str,
    ) -> str:
        name = business.get("company_name", symbol) if business.get("available") else symbol

        pe_count = len(competition.get("peers", [])) if competition.get("available") else 0
        ev_count = len(business.get("recent_events", [])) if business.get("available") else 0
        sub_count = len(business.get("subsidiaries", [])) if business.get("available") else 0
        prom_count = len(business.get("promoters", [])) if business.get("available") else 0
        stmt_count = len(financials.get("statements", [])) if financials.get("available") else 0

        sector = business.get("sector", "N/A") if business.get("available") else "N/A"
        industry = business.get("industry", "N/A") if business.get("available") else "N/A"
        exchange = business.get("exchange", "N/A") if business.get("available") else "N/A"

        mc = business.get("market_cap") if business.get("available") else None
        mc_str = f"${mc:,}" if mc else "N/A"
        status = business.get("status", "N/A") if business.get("available") else "N/A"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Company Research - {name} ({symbol})</title>
<style>
@page {{ margin: 20mm 15mm; size: A4; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #1a1a2e; background: #f0f2f5; line-height: 1.6; }}
.container {{ max-width: 1100px; margin: 0 auto; padding: 20px; }}
.header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: #fff; padding: 30px; border-radius: 12px; margin-bottom: 24px; }}
.header h1 {{ font-size: 26px; margin-bottom: 6px; }}
.header .subtitle {{ font-size: 14px; color: #a0aec0; }}
.header .meta {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 14px; font-size: 13px; }}
.header .meta span {{ background: rgba(255,255,255,0.1); padding: 4px 12px; border-radius: 6px; }}
.section {{ background: #fff; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
.section h2 {{ font-size: 18px; color: #1a1a2e; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; margin-bottom: 16px; }}
.section h2 span {{ color: #667eea; }}
.grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
.grid-3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }}
.metric-card {{ background: #f7fafc; padding: 14px; border-radius: 8px; border-left: 3px solid #667eea; }}
.metric-card .label {{ font-size: 11px; color: #718096; text-transform: uppercase; }}
.metric-card .value {{ font-size: 18px; font-weight: 700; color: #1a1a2e; }}
.summary-box {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #fff; padding: 20px; border-radius: 12px; margin-bottom: 24px; font-size: 14px; line-height: 1.8; }}
.summary-box h2 {{ color: #fff; border-bottom-color: rgba(255,255,255,0.3); }}
table.data-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
table.data-table th {{ background: #edf2f7; padding: 8px 12px; text-align: left; font-weight: 600; color: #4a5568; border-bottom: 2px solid #e2e8f0; }}
table.data-table td {{ padding: 8px 12px; border-bottom: 1px solid #e2e8f0; }}
table.data-table tr:hover {{ background: #f7fafc; }}
.badge {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }}
.badge-green {{ background: #c6f6d5; color: #22543d; }}
.badge-red {{ background: #fed7d7; color: #9b2c2c; }}
.badge-yellow {{ background: #fefcbf; color: #744210; }}
.badge-blue {{ background: #bee3f8; color: #2a4365; }}
.footer {{ text-align: center; font-size: 12px; color: #a0aec0; padding: 20px; }}
@media print {{
    body {{ background: #fff; }}
    .container {{ max-width: 100%; padding: 0; }}
    .section {{ box-shadow: none; border: 1px solid #e2e8f0; break-inside: avoid; }}
    .header, .summary-box {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
}}
</style>
</head>
<body>
<div class="container">

<div class="header">
<h1>{name} ({symbol})</h1>
<div class="subtitle">Company Research Report &mdash; {as_of_date.isoformat()}</div>
<div class="meta">
    <span>Sector: {sector}</span>
    <span>Industry: {industry}</span>
    <span>Exchange: {exchange}</span>
    <span>Market Cap: {mc_str}</span>
    <span>Status: {status}</span>
</div>
</div>

{self._build_ai_summary_html(ai_summary)}

<div class="section">
<h2><span>01</span> Business Overview</h2>
{self._build_business_html(business)}
</div>

<div class="section">
<h2><span>02</span> Financials</h2>
{self._build_financials_html(financials)}
</div>

<div class="section">
<h2><span>03</span> Risk Assessment</h2>
{self._build_risks_html(risks)}
</div>

<div class="section">
<h2><span>04</span> Growth Analysis</h2>
{self._build_growth_html(growth)}
</div>

<div class="section">
<h2><span>05</span> Competition</h2>
{self._build_competition_html(competition)}
</div>

<div class="footer">
<p>Generated by TitanX Research Platform &mdash; {as_of_date.isoformat()}</p>
<p>This report is for informational purposes only. Not investment advice.</p>
</div>

</div>
</body>
</html>"""

    def _build_ai_summary_html(self, ai_summary: str) -> str:
        return f"""<div class="summary-box">
<h2 style="color:#fff;border-bottom:1px solid rgba(255,255,255,0.3);padding-bottom:10px;margin-bottom:12px;">AI Summary</h2>
<p>{ai_summary}</p>
</div>"""

    def _build_business_html(self, business: dict) -> str:
        if not business.get("available"):
            return "<p style='color:#a0aec0;font-size:13px;'>No business data available</p>"

        desc = business.get("description")
        desc_html = f"<p style='margin-bottom:12px;'>{desc}</p>" if desc else ""

        website = business.get("website")
        web_html = f'<p style="margin-bottom:12px;"><strong>Website:</strong> <a href="{website}" style="color:#667eea;">{website}</a></p>' if website else ""

        subs = business.get("subsidiaries", [])
        sub_html = ""
        if subs:
            rows = "".join(
                f"<tr><td>{s['name']}</td><td>{s.get('symbol', '')}</td><td>{s.get('ownership_pct', '')}%</td></tr>"
                for s in subs
            )
            sub_html = f"""
<h3 style="margin:16px 0 8px;font-size:14px;color:#4a5568;">Subsidiaries ({len(subs)})</h3>
<table class="data-table"><thead><tr><th>Name</th><th>Symbol</th><th>Ownership</th></tr></thead><tbody>{rows}</tbody></table>"""

        prom = business.get("promoters", [])
        prom_html = ""
        if prom:
            rows = "".join(
                f"<tr><td>{p['name']}</td><td>{p.get('type', '')}</td><td>{p.get('ownership_pct', '')}%</td><td>{p.get('role', '')}</td></tr>"
                for p in prom
            )
            prom_html = f"""
<h3 style="margin:16px 0 8px;font-size:14px;color:#4a5568;">Promoters ({len(prom)})</h3>
<table class="data-table"><thead><tr><th>Name</th><th>Type</th><th>Ownership</th><th>Role</th></tr></thead><tbody>{rows}</tbody></table>"""

        events = business.get("recent_events", [])
        ev_html = ""
        if events:
            rows = "".join(
                f"<tr><td>{e['event_type']}</td><td>{e['event_date']}</td><td>{e['title'][:60]}</td><td>{e.get('impact_score', '')}</td></tr>"
                for e in events
            )
            ev_html = f"""
<h3 style="margin:16px 0 8px;font-size:14px;color:#4a5568;">Recent Events ({len(events)})</h3>
<table class="data-table"><thead><tr><th>Type</th><th>Date</th><th>Title</th><th>Impact</th></tr></thead><tbody>{rows}</tbody></table>"""

        listing = business.get("listing_date")

        return f"""
<div class="grid-2">
    <div class="metric-card"><div class="label">Sector</div><div class="value">{business.get('sector', 'N/A')}</div></div>
    <div class="metric-card"><div class="label">Industry</div><div class="value">{business.get('industry', 'N/A')}</div></div>
    <div class="metric-card"><div class="label">Exchange</div><div class="value">{business.get('exchange', 'N/A')}</div></div>
    <div class="metric-card"><div class="label">Listed Since</div><div class="value">{listing or 'N/A'}</div></div>
    <div class="metric-card"><div class="label">ISIN</div><div class="value">{business.get('isin', 'N/A')}</div></div>
    <div class="metric-card"><div class="label">Status</div><div class="value">{business.get('status', 'N/A')}</div></div>
</div>
{desc_html}
{web_html}
{sub_html}
{prom_html}
{ev_html}"""

    def _build_financials_html(self, financials: dict) -> str:
        if not financials.get("available"):
            return "<p style='color:#a0aec0;font-size:13px;'>No financial data available</p>"

        metrics = financials.get("key_metrics", {})
        def card(label: str, val, suffix: str = "") -> str:
            v = f"{val:.2f}{suffix}" if val is not None else "N/A"
            return f'<div class="metric-card"><div class="label">{label}</div><div class="value">{v}</div></div>'

        met_html = f"""
<h3 style="margin:0 0 12px;font-size:14px;color:#4a5568;">Key Financial Metrics</h3>
<div class="grid-3">
{card('P/E Ratio', metrics.get('pe_ratio'))}
{card('P/B Ratio', metrics.get('pb_ratio'))}
{card('Debt/Equity', metrics.get('debt_to_equity'))}
{card('Current Ratio', metrics.get('current_ratio'))}
{card('Profit Margin', metrics.get('profit_margin'), '%')}
{card('Revenue Growth', metrics.get('revenue_growth'), '%')}
{card('EPS Growth', metrics.get('eps_growth'), '%')}
{card('ROE', metrics.get('roe'), '%')}
{card('ROA', metrics.get('roa'), '%')}
</div>"""

        stmts = financials.get("statements", [])
        stmt_html = ""
        if stmts:
            stmt_html = '<h3 style="margin:16px 0 8px;font-size:14px;color:#4a5568;">Financial Statements</h3>'
            for stmt in stmts:
                items = stmt.get("line_items", [])
                if not items:
                    continue
                rows = "".join(
                    f"<tr><td>{li.get('label', li['concept'])}</td><td>{li.get('value', '')}</td><td>{li.get('unit', '')}</td></tr>"
                    for li in items
                )
                stmt_html += f"""
<table class="data-table" style="margin-bottom:12px;">
<caption style="text-align:left;font-weight:600;padding:4px 0;color:#1a1a2e;">
{stmt['statement_type'].title()} — FY{stmt['fiscal_year']} Q{stmt['fiscal_period']} ({stmt['period_type']})
</caption>
<thead><tr><th>Item</th><th>Value</th><th>Unit</th></tr></thead>
<tbody>{rows}</tbody>
</table>"""

        return met_html + stmt_html

    def _build_risks_html(self, risks: dict) -> str:
        if not risks.get("available"):
            return "<p style='color:#a0aec0;font-size:13px;'>No risk data available</p>"

        def card(label: str, val, suffix: str = "") -> str:
            v = f"{val:.2f}{suffix}" if val is not None else "N/A"
            return f'<div class="metric-card"><div class="label">{label}</div><div class="value">{v}</div></div>'

        rs = risks.get("composite_risk_score")
        risk_badge = ""
        if rs is not None:
            cls = "badge-green" if rs < 30 else "badge-yellow" if rs < 60 else "badge-red"
            risk_badge = f'<span class="badge {cls}" style="font-size:14px;margin-left:8px;">{rs:.0f}/100</span>'

        rr = risks.get("risk_rating")
        rr_html = f"<span style='margin-left:4px;'>({rr})</span>" if rr else ""

        return f"""
<div class="grid-3">
    <div class="metric-card"><div class="label">Composite Risk{risk_badge}</div><div class="value">{'' if rs is None else ''}{rr_html}</div></div>
    <div class="metric-card"><div class="label">Volatility (20D)</div><div class="value">{card('', risks.get('volatility_20d'))}</div></div>
    <div class="metric-card"><div class="label">Volatility (60D)</div><div class="value">{card('', risks.get('volatility_60d'))}</div></div>
    <div class="metric-card"><div class="label">Max Drawdown (1M)</div><div class="value">{card('', risks.get('max_drawdown_1m'), '%')}</div></div>
    <div class="metric-card"><div class="label">Max Drawdown (3M)</div><div class="value">{card('', risks.get('max_drawdown_3m'), '%')}</div></div>
    <div class="metric-card"><div class="label">Max Drawdown (6M)</div><div class="value">{card('', risks.get('max_drawdown_6m'), '%')}</div></div>
</div>
<div class="grid-2" style="margin-top:16px;">
    <div class="metric-card"><div class="label">Liquidity Score / Rating</div><div class="value">{card('', risks.get('liquidity_score'))} / {risks.get('liquidity_rating', 'N/A')}</div></div>
    <div class="metric-card"><div class="label">Event Risk / News Count</div><div class="value">{card('', risks.get('event_risk_score'))} / {risks.get('news_count_30d', 'N/A')}</div></div>
</div>

<h3 style="margin:16px 0 8px;font-size:14px;color:#4a5568;">Regime Context</h3>
<div class="grid-2">
    <div class="metric-card"><div class="label">Trend Regime</div><div class="value">{risks.get('trend_regime', 'N/A')}</div></div>
    <div class="metric-card"><div class="label">Volatility Regime</div><div class="value">{risks.get('volatility_regime', 'N/A')}</div></div>
</div>"""

    def _build_growth_html(self, growth: dict) -> str:
        if not growth.get("available"):
            return "<p style='color:#a0aec0;font-size:13px;'>No growth data available</p>"

        ret = growth.get("price_returns", {})
        def card(label: str, val) -> str:
            if val is None:
                return f'<div class="metric-card"><div class="label">{label}</div><div class="value">N/A</div></div>'
            cls = "green" if val >= 0 else "red"
            return f'<div class="metric-card"><div class="label">{label}</div><div class="value" style="color:{cls};">{val:+.2f}%</div></div>'

        price_html = f"""
<h3 style="margin:0 0 12px;font-size:14px;color:#4a5568;">Price Returns</h3>
<div class="grid-3">
{card('1 Day', ret.get('1d'))}
{card('1 Month', ret.get('1m'))}
{card('3 Months', ret.get('3m'))}
{card('1 Year', ret.get('1y'))}
<div class="metric-card"><div class="label">Current Price</div><div class="value">${growth.get('current_price', 0):,.2f}</div></div>
</div>"""

        fg = growth.get("fundamental_growth", {})
        fund_html = ""
        if fg:
            fund_html = '<h3 style="margin:16px 0 8px;font-size:14px;color:#4a5568;">Fundamental Growth Trends</h3>'
            for metric_name, values in fg.items():
                if not values:
                    continue
                rows = "".join(
                    f"<tr><td>FY{v['fiscal_year']}</td><td>{v.get('value', 'N/A')}</td></tr>"
                    for v in values
                )
                fund_html += f"""
<table class="data-table" style="margin-bottom:8px;">
<caption style="text-align:left;font-weight:600;padding:4px 0;color:#1a1a2e;font-size:13px;">{metric_name.replace('_', ' ').title()}</caption>
<thead><tr><th>Period</th><th>Value</th></tr></thead>
<tbody>{rows}</tbody>
</table>"""

        sc = growth.get("sector_comparison")
        sc_html = ""
        if sc:
            sc_html = f"""
<h3 style="margin:16px 0 8px;font-size:14px;color:#4a5568;">Sector Context</h3>
<div class="grid-3">
    <div class="metric-card"><div class="label">Sector Return</div><div class="value">{sc.get('return_pct', 'N/A')}%</div></div>
    <div class="metric-card"><div class="label">Sector Momentum</div><div class="value">{sc.get('momentum_score', 'N/A')}</div></div>
    <div class="metric-card"><div class="label">Sector Rank</div><div class="value">{sc.get('rank', 'N/A')}</div></div>
</div>"""

        return price_html + fund_html + sc_html

    def _build_competition_html(self, competition: dict) -> str:
        if not competition.get("available"):
            return "<p style='color:#a0aec0;font-size:13px;'>{}</p>".format(
                competition.get("note", "No competition data available"),
            )

        peers = competition.get("peers", [])
        if not peers:
            return "<p style='color:#a0aec0;font-size:13px;'>No peer companies found in the same sector.</p>"

        our_mc = competition.get("company_market_cap")
        total = competition.get("peer_count", len(peers))

        rows = ""
        for p in peers:
            mc = p.get("market_cap")
            mc_str = f"${mc:,}" if mc else "N/A"
            pe_str = f"{p.get('pe_ratio'):.1f}x" if p.get("pe_ratio") is not None else "N/A"
            rows += f"<tr><td>{p['company_name']}</td><td>{p['symbol']}</td><td>{mc_str}</td><td>{pe_str}</td><td>{p.get('exchange', '')}</td></tr>"

        return f"""
<p style="margin-bottom:12px;font-size:13px;color:#4a5568;">
{competition.get('sector', 'N/A')} sector — {total} active peer{'' if total == 1 else 's'}
</p>
<table class="data-table">
<thead><tr><th>Company</th><th>Symbol</th><th>Market Cap</th><th>P/E</th><th>Exchange</th></tr></thead>
<tbody>{rows}</tbody>
</table>

<h3 style="margin:16px 0 8px;font-size:14px;color:#4a5568;">Market Position</h3>
<div class="grid-2">
    <div class="metric-card"><div class="label">Company Market Cap</div><div class="value">${our_mc:,}</div></div>
    <div class="metric-card"><div class="label">Peer Count</div><div class="value">{total}</div></div>
</div>"""
