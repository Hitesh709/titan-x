from collections.abc import Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import math

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from titan_x.db.repository import BaseRepository
from titan_x.models.company import Company
from titan_x.models.portfolio import Portfolio, PortfolioHolding, PortfolioTransaction
from titan_x.models.price import DailyPrice

logger = structlog.get_logger(__name__)


class PortfolioEngine:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._portfolio_repo = BaseRepository(session, Portfolio)
        self._holding_repo = BaseRepository(session, PortfolioHolding)
        self._txn_repo = BaseRepository(session, PortfolioTransaction)

    async def create_portfolio(
        self, name: str, description: str | None = None,
        metadata_json: str | None = None,
    ) -> dict[str, Any]:
        portfolio = await self._portfolio_repo.create(
            name=name, description=description,
            metadata_json=metadata_json or "{}",
        )
        return self._portfolio_to_dict(portfolio)

    async def list_portfolios(self, skip: int = 0, limit: int = 100) -> tuple[Sequence[Portfolio], int]:
        query = select(Portfolio).order_by(Portfolio.created_at.desc()).offset(skip).limit(limit)
        count_query = select(func.count()).select_from(Portfolio)
        total = (await self._session.execute(count_query)).scalar() or 0
        rows = (await self._session.execute(query)).scalars().all()
        return rows, total

    async def get_portfolio(self, portfolio_id: int) -> Portfolio | None:
        result = await self._session.execute(
            select(Portfolio).where(Portfolio.id == portfolio_id)
        )
        return result.scalar_one_or_none()

    async def delete_portfolio(self, portfolio_id: int) -> bool:
        return await self._portfolio_repo.delete(portfolio_id)

    async def record_transaction(
        self, portfolio_id: int, symbol: str, transaction_type: str,
        quantity: float, price: float, transaction_date: date | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        if transaction_type not in ("buy", "sell"):
            raise ValueError("transaction_type must be 'buy' or 'sell'")
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if price <= 0:
            raise ValueError("price must be positive")

        if transaction_date is None:
            transaction_date = date.today()

        portfolio = await self.get_portfolio(portfolio_id)
        if portfolio is None:
            raise ValueError(f"Portfolio {portfolio_id} not found")

        total_amount = quantity * price
        company = await self._get_company(symbol)
        sector = company.sector if company else None

        realized_pnl: float | None = None
        if transaction_type == "sell":
            holding = await self._get_holding(portfolio_id, symbol)
            if holding is None or holding.quantity < quantity:
                raise ValueError(f"Not enough shares to sell: have {holding.quantity if holding else 0}, trying to sell {quantity}")
            realized_pnl = (price - holding.average_price) * quantity

        txn = await self._txn_repo.create(
            portfolio_id=portfolio_id, symbol=symbol.upper(),
            transaction_type=transaction_type, quantity=quantity,
            price=price, total_amount=total_amount,
            transaction_date=transaction_date, realized_pnl=realized_pnl,
            notes=notes,
        )

        await self._update_holding(portfolio_id, symbol.upper(), sector, transaction_type, quantity, price, transaction_date)

        result = self._txn_to_dict(txn)
        result["realized_pnl"] = realized_pnl
        return result

    async def get_transactions(
        self, portfolio_id: int, symbol: str | None = None,
        transaction_type: str | None = None,
        start_date: date | None = None, end_date: date | None = None,
        skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[PortfolioTransaction], int]:
        query = select(PortfolioTransaction).where(PortfolioTransaction.portfolio_id == portfolio_id)
        count_query = select(func.count()).select_from(PortfolioTransaction).where(PortfolioTransaction.portfolio_id == portfolio_id)

        if symbol:
            query = query.where(PortfolioTransaction.symbol == symbol.upper())
            count_query = count_query.where(PortfolioTransaction.symbol == symbol.upper())
        if transaction_type:
            query = query.where(PortfolioTransaction.transaction_type == transaction_type)
            count_query = count_query.where(PortfolioTransaction.transaction_type == transaction_type)
        if start_date:
            query = query.where(PortfolioTransaction.transaction_date >= start_date)
            count_query = count_query.where(PortfolioTransaction.transaction_date >= start_date)
        if end_date:
            query = query.where(PortfolioTransaction.transaction_date <= end_date)
            count_query = count_query.where(PortfolioTransaction.transaction_date <= end_date)

        total = (await self._session.execute(count_query)).scalar() or 0
        query = query.order_by(desc(PortfolioTransaction.transaction_date)).offset(skip).limit(limit)
        rows = (await self._session.execute(query)).scalars().all()
        return rows, total

    async def get_holdings(
        self, portfolio_id: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        result = await self._session.execute(
            select(PortfolioHolding).where(
                PortfolioHolding.portfolio_id == portfolio_id,
                PortfolioHolding.quantity > 0,
            ).order_by(PortfolioHolding.symbol)
        )
        holdings = result.scalars().all()

        total_value = 0.0
        enriched: list[dict[str, Any]] = []
        for h in holdings:
            current_price = await self._get_current_price(h.symbol)
            market_value = (current_price or 0) * h.quantity
            unrealized_pnl = (current_price - h.average_price) * h.quantity if current_price and h.average_price else 0.0
            total_value += market_value
            enriched.append({
                "symbol": h.symbol,
                "sector": h.sector,
                "quantity": h.quantity,
                "average_price": round(h.average_price, 4) if h.average_price else None,
                "cost_basis": round(h.cost_basis, 2) if h.cost_basis else None,
                "current_price": round(current_price, 4) if current_price else None,
                "market_value": round(market_value, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "allocation_pct": 0.0,
                "as_of_date": h.as_of_date.isoformat() if h.as_of_date else None,
            })

        for item in enriched:
            if total_value > 0:
                item["allocation_pct"] = round((item["market_value"] / total_value) * 100, 2)

        summary = {"total_value": round(total_value, 2), "holding_count": len(enriched)}
        return enriched, summary

    async def get_pnl(self, portfolio_id: int) -> dict[str, Any]:
        realized = await self._get_realized_pnl(portfolio_id)
        holdings_enriched, _ = await self.get_holdings(portfolio_id)
        unrealized = sum(h.get("unrealized_pnl", 0) for h in holdings_enriched)
        return {
            "realized_pnl": round(realized, 2),
            "unrealized_pnl": round(unrealized, 2),
            "total_pnl": round(realized + unrealized, 2),
        }

    async def get_portfolio_allocation(self, portfolio_id: int) -> list[dict[str, Any]]:
        holdings, summary = await self.get_holdings(portfolio_id)
        total = summary["total_value"]
        if total <= 0:
            return [{"symbol": h["symbol"], "allocation_pct": 0.0, "market_value": h["market_value"]} for h in holdings]
        return [
            {
                "symbol": h["symbol"],
                "allocation_pct": round((h["market_value"] / total) * 100, 2),
                "market_value": h["market_value"],
            }
            for h in holdings
        ]

    async def get_sector_allocation(self, portfolio_id: int) -> list[dict[str, Any]]:
        holdings, summary = await self.get_holdings(portfolio_id)
        total = summary["total_value"]
        sector_map: dict[str, float] = {}
        for h in holdings:
            sec = h.get("sector") or "Unknown"
            sector_map[sec] = sector_map.get(sec, 0) + h["market_value"]
        if total <= 0:
            return [{"sector": k, "allocation_pct": 0.0, "market_value": round(v, 2)} for k, v in sector_map.items()]
        return [
            {
                "sector": k,
                "allocation_pct": round((v / total) * 100, 2),
                "market_value": round(v, 2),
            }
            for k, v in sorted(sector_map.items(), key=lambda x: -x[1])
        ]

    async def get_average_price(self, portfolio_id: int, symbol: str) -> dict[str, Any]:
        holding = await self._get_holding(portfolio_id, symbol.upper())
        if holding is None or holding.quantity <= 0:
            return {"symbol": symbol.upper(), "average_price": None, "quantity": 0, "cost_basis": None}
        return {
            "symbol": holding.symbol,
            "average_price": round(holding.average_price, 4) if holding.average_price else None,
            "quantity": holding.quantity,
            "cost_basis": round(holding.cost_basis, 2) if holding.cost_basis else None,
        }

    async def get_portfolio_summary(self, portfolio_id: int) -> dict[str, Any]:
        portfolio = await self.get_portfolio(portfolio_id)
        if portfolio is None:
            return {}
        holdings, holding_summary = await self.get_holdings(portfolio_id)
        pnl = await self.get_pnl(portfolio_id)
        allocation = await self.get_portfolio_allocation(portfolio_id)
        sector_alloc = await self.get_sector_allocation(portfolio_id)

        return {
            "portfolio": self._portfolio_to_dict(portfolio),
            "holdings": holdings,
            "pnl": pnl,
            "allocation": allocation,
            "sector_allocation": sector_alloc,
            "summary": holding_summary,
        }

    async def get_portfolio_beta(
        self, portfolio_id: int, benchmark_symbol: str = "SPY",
        days: int = 252,
    ) -> dict[str, Any]:
        holdings, _ = await self.get_holdings(portfolio_id)
        if not holdings:
            return {"beta": None, "error": "No holdings"}

        symbols = [h["symbol"] for h in holdings]
        weights = {h["symbol"]: h["allocation_pct"] / 100 for h in holdings if h["allocation_pct"] > 0}
        if not weights:
            return {"beta": None, "error": "No positive allocations"}

        end = date.today()
        start = end - timedelta(days=days + 30)

        benchmark_rets = await self._get_daily_returns(benchmark_symbol, start, end)
        if not benchmark_rets:
            return {"beta": None, "error": f"No price data for benchmark {benchmark_symbol}"}

        holding_rets: dict[str, list[float]] = {}
        for sym in weights:
            rets = await self._get_daily_returns(sym, start, end)
            if len(rets) >= 20:
                holding_rets[sym] = rets

        if not holding_rets:
            return {"beta": None, "error": "No return data for holdings"}

        min_len = min(len(benchmark_rets), *(len(r) for r in holding_rets.values()))
        b_rets = benchmark_rets[-min_len:]

        bench_mean = sum(b_rets) / len(b_rets)
        bench_var = sum((r - bench_mean) ** 2 for r in b_rets) / len(b_rets)
        if bench_var <= 0:
            return {"beta": None, "error": "Benchmark has zero variance"}

        individual_betas: list[dict[str, Any]] = []
        weighted_beta = 0.0
        total_w = sum(weights.values())
        for sym, rets in holding_rets.items():
            a_rets = rets[-min_len:]
            cov = sum((a_rets[i] - sum(a_rets) / len(a_rets)) * (b_rets[i] - bench_mean) for i in range(len(a_rets))) / len(a_rets)
            beta = cov / bench_var
            w = weights[sym] / total_w
            weighted_beta += w * beta
            individual_betas.append({
                "symbol": sym, "beta": round(beta, 4),
                "weight_pct": round(w * 100, 2),
            })

        individual_betas.sort(key=lambda x: -x["weight_pct"])
        return {
            "portfolio_beta": round(weighted_beta, 4),
            "benchmark_symbol": benchmark_symbol,
            "individual_betas": individual_betas,
            "observation_days": min_len,
        }

    async def get_correlation_matrix(
        self, portfolio_id: int, days: int = 252,
    ) -> dict[str, Any]:
        holdings, _ = await self.get_holdings(portfolio_id)
        if len(holdings) < 2:
            return {"correlation_matrix": [], "message": "Need at least 2 holdings"}

        symbols = [h["symbol"] for h in holdings]
        weights = {h["symbol"]: h["allocation_pct"] / 100 for h in holdings if h["allocation_pct"] > 0}
        end = date.today()
        start = end - timedelta(days=days + 30)

        all_rets: dict[str, list[float]] = {}
        for sym in symbols:
            rets = await self._get_daily_returns(sym, start, end)
            if len(rets) >= 20:
                all_rets[sym] = rets

        valid = [s for s in symbols if s in all_rets]
        if len(valid) < 2:
            return {"correlation_matrix": [], "message": "Insufficient return data for correlation"}

        min_len = min(len(all_rets[s]) for s in valid)
        aligned = {s: all_rets[s][-min_len:] for s in valid}

        n = len(valid)
        matrix = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if i == j:
                    matrix[i][j] = 1.0
                else:
                    r = self._pearson(aligned[valid[i]], aligned[valid[j]])
                    matrix[i][j] = round(r, 4)
                    matrix[j][i] = round(r, 4)

        avg_corr = 0.0
        count = 0
        for i in range(n):
            for j in range(i + 1, n):
                avg_corr += matrix[i][j]
                count += 1
        avg_corr = avg_corr / count if count > 0 else 0

        return {
            "symbols": valid,
            "matrix": matrix,
            "average_correlation": round(avg_corr, 4),
            "observation_days": min_len,
        }

    async def get_diversification_metrics(self, portfolio_id: int) -> dict[str, Any]:
        holdings, _ = await self.get_holdings(portfolio_id)
        if not holdings:
            return {"diversification_score": 0, "effective_n": 0, "holding_count": 0}

        weights = [h["allocation_pct"] / 100 for h in holdings if h["allocation_pct"] > 0]
        if not weights:
            return {"diversification_score": 0, "effective_n": 0, "holding_count": 0}

        w_sum = sum(weights)
        weights = [w / w_sum for w in weights]
        n = len(weights)
        hhi = sum(w ** 2 for w in weights)
        effective_n = 1.0 / hhi if hhi > 0 else 0
        max_w = max(weights)
        min_w = min(weights)
        avg_w = sum(weights) / n
        variance = sum((w - avg_w) ** 2 for w in weights) / n
        std = math.sqrt(variance)

        diversification_score = min(100, (1 - hhi) * 100)
        if effective_n >= n * 0.8:
            diversification_score = min(100, diversification_score + 10)

        return {
            "holding_count": n,
            "hhi": round(hhi, 4),
            "effective_n": round(effective_n, 2),
            "max_weight_pct": round(max_w * 100, 2),
            "min_weight_pct": round(min_w * 100, 2),
            "avg_weight_pct": round(avg_w * 100, 2),
            "weight_std_pct": round(std * 100, 2),
            "diversification_score": round(diversification_score, 1),
        }

    async def get_concentration_risk(self, portfolio_id: int) -> dict[str, Any]:
        holdings, _ = await self.get_holdings(portfolio_id)
        if not holdings:
            return {"concentration_score": 0, "top_1_pct": 0, "top_3_pct": 0, "top_5_pct": 0}

        sorted_h = sorted(holdings, key=lambda h: h["market_value"], reverse=True)
        total = sum(h["market_value"] for h in sorted_h)
        if total <= 0:
            return {"concentration_score": 100, "top_1_pct": 0, "top_3_pct": 0, "top_5_pct": 0, "hhi": 0}

        weights = [h["market_value"] / total for h in sorted_h]
        hhi = sum(w ** 2 for w in weights)
        top_1 = weights[0] * 100 if weights else 0
        top_3 = sum(weights[:3]) * 100
        top_5 = sum(weights[:5]) * 100
        threshold_pct = 0.05
        below_threshold = sum(1 for w in weights if w < threshold_pct)
        above_threshold = sum(1 for w in weights if w >= threshold_pct)

        concentration_score = min(100, hhi * 100)
        if top_1 > 50:
            concentration_score = min(100, concentration_score + 15)

        return {
            "concentration_score": round(concentration_score, 1),
            "hhi": round(hhi, 4),
            "top_1_pct": round(top_1, 2),
            "top_3_pct": round(top_3, 2),
            "top_5_pct": round(top_5, 2),
            "holdings_above_5pct": above_threshold,
            "holdings_below_5pct": below_threshold,
        }

    async def get_sector_exposure(self, portfolio_id: int) -> dict[str, Any]:
        holdings, _ = await self.get_holdings(portfolio_id)
        if not holdings:
            return {"sectors": [], "sector_hhi": 0, "sector_count": 0}

        total = sum(h["market_value"] for h in holdings)
        if total <= 0:
            return {"sectors": [], "sector_hhi": 0, "sector_count": 0, "max_sector_pct": 0}

        sector_map: dict[str, float] = {}
        for h in holdings:
            sec = h.get("sector") or "Unknown"
            sector_map[sec] = sector_map.get(sec, 0) + h["market_value"]

        sector_list = sorted(
            [{"sector": k, "allocation_pct": round(v / total * 100, 2), "market_value": round(v, 2)}
             for k, v in sector_map.items()],
            key=lambda x: -x["allocation_pct"],
        )

        sector_weights = [v / total for v in sector_map.values()]
        sector_hhi = sum(w ** 2 for w in sector_weights)
        max_sector = max(sector_weights) * 100 if sector_weights else 0

        return {
            "sectors": sector_list,
            "sector_count": len(sector_list),
            "sector_hhi": round(sector_hhi, 4),
            "max_sector_pct": round(max_sector, 2),
            "sector_diversification_score": round(min(100, (1 - sector_hhi) * 100), 1),
        }

    async def get_expected_drawdown(
        self, portfolio_id: int, days: int = 252, confidence: float = 0.95,
    ) -> dict[str, Any]:
        holdings, summary = await self.get_holdings(portfolio_id)
        if not holdings:
            return {"expected_drawdown_pct": 0, "max_drawdown_pct": 0}

        weights = {h["symbol"]: h["allocation_pct"] / 100 for h in holdings if h["allocation_pct"] > 0}
        if not weights:
            return {"expected_drawdown_pct": 0, "max_drawdown_pct": 0}

        w_sum = sum(weights.values())
        weights = {k: v / w_sum for k, v in weights.items()}

        end = date.today()
        start = end - timedelta(days=days + 30)

        all_rets: dict[str, list[float]] = {}
        for sym in weights:
            rets = await self._get_daily_returns(sym, start, end)
            if len(rets) >= 20:
                all_rets[sym] = rets

        if not all_rets:
            return {"expected_drawdown_pct": 0, "max_drawdown_pct": 0}

        min_len = min(len(r) for r in all_rets.values())
        portfolio_rets = [0.0] * min_len
        for sym, rets in all_rets.items():
            a = rets[-min_len:]
            w = weights[sym]
            for i in range(min_len):
                portfolio_rets[i] += w * a[i]

        cumulative = 1.0
        running_max = 1.0
        max_dd = 0.0
        dd_values: list[float] = []
        for r in portfolio_rets:
            cumulative *= (1 + r)
            if cumulative > running_max:
                running_max = cumulative
            dd = (cumulative - running_max) / running_max
            dd_values.append(dd)
            if dd < max_dd:
                max_dd = dd

        dd_values.sort()
        idx = int(len(dd_values) * (1 - confidence))
        expected_dd = dd_values[idx] if idx < len(dd_values) else dd_values[-1]

        mu = sum(portfolio_rets) / len(portfolio_rets)
        variance = sum((r - mu) ** 2 for r in portfolio_rets) / len(portfolio_rets)
        vol = math.sqrt(variance) * math.sqrt(252)
        parametric_dd = -(vol * 1.645 + mu * 20) / 100

        return {
            "historical_max_drawdown_pct": round(abs(max_dd) * 100, 2),
            "expected_drawdown_pct": round(abs(expected_dd) * 100, 2),
            "parametric_drawdown_pct": round(abs(parametric_dd) * 100, 2),
            "portfolio_volatility_pct": round(vol * 100, 2),
            "confidence_level": confidence,
            "observation_days": min_len,
        }

    async def get_portfolio_risk_score(self, portfolio_id: int) -> dict[str, Any]:
        holdings, _ = await self.get_holdings(portfolio_id)
        if not holdings:
            return {"risk_score": 0, "risk_rating": "none", "components": {}}

        beta_data = await self.get_portfolio_beta(portfolio_id)
        concentration = await self.get_concentration_risk(portfolio_id)
        drawdown = await self.get_expected_drawdown(portfolio_id)
        diversification = await self.get_diversification_metrics(portfolio_id)
        correlation = await self.get_correlation_matrix(portfolio_id)

        beta = abs(beta_data.get("portfolio_beta") or 1.0)
        beta_score = min(100, (beta - 0.5) * 100) if beta > 0.5 else 0
        conc_score = concentration.get("concentration_score", 0)
        dd_score = min(100, drawdown.get("expected_drawdown_pct", 0) * 2)
        vol_score = min(100, drawdown.get("portfolio_volatility_pct", 0) * 1.5)
        avg_corr = abs(correlation.get("average_correlation", 0))
        corr_score = min(100, avg_corr * 100)
        div_score = 100 - diversification.get("diversification_score", 0)

        risk_score = (
            beta_score * 0.15 + conc_score * 0.20 + dd_score * 0.20 +
            vol_score * 0.20 + corr_score * 0.10 + div_score * 0.15
        )

        if risk_score >= 80:
            rating = "extreme"
        elif risk_score >= 60:
            rating = "high"
        elif risk_score >= 40:
            rating = "medium"
        elif risk_score >= 20:
            rating = "low"
        else:
            rating = "very_low"

        return {
            "risk_score": round(risk_score, 1),
            "risk_rating": rating,
            "components": {
                "beta_score": round(beta_score, 1),
                "concentration_score": round(conc_score, 1),
                "drawdown_score": round(dd_score, 1),
                "volatility_score": round(vol_score, 1),
                "correlation_score": round(corr_score, 1),
                "diversification_deficit": round(div_score, 1),
            },
            "details": {
                "portfolio_beta": beta_data.get("portfolio_beta"),
                "concentration_hhi": concentration.get("hhi"),
                "expected_drawdown_pct": drawdown.get("expected_drawdown_pct"),
                "portfolio_volatility_pct": drawdown.get("portfolio_volatility_pct"),
                "average_correlation": correlation.get("average_correlation"),
            },
        }

    async def get_portfolio_risk_report(self, portfolio_id: int) -> dict[str, Any]:
        portfolio = await self.get_portfolio(portfolio_id)
        if portfolio is None:
            return {"error": "Portfolio not found"}

        holdings, summary = await self.get_holdings(portfolio_id)
        if not holdings:
            return {"error": "No holdings in portfolio"}

        beta_data = await self.get_portfolio_beta(portfolio_id)
        correlation_data = await self.get_correlation_matrix(portfolio_id)
        diversification = await self.get_diversification_metrics(portfolio_id)
        concentration = await self.get_concentration_risk(portfolio_id)
        sector_exposure = await self.get_sector_exposure(portfolio_id)
        drawdown = await self.get_expected_drawdown(portfolio_id)
        risk_score_data = await self.get_portfolio_risk_score(portfolio_id)

        return {
            "portfolio_id": portfolio_id,
            "portfolio_name": portfolio.name,
            "summary": summary,
            "beta": beta_data,
            "correlation": correlation_data,
            "diversification": diversification,
            "concentration_risk": concentration,
            "sector_exposure": sector_exposure,
            "expected_drawdown": drawdown,
            "risk_score": risk_score_data,
        }

    def _pearson(self, x: list[float], y: list[float]) -> float:
        n = len(x)
        if n < 3:
            return 0.0
        mx = sum(x) / n
        my = sum(y) / n
        num = sum((x[i] - mx) * (y[i] - my) for i in range(n))
        dx = math.sqrt(sum((xi - mx) ** 2 for xi in x))
        dy = math.sqrt(sum((yi - my) ** 2 for yi in y))
        if dx * dy == 0:
            return 0.0
        return num / (dx * dy)

    async def _get_daily_returns(self, symbol: str, start: date, end: date) -> list[float]:
        result = await self._session.execute(
            select(DailyPrice.close, DailyPrice.trade_date)
            .where(DailyPrice.symbol == symbol.upper(), DailyPrice.trade_date.between(start, end))
            .order_by(DailyPrice.trade_date)
        )
        rows = result.all()
        if len(rows) < 2:
            return []
        prices = [float(r.close) for r in rows]
        return [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))]

    async def _get_holding(self, portfolio_id: int, symbol: str) -> PortfolioHolding | None:
        result = await self._session.execute(
            select(PortfolioHolding).where(
                PortfolioHolding.portfolio_id == portfolio_id,
                PortfolioHolding.symbol == symbol.upper(),
            )
        )
        return result.scalar_one_or_none()

    async def _update_holding(
        self, portfolio_id: int, symbol: str, sector: str | None,
        transaction_type: str, quantity: float, price: float,
        as_of_date: date,
    ) -> None:
        holding = await self._get_holding(portfolio_id, symbol)
        if holding:
            if transaction_type == "buy":
                total_cost = (holding.average_price or 0) * holding.quantity + quantity * price
                holding.quantity += quantity
                holding.average_price = total_cost / holding.quantity if holding.quantity > 0 else 0
            else:
                holding.quantity -= quantity
                if holding.quantity <= 0:
                    holding.quantity = 0
                    holding.average_price = 0
                    holding.cost_basis = 0
                else:
                    holding.cost_basis = (holding.average_price or 0) * holding.quantity
            holding.cost_basis = (holding.average_price or 0) * holding.quantity
            holding.as_of_date = as_of_date
            if sector:
                holding.sector = sector
        else:
            if transaction_type == "buy":
                holding = PortfolioHolding(
                    portfolio_id=portfolio_id, symbol=symbol,
                    sector=sector, quantity=quantity,
                    average_price=price, cost_basis=quantity * price,
                    as_of_date=as_of_date,
                )
                self._session.add(holding)
        await self._session.flush()

    async def _get_realized_pnl(self, portfolio_id: int) -> float:
        result = await self._session.execute(
            select(func.coalesce(func.sum(PortfolioTransaction.realized_pnl), 0)).where(
                PortfolioTransaction.portfolio_id == portfolio_id,
                PortfolioTransaction.transaction_type == "sell",
            )
        )
        return float(result.scalar() or 0)

    async def _get_current_price(self, symbol: str) -> float | None:
        result = await self._session.execute(
            select(DailyPrice.close).where(DailyPrice.symbol == symbol.upper())
            .order_by(desc(DailyPrice.trade_date)).limit(1)
        )
        row = result.scalar_one_or_none()
        return float(row) if row else None

    async def _get_company(self, symbol: str) -> Company | None:
        result = await self._session.execute(
            select(Company).where(Company.symbol == symbol.upper())
        )
        return result.scalar_one_or_none()

    def _portfolio_to_dict(self, portfolio: Portfolio) -> dict[str, Any]:
        return {
            "id": portfolio.id,
            "name": portfolio.name,
            "description": portfolio.description,
            "metadata_json": portfolio.metadata_json,
            "created_at": portfolio.created_at.isoformat() if portfolio.created_at else None,
        }

    def _txn_to_dict(self, txn: PortfolioTransaction) -> dict[str, Any]:
        return {
            "id": txn.id,
            "portfolio_id": txn.portfolio_id,
            "symbol": txn.symbol,
            "transaction_type": txn.transaction_type,
            "quantity": txn.quantity,
            "price": txn.price,
            "total_amount": txn.total_amount,
            "transaction_date": txn.transaction_date.isoformat() if txn.transaction_date else None,
            "realized_pnl": txn.realized_pnl,
            "notes": txn.notes,
        }
