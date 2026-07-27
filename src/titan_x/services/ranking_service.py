import json
import math
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from titan_x.models.company import Company
from titan_x.models.corporate_tracking import CorporateAnalysis
from titan_x.models.financial_analysis import FinancialAnalysis
from titan_x.models.institutional_holdings import InstitutionalAnalysis
from titan_x.models.microstructure import MarketMicrostructure
from titan_x.models.price import DailyPrice
from titan_x.models.ranking import StockRanking
from titan_x.models.risk import RiskMetrics
from titan_x.models.valuation import ValuationReport


class RankingService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def rank_all(self, as_of_date: date | None = None) -> list[StockRanking]:
        if as_of_date is None:
            as_of_date = date.today()

        companies_result = await self.session.execute(
            select(Company).where(Company.status == "active")
        )
        companies = list(companies_result.scalars().all())
        if not companies:
            return []

        symbols = [c.symbol for c in companies]
        company_map = {c.symbol: c for c in companies}

        # Bulk-load all data sources
        fa_map = await self._bulk_latest(FinancialAnalysis, FinancialAnalysis.symbol, symbols, FinancialAnalysis.analysis_date)
        ca_map = await self._bulk_latest_ca(CorporateAnalysis, symbols)
        ia_map = await self._bulk_latest_ia(InstitutionalAnalysis, symbols)
        vr_map = await self._bulk_latest(ValuationReport, ValuationReport.symbol, symbols, ValuationReport.report_date)
        ms_map = await self._bulk_latest(MarketMicrostructure, MarketMicrostructure.symbol, symbols, MarketMicrostructure.as_of_date)
        rk_map = await self._bulk_latest(RiskMetrics, RiskMetrics.symbol, symbols, RiskMetrics.as_of_date)
        mom_map = await self._bulk_momentum(symbols, as_of_date)

        scored = []
        for sym in symbols:
            fa = fa_map.get(sym)
            ca = ca_map.get(sym)
            ia = ia_map.get(sym)
            vr = vr_map.get(sym)
            ms = ms_map.get(sym)
            rk = rk_map.get(sym)
            mom = mom_map.get(sym, {})

            fh_score = self._score_financial_health(fa)
            val_score = self._score_valuation(vr)
            mom_score = self._score_momentum(mom)
            liq_score = self._score_liquidity(ms)
            risk_score = self._score_risk(rk)
            corp_score = self._score_corporate(ca)
            inst_score = self._score_institutional(ia)

            valid = [s for s in [fh_score, val_score, mom_score, liq_score, risk_score, corp_score, inst_score] if s is not None]
            composite = round(sum(valid) / len(valid), 1) if valid else 50.0

            if risk_score is not None:
                risk_adj = composite * (1 - (100 - risk_score) / 200)
            else:
                risk_adj = composite

            scored.append({
                "symbol": sym,
                "company_name": company_map[sym].company_name,
                "sector": company_map[sym].sector,
                "composite_score": composite,
                "financial_health_score": fh_score,
                "valuation_score": val_score,
                "momentum_score": mom_score,
                "liquidity_score": liq_score,
                "risk_adjusted_score": round(risk_adj, 1),
                "corporate_score": corp_score,
                "institutional_score": inst_score,
                "fa": fa,
                "vr": vr,
                "ms": ms,
                "rk": rk,
                "mom": mom,
            })

        scored.sort(key=lambda x: x["risk_adjusted_score"], reverse=True)

        rankings = []
        for idx, entry in enumerate(scored):
            rank = idx + 1
            tier = self._assign_tier(rank)
            is_best = rank == 1

            expl = self._build_explanation(entry, rank)

            ranking = StockRanking(
                as_of_date=as_of_date,
                rank=rank,
                symbol=entry["symbol"],
                company_name=entry["company_name"],
                sector=entry["sector"],
                composite_score=entry["composite_score"],
                financial_health_score=entry["financial_health_score"],
                valuation_score=entry["valuation_score"],
                momentum_score=entry["momentum_score"],
                liquidity_score=entry["liquidity_score"],
                risk_adjusted_score=entry["risk_adjusted_score"],
                corporate_score=entry["corporate_score"],
                institutional_score=entry["institutional_score"],
                tier=tier,
                is_best_opportunity=is_best,
                explanation_json=json.dumps(expl, indent=2),
                metadata_json=json.dumps({"total_ranked": len(scored)}),
            )
            self.session.add(ranking)
            rankings.append(ranking)

        await self.session.flush()
        for r in rankings:
            await self.session.refresh(r)
        return rankings

    async def get_ranking(self, symbol: str, as_of_date: date | None = None) -> StockRanking | None:
        stmt = select(StockRanking).where(StockRanking.symbol == symbol.upper())
        if as_of_date:
            stmt = stmt.where(StockRanking.as_of_date == as_of_date)
        stmt = stmt.order_by(StockRanking.as_of_date.desc()).limit(1)
        r = await self.session.execute(stmt)
        return r.scalar_one_or_none()

    async def get_top(self, tier: str, as_of_date: date | None = None) -> list[StockRanking]:
        stmt = select(StockRanking).where(StockRanking.tier == tier)
        if as_of_date:
            stmt = stmt.where(StockRanking.as_of_date == as_of_date)
        stmt = stmt.order_by(StockRanking.rank.asc())
        r = await self.session.execute(stmt)
        return list(r.scalars().all())

    async def get_best_opportunity(self, as_of_date: date | None = None) -> StockRanking | None:
        stmt = select(StockRanking).where(StockRanking.is_best_opportunity == True)
        if as_of_date:
            stmt = stmt.where(StockRanking.as_of_date == as_of_date)
        stmt = stmt.order_by(StockRanking.as_of_date.desc()).limit(1)
        r = await self.session.execute(stmt)
        return r.scalar_one_or_none()

    # ============================================================
    # BULK LOADERS
    # ============================================================

    async def _bulk_latest(self, model, symbol_col, symbols: list[str], date_col) -> dict[str, Any]:
        if not symbols:
            return {}
        # Use subquery to get latest per symbol (cross-DB compatible)
        max_date = (
            select(symbol_col, date_col.label("max_date"))
            .where(symbol_col.in_(symbols))
            .group_by(symbol_col)
            .subquery()
        )
        result = await self.session.execute(
            select(model).join(
                max_date,
                (symbol_col == max_date.c[0]) & (date_col == max_date.c[1])
            )
        )
        return {getattr(r, symbol_col.name): r for r in result.scalars().all()}

    async def _bulk_latest_ca(self, model, symbols: list[str]) -> dict[str, Any]:
        if not symbols:
            return {}
        result = await self.session.execute(
            select(Company.id, Company.symbol).where(Company.symbol.in_(symbols))
        )
        sym_to_id = {r[1]: r[0] for r in result.all()}
        ids = list(sym_to_id.values())
        if not ids:
            return {}
        max_date = (
            select(model.company_id, model.analysis_date.label("max_date"))
            .where(model.company_id.in_(ids))
            .group_by(model.company_id)
            .subquery()
        )
        ca_result = await self.session.execute(
            select(model).join(
                max_date,
                (model.company_id == max_date.c[0]) & (model.analysis_date == max_date.c[1])
            )
        )
        id_to_ca = {r.company_id: r for r in ca_result.scalars().all()}
        return {sym: id_to_ca[sym_to_id[sym]] for sym in symbols if sym_to_id.get(sym) in id_to_ca}

    async def _bulk_latest_ia(self, model, symbols: list[str]) -> dict[str, Any]:
        if not symbols:
            return {}
        result = await self.session.execute(
            select(Company.id, Company.symbol).where(Company.symbol.in_(symbols))
        )
        sym_to_id = {r[1]: r[0] for r in result.all()}
        ids = list(sym_to_id.values())
        if not ids:
            return {}
        max_date = (
            select(model.company_id, model.analysis_date.label("max_date"))
            .where(model.company_id.in_(ids))
            .group_by(model.company_id)
            .subquery()
        )
        ia_result = await self.session.execute(
            select(model).join(
                max_date,
                (model.company_id == max_date.c[0]) & (model.analysis_date == max_date.c[1])
            )
        )
        id_to_ia = {r.company_id: r for r in ia_result.scalars().all()}
        return {sym: id_to_ia[sym_to_id[sym]] for sym in symbols if sym_to_id.get(sym) in id_to_ia}

    async def _bulk_momentum(self, symbols: list[str], as_of_date: date) -> dict[str, dict]:
        if not symbols:
            return {}
        lookback = as_of_date - timedelta(days=60)
        result = await self.session.execute(
            select(DailyPrice).where(
                DailyPrice.symbol.in_(symbols),
                DailyPrice.trade_date >= lookback,
                DailyPrice.trade_date <= as_of_date,
            ).order_by(DailyPrice.symbol, DailyPrice.trade_date.asc())
        )
        prices = list(result.scalars().all())
        grouped = defaultdict(list)
        for p in prices:
            grouped[p.symbol].append(p)

        mom = {}
        for sym, pxs in grouped.items():
            if len(pxs) < 5:
                continue
            closes = [p.close for p in pxs]
            ret_1d = (closes[-1] - closes[-2]) / closes[-2] if len(closes) >= 2 else 0
            ret_5d = (closes[-1] - closes[-6]) / closes[-6] if len(closes) >= 6 else ret_1d
            ret_20d = (closes[-1] - closes[-21]) / closes[-21] if len(closes) >= 21 else ret_5d
            sma_20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else closes[-1]
            price_vs_sma = (closes[-1] - sma_20) / sma_20 if sma_20 > 0 else 0
            mom[sym] = {
                "ret_1d": ret_1d, "ret_5d": ret_5d, "ret_20d": ret_20d,
                "price_vs_sma_20": price_vs_sma,
                "closes": closes,
            }
        return mom

    # ============================================================
    # SCORING
    # ============================================================

    def _score_financial_health(self, fa: FinancialAnalysis | None) -> float | None:
        if fa and fa.overall_score is not None:
            return fa.overall_score
        return None

    def _score_valuation(self, vr: ValuationReport | None) -> float | None:
        if vr and vr.composite_fair_value is not None and vr.current_price and vr.current_price > 0:
            upside = (vr.composite_fair_value - vr.current_price) / vr.current_price
            score = 50 + upside * 100
            return max(0, min(100, round(score, 1)))
        return None

    def _score_momentum(self, mom: dict | None) -> float | None:
        if not mom:
            return None
        score = 50.0
        ret_20d = mom.get("ret_20d", 0)
        ret_5d = mom.get("ret_5d", 0)
        score += ret_20d * 150
        score += ret_5d * 100
        price_vs_sma = mom.get("price_vs_sma_20", 0)
        score += price_vs_sma * 100
        return max(0, min(100, round(score, 1)))

    def _score_liquidity(self, ms: MarketMicrostructure | None) -> float | None:
        if ms and ms.liquidity_score is not None:
            return ms.liquidity_score
        return None

    def _score_risk(self, rk: RiskMetrics | None) -> float | None:
        if rk and rk.composite_risk_score is not None:
            return max(0, min(100, round(100 - rk.composite_risk_score, 1)))
        return None

    def _score_corporate(self, ca: CorporateAnalysis | None) -> float | None:
        if ca and ca.weighted_score is not None:
            return ca.weighted_score
        return None

    def _score_institutional(self, ia: InstitutionalAnalysis | None) -> float | None:
        if ia and ia.composite_score is not None:
            return ia.composite_score
        return None

    def _assign_tier(self, rank: int) -> str:
        if rank <= 5:
            return "top_5"
        elif rank <= 10:
            return "top_10"
        elif rank <= 25:
            return "top_25"
        elif rank <= 50:
            return "top_50"
        elif rank <= 100:
            return "top_100"
        return "unranked"

    def _build_explanation(self, entry: dict, rank: int) -> dict:
        sym = entry["symbol"]
        score = entry["composite_score"]
        risk_adj = entry["risk_adjusted_score"]

        details = []
        strengths = []
        weaknesses = []

        fh = entry.get("financial_health_score")
        if fh is not None:
            details.append(f"Financial Health: {fh}/100")
            if fh >= 70:
                strengths.append("Strong financial health with high revenue growth, margins, and EPS momentum")
            elif fh < 40:
                weaknesses.append("Weak financial health — low growth, margins, or EPS")

        val = entry.get("valuation_score")
        if val is not None:
            details.append(f"Valuation: {val}/100")
            if val >= 60:
                strengths.append("Attractive valuation — stock trades below estimated fair value")
            elif val < 40:
                weaknesses.append("Rich valuation — stock trades above estimated fair value")

        mom = entry.get("momentum_score")
        if mom is not None:
            details.append(f"Momentum: {mom}/100")
            if mom >= 60:
                strengths.append("Strong price momentum with positive short/medium-term returns")
            elif mom < 40:
                weaknesses.append("Weak price momentum — negative short/medium-term returns")

        liq = entry.get("liquidity_score")
        if liq is not None:
            details.append(f"Liquidity: {liq}/100")
            if liq >= 60:
                strengths.append("High liquidity with strong volume and tight spreads")
            elif liq < 40:
                weaknesses.append("Low liquidity — thin trading volumes and wide spreads")

        risk = entry.get("risk_adjusted_score")
        if risk is not None:
            details.append(f"Risk-Adjusted Score: {risk}/100")

        corp = entry.get("corporate_score")
        if corp is not None:
            details.append(f"Corporate Action Score: {corp}/100")
            if corp >= 60:
                strengths.append("Positive corporate actions — promoter buying or insider confidence")
            elif corp < 40:
                weaknesses.append("Negative corporate signals — promoter selling or insider pessimism")

        inst = entry.get("institutional_score")
        if inst is not None:
            details.append(f"Institutional Score: {inst}/100")
            if inst >= 60:
                strengths.append("Strong institutional interest — FII/DII/MF increasing stakes")
            elif inst < 40:
                weaknesses.append("Weak institutional interest — FII/DII/MF reducing stakes")

        strategy = []
        if strengths and weaknesses:
            strategy.append(f"Rank #{rank}: {len(strengths)} strengths, {len(weaknesses)} weaknesses")
        if score >= 70:
            strategy.append("HIGH CONVICTION: Strong across multiple dimensions")
        elif score >= 55:
            strategy.append("MODERATE CONVICTION: Balanced risk-reward profile")
        elif score >= 40:
            strategy.append("CAUTIOUS: Mixed signals — selective positioning recommended")
        else:
            strategy.append("AVOID: Weak across most dimensions")

        return {
            "symbol": sym,
            "rank": rank,
            "composite_score": score,
            "risk_adjusted_score": risk_adj,
            "details": details,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "strategy": strategy,
            "summary": f"{sym} ranks #{rank} with a composite score of {score}/100 (risk-adjusted: {risk_adj}/100). "
                       f"{' '.join(strengths[:2])}" if strengths else f"No strong positive signals detected.",
        }
