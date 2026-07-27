import json
import math
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.company import Company
from titan_x.models.portfolio import Portfolio, PortfolioHolding
from titan_x.models.portfolio_optimizer import OptimizationAllocation, PortfolioOptimization
from titan_x.models.price import DailyPrice
from titan_x.models.sector import SectorPerformance

logger = structlog.get_logger(__name__)

RISK_FREE_RATE = 0.05
MAX_ALLOCATION_PCT = 25.0
MIN_ALLOCATION_PCT = 1.0


class PortfolioOptimizerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.opt_repo = BaseRepository(session, PortfolioOptimization)
        self.alloc_repo = BaseRepository(session, OptimizationAllocation)

    async def optimize(
        self, portfolio_id: int, strategy: str = "risk_parity",
        constraints: dict | None = None,
    ) -> PortfolioOptimization:
        portfolio = await self._get_portfolio(portfolio_id)
        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found")

        constraints = constraints or {}
        if constraints.get("max_allocation_pct") is None:
            constraints["max_allocation_pct"] = MAX_ALLOCATION_PCT
        if constraints.get("min_allocation_pct") is None:
            constraints["min_allocation_pct"] = MIN_ALLOCATION_PCT

        holdings, _ = await self._get_holdings(portfolio_id)
        if not holdings:
            raise ValueError("Portfolio has no holdings")

        symbols = [h["symbol"] for h in holdings]
        companies = await self._get_companies(symbols)
        price_data = await self._get_price_data(symbols)
        sector_perf = await self._get_sector_performance()

        returns, risks = self._compute_returns_and_risks(price_data)
        correlations = self._compute_correlations(price_data, symbols)

        allocations = self._allocate(
            symbols, companies, returns, risks, correlations,
            strategy, constraints, sector_perf,
        )

        expected_ret = sum(a["allocation_pct"] / 100 * a["expected_return"] for a in allocations)
        expected_vol = self._portfolio_volatility(allocations, risks, correlations)
        sharpe = (expected_ret - RISK_FREE_RATE) / expected_vol if expected_vol > 0 else 0
        div_score = self._diversification_score(allocations)
        risk_score = self._risk_score(expected_vol, allocations, correlations)
        sector_balance = self._sector_balance_score(allocations)

        optimization = PortfolioOptimization(
            portfolio_id=portfolio_id,
            optimization_date=date.today(),
            strategy=strategy,
            expected_return=round(expected_ret, 4),
            expected_volatility=round(expected_vol, 4),
            sharpe_ratio=round(sharpe, 4),
            diversification_score=round(div_score, 1),
            risk_score=round(risk_score, 1),
            sector_balance_score=round(sector_balance, 1),
            total_holdings=len(allocations),
            constraints_json=json.dumps(constraints),
            report_json=json.dumps(self._generate_report(allocations, expected_ret, expected_vol, sharpe, div_score, risk_score, sector_balance)),
        )
        self.session.add(optimization)
        await self.session.flush()

        for rank, a in enumerate(allocations, 1):
            alloc = OptimizationAllocation(
                optimization_id=optimization.id,
                symbol=a["symbol"],
                sector=a["sector"],
                allocation_pct=a["allocation_pct"],
                expected_return=a["expected_return"],
                expected_risk=a["expected_risk"],
                weight=a["allocation_pct"] / 100,
                rank=rank,
            )
            self.session.add(alloc)

        await self.session.flush()
        await self.session.refresh(optimization)
        return optimization

    async def get_optimization(self, optimization_id: int) -> PortfolioOptimization | None:
        r = await self.session.execute(
            select(PortfolioOptimization).where(PortfolioOptimization.id == optimization_id)
        )
        return r.scalar_one_or_none()

    async def get_allocations(
        self, optimization_id: int,
    ) -> list[OptimizationAllocation]:
        r = await self.session.execute(
            select(OptimizationAllocation).where(
                OptimizationAllocation.optimization_id == optimization_id,
            ).order_by(OptimizationAllocation.rank)
        )
        return list(r.scalars().all())

    async def get_history(
        self, portfolio_id: int, limit: int = 20,
    ) -> list[PortfolioOptimization]:
        r = await self.session.execute(
            select(PortfolioOptimization).where(
                PortfolioOptimization.portfolio_id == portfolio_id,
            ).order_by(desc(PortfolioOptimization.optimization_date)).limit(limit)
        )
        return list(r.scalars().all())

    async def _get_portfolio(self, portfolio_id: int) -> Portfolio | None:
        r = await self.session.execute(
            select(Portfolio).where(Portfolio.id == portfolio_id)
        )
        return r.scalar_one_or_none()

    async def _get_holdings(self, portfolio_id: int) -> tuple[list[dict], dict]:
        r = await self.session.execute(
            select(PortfolioHolding).where(
                PortfolioHolding.portfolio_id == portfolio_id,
                PortfolioHolding.quantity > 0,
            )
        )
        holdings = list(r.scalars().all())
        enriched = []
        total_value = 0
        for h in holdings:
            current = await self._get_current_price(h.symbol)
            mv = (current or 100) * h.quantity
            total_value += mv
            enriched.append({"symbol": h.symbol, "sector": h.sector, "market_value": mv, "current_price": current})
        for h in enriched:
            if total_value > 0:
                h["current_allocation"] = h["market_value"] / total_value * 100
        return enriched, {"total_value": total_value}

    async def _get_companies(self, symbols: list[str]) -> dict[str, Company]:
        r = await self.session.execute(
            select(Company).where(Company.symbol.in_(symbols))
        )
        return {c.symbol: c for c in r.scalars().all()}

    async def _get_price_data(self, symbols: list[str]) -> dict[str, list[float]]:
        end = date.today()
        start = end - timedelta(days=400)
        r = await self.session.execute(
            select(DailyPrice).where(
                DailyPrice.symbol.in_(symbols),
                DailyPrice.trade_date >= start,
            ).order_by(DailyPrice.symbol, DailyPrice.trade_date)
        )
        prices = list(r.scalars().all())
        result = defaultdict(list)
        for p in prices:
            result[p.symbol].append(float(p.close))
        return dict(result)

    async def _get_sector_performance(self) -> dict[str, float]:
        end = date.today()
        r = await self.session.execute(
            select(SectorPerformance).where(
                SectorPerformance.as_of_date == end,
                SectorPerformance.period_label == "1M",
            )
        )
        rows = list(r.scalars().all())
        if not rows:
            r = await self.session.execute(
                select(SectorPerformance).where(
                    SectorPerformance.period_label == "1M",
                ).order_by(desc(SectorPerformance.as_of_date)).limit(20)
            )
            rows = list(r.scalars().all())
        perf = {}
        for row in rows:
            if row.return_pct is not None:
                if row.sector not in perf:
                    perf[row.sector] = row.return_pct
        return perf

    async def _get_current_price(self, symbol: str) -> float | None:
        r = await self.session.execute(
            select(DailyPrice.close).where(DailyPrice.symbol == symbol)
            .order_by(desc(DailyPrice.trade_date)).limit(1)
        )
        row = r.scalar_one_or_none()
        return float(row) if row else None

    def _compute_returns_and_risks(
        self, price_data: dict[str, list[float]],
    ) -> tuple[dict[str, float], dict[str, float]]:
        returns = {}
        risks = {}
        for sym, prices in price_data.items():
            if len(prices) < 20:
                returns[sym] = 0.08
                risks[sym] = 0.20
                continue
            rets = [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))]
            ann_ret = (1 + sum(rets) / len(rets)) ** 252 - 1
            ann_vol = math.sqrt(sum((r - sum(rets) / len(rets)) ** 2 for r in rets) / len(rets)) * math.sqrt(252)
            returns[sym] = max(ann_ret, -0.5)
            risks[sym] = max(ann_vol, 0.05)
        return returns, risks

    def _compute_correlations(
        self, price_data: dict[str, list[float]], symbols: list[str],
    ) -> dict[tuple[str, str], float]:
        corr = {}
        for i, s1 in enumerate(symbols):
            for s2 in symbols[i:]:
                if s1 not in price_data or s2 not in price_data:
                    corr[(s1, s2)] = corr[(s2, s1)] = 0.5
                    continue
                r1 = price_data[s1]
                r2 = price_data[s2]
                n = min(len(r1), len(r2))
                if n < 10:
                    corr[(s1, s2)] = corr[(s2, s1)] = 0.5
                    continue
                rets1 = [(r1[i] - r1[i - 1]) / r1[i - 1] for i in range(1, n)]
                rets2 = [(r2[i] - r2[i - 1]) / r2[i - 1] for i in range(1, n)]
                m1 = sum(rets1) / len(rets1)
                m2 = sum(rets2) / len(rets2)
                num = sum((rets1[i] - m1) * (rets2[i] - m2) for i in range(len(rets1)))
                d1 = math.sqrt(sum((r - m1) ** 2 for r in rets1))
                d2 = math.sqrt(sum((r - m2) ** 2 for r in rets2))
                c = num / (d1 * d2) if d1 * d2 > 0 else 0
                corr[(s1, s2)] = corr[(s2, s1)] = max(-1, min(1, c))
        return corr

    def _allocate(
        self, symbols: list[str], companies: dict[str, Company],
        returns: dict[str, float], risks: dict[str, float],
        correlations: dict[tuple[str, str], float],
        strategy: str, constraints: dict,
        sector_perf: dict[str, float],
    ) -> list[dict]:
        max_alloc = constraints.get("max_allocation_pct", MAX_ALLOCATION_PCT)
        min_alloc = constraints.get("min_allocation_pct", MIN_ALLOCATION_PCT)
        n = len(symbols)

        if strategy == "equal_weight":
            alloc = {s: 100.0 / n for s in symbols}
        elif strategy == "risk_parity":
            inv_risk = {s: 1.0 / max(risks.get(s, 0.2), 0.05) for s in symbols}
            total = sum(inv_risk.values())
            alloc = {s: inv_risk[s] / total * 100 for s in symbols}
        elif strategy == "max_sharpe":
            inv_vol = {s: returns.get(s, 0.08) / max(risks.get(s, 0.2), 0.05) for s in symbols}
            total = sum(max(v, 0) for v in inv_vol.values())
            if total <= 0:
                alloc = {s: 100.0 / n for s in symbols}
            else:
                alloc = {s: max(inv_vol.get(s, 0), 0) / total * 100 for s in symbols}
        elif strategy == "sector_balanced":
            sector_groups = defaultdict(list)
            sector_mom = {}
            for s in symbols:
                sec = companies.get(s, None)
                sec_name = sec.sector if sec and sec.sector else "Unknown"
                sector_groups[sec_name].append(s)
                sector_mom[sec_name] = sector_perf.get(sec_name, 0)
            sorted_sectors = sorted(sector_mom.keys(), key=lambda x: sector_mom.get(x, 0), reverse=True)
            sector_alloc = {}
            for i, sec in enumerate(sorted_sectors):
                sector_alloc[sec] = (100.0 / len(sorted_sectors)) * (1 + sector_mom.get(sec, 0) * 0.5)
            sec_total = sum(sector_alloc.values())
            if sec_total > 0:
                sector_alloc = {k: v / sec_total * 100 for k, v in sector_alloc.items()}
            alloc = {}
            for sec, symbols_list in sector_groups.items():
                per_sym = sector_alloc.get(sec, 100.0 / len(sector_groups)) / len(symbols_list)
                for s in symbols_list:
                    alloc[s] = per_sym
        else:
            alloc = {s: 100.0 / n for s in symbols}

        for s in alloc:
            alloc[s] = max(min_alloc, min(max_alloc, alloc[s]))
        total = sum(alloc.values())
        if total > 0:
            alloc = {s: v / total * 100 for s, v in alloc.items()}

        result = []
        for s in alloc:
            sec = companies.get(s, None)
            result.append({
                "symbol": s,
                "sector": sec.sector if sec and sec.sector else "Unknown",
                "allocation_pct": round(alloc[s], 2),
                "expected_return": round(returns.get(s, 0.08), 4),
                "expected_risk": round(risks.get(s, 0.20), 4),
            })
        result.sort(key=lambda x: -x["allocation_pct"])
        return result

    def _portfolio_volatility(
        self, allocations: list[dict],
        risks: dict[str, float],
        correlations: dict[tuple[str, str], float],
    ) -> float:
        n = len(allocations)
        var = 0.0
        for i in range(n):
            for j in range(n):
                s1, s2 = allocations[i]["symbol"], allocations[j]["symbol"]
                w1 = allocations[i]["allocation_pct"] / 100
                w2 = allocations[j]["allocation_pct"] / 100
                r1 = risks.get(s1, 0.2)
                r2 = risks.get(s2, 0.2)
                c = correlations.get((s1, s2), 0.5)
                var += w1 * w2 * r1 * r2 * c
        return math.sqrt(max(var, 0))

    def _diversification_score(self, allocations: list[dict]) -> float:
        weights = [a["allocation_pct"] / 100 for a in allocations]
        hhi = sum(w ** 2 for w in weights)
        return min(100, (1 - hhi) * 100)

    def _risk_score(self, vol: float, allocations: list[dict], correlations: dict) -> float:
        return min(100, vol * 100 * 2)

    def _sector_balance_score(self, allocations: list[dict]) -> float:
        sectors = defaultdict(float)
        for a in allocations:
            sectors[a["sector"]] += a["allocation_pct"]
        weights = [v / 100 for v in sectors.values()]
        hhi = sum(w ** 2 for w in weights)
        return min(100, (1 - hhi) * 100)

    def _generate_report(
        self, allocations: list[dict], expected_ret: float,
        expected_vol: float, sharpe: float, div_score: float,
        risk_score: float, sector_balance: float,
    ) -> dict:
        top_holdings = sorted(allocations, key=lambda x: -x["allocation_pct"])[:5]
        sectors = defaultdict(float)
        for a in allocations:
            sectors[a["sector"]] += a["allocation_pct"]
        top_sectors = sorted(sectors.items(), key=lambda x: -x[1])[:3]
        return {
            "summary": {
                "expected_annual_return": f"{expected_ret * 100:.2f}%",
                "expected_volatility": f"{expected_vol * 100:.2f}%",
                "sharpe_ratio": f"{sharpe:.2f}",
                "risk_free_rate": f"{RISK_FREE_RATE:.2%}",
            },
            "scores": {
                "diversification": f"{div_score:.1f}/100",
                "risk": f"{risk_score:.1f}/100",
                "sector_balance": f"{sector_balance:.1f}/100",
            },
            "top_holdings": [
                {
                    "symbol": h["symbol"],
                    "allocation": f"{h['allocation_pct']:.1f}%",
                    "expected_return": f"{h['expected_return'] * 100:.1f}%",
                    "expected_risk": f"{h['expected_risk'] * 100:.1f}%",
                }
                for h in top_holdings
            ],
            "sector_exposure": [
                {"sector": s, "exposure": f"{pct:.1f}%"}
                for s, pct in top_sectors
            ],
            "recommendations": self._generate_recommendations(div_score, risk_score, sector_balance),
        }

    def _generate_recommendations(
        self, div_score: float, risk_score: float, sector_balance: float,
    ) -> list[str]:
        recs = []
        if div_score < 50:
            recs.append("Consider increasing diversification — portfolio is too concentrated")
        if risk_score > 60:
            recs.append("Risk levels are elevated — consider adding lower-volatility positions")
        if sector_balance < 50:
            recs.append("Sector concentration is high — consider spreading across more sectors")
        if div_score >= 70 and risk_score <= 40 and sector_balance >= 70:
            recs.append("Portfolio is well-balanced — maintain current allocation")
        if not recs:
            recs.append("Portfolio optimization completed successfully")
        return recs
