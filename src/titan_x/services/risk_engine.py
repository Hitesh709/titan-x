import json
import math
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.company import Company
from titan_x.models.news import NewsArticle
from titan_x.models.price import DailyPrice
from titan_x.models.risk import PortfolioRisk, RiskMetrics

logger = structlog.get_logger(__name__)

DRAWDOWN_PERIODS = {"1m": 21, "3m": 63, "6m": 126, "1y": 252}
VOLATILITY_WINDOWS = {"20d": 20, "60d": 60, "252d": 252}
LIQUIDITY_WINDOW = 20
GAP_WINDOW = 60
RISK_FREE_RATE = 0.05


class RiskEngine:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._risk_repo = BaseRepository(session, RiskMetrics)
        self._portfolio_repo = BaseRepository(session, PortfolioRisk)

    async def _get_prices(
        self, symbol: str, start_date: date, end_date: date,
    ) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(DailyPrice)
            .where(
                DailyPrice.symbol == symbol,
                DailyPrice.trade_date.between(start_date, end_date),
            )
            .order_by(DailyPrice.trade_date)
        )
        return [
            {
                "trade_date": r.trade_date,
                "open": r.open, "close": r.close,
                "high": r.high, "low": r.low, "volume": r.volume,
            }
            for r in result.scalars().all()
        ]

    async def _get_company(self, symbol: str) -> Company | None:
        result = await self._session.execute(
            select(Company).where(Company.symbol == symbol),
        )
        return result.scalar_one_or_none()

    async def _get_news_count(self, symbol: str, days: int = 30) -> int:
        start = date.today() - timedelta(days=days)
        result = await self._session.execute(
            select(func.count(NewsArticle.id))
            .where(
                NewsArticle.symbol == symbol,
                NewsArticle.published_at >= start,
            )
        )
        return result.scalar() or 0

    def _compute_max_drawdown(
        self, prices: list[dict[str, Any]], name: str,
    ) -> dict[str, float | None]:
        if len(prices) < 2:
            return {f"max_drawdown_{name}": None}
        running_max = prices[0]["close"]
        max_dd = 0.0
        for p in prices:
            if p["close"] > running_max:
                running_max = p["close"]
            dd = (p["close"] - running_max) / running_max
            if dd < max_dd:
                max_dd = dd
        return {f"max_drawdown_{name}": round(max_dd * 100, 4)}

    def _compute_volatility(
        self, prices: list[dict[str, Any]], name: str,
    ) -> dict[str, float | None]:
        if len(prices) < 3:
            return {f"volatility_{name}": None}
        returns = []
        for i in range(1, len(prices)):
            r = (prices[i]["close"] - prices[i - 1]["close"]) / prices[i - 1]["close"]
            returns.append(r)
        if not returns:
            return {f"volatility_{name}": None}
        mean_r = sum(returns) / len(returns)
        variance = sum((r - mean_r) ** 2 for r in returns) / len(returns)
        daily_vol = math.sqrt(variance)
        ann_vol = daily_vol * math.sqrt(252)
        return {f"volatility_{name}": round(ann_vol * 100, 4)}

    def _compute_liquidity(self, prices: list[dict[str, Any]]) -> dict[str, Any]:
        if not prices:
            return {"avg_daily_volume_20d": None, "avg_dollar_volume_20d": None, "liquidity_score": None}
        volumes = [p["volume"] for p in prices]
        closes = [p["close"] for p in prices]
        avg_vol = int(sum(volumes) / len(volumes))
        avg_dollar_vol = sum(closes[i] * volumes[i] for i in range(len(prices))) / len(prices)
        adv_millions = avg_dollar_vol / 1_000_000
        if adv_millions > 1000:
            score = 95
        elif adv_millions > 100:
            score = 80
        elif adv_millions > 10:
            score = 60
        elif adv_millions > 1:
            score = 40
        else:
            score = 20
        return {
            "avg_daily_volume_20d": avg_vol,
            "avg_dollar_volume_20d": round(avg_dollar_vol, 2),
            "liquidity_score": score,
        }

    def _compute_gap_risk(self, prices: list[dict[str, Any]]) -> dict[str, Any]:
        if len(prices) < 10:
            return {"gap_frequency_20d": None, "avg_gap_pct": None, "max_gap_pct": None}
        gaps: list[float] = []
        for i in range(1, min(len(prices), GAP_WINDOW + 1)):
            prev_close = prices[i - 1]["close"]
            if prev_close > 0:
                gap = (prices[i]["open"] - prev_close) / prev_close * 100
                gaps.append(gap)
        if not gaps:
            return {"gap_frequency_20d": 0.0, "avg_gap_pct": 0.0, "max_gap_pct": 0.0}
        significant = sum(1 for g in gaps if abs(g) > 1.0)
        frequency = significant / len(gaps) * 100
        avg_gap = sum(abs(g) for g in gaps) / len(gaps)
        max_gap = max(abs(g) for g in gaps)
        return {
            "gap_frequency_20d": round(frequency, 4),
            "avg_gap_pct": round(avg_gap, 4),
            "max_gap_pct": round(max_gap, 4),
        }

    def _compute_event_risk(self, news_count: int) -> dict[str, Any]:
        if news_count > 100:
            score = 70
        elif news_count > 50:
            score = 55
        elif news_count > 20:
            score = 40
        elif news_count > 5:
            score = 25
        else:
            score = 10
        return {"event_risk_score": score, "news_count_30d": news_count}

    def _compute_composite_score(
        self, dd_1y: float | None, vol_252d: float | None,
        liquidity_score: float | None, gap_freq: float | None,
        event_score: float | None,
    ) -> dict[str, Any]:
        dd_score = 50.0
        if dd_1y is not None:
            ad = abs(dd_1y)
            if ad > 50:
                dd_score = 90
            elif ad > 30:
                dd_score = 75
            elif ad > 15:
                dd_score = 55
            elif ad > 5:
                dd_score = 35
            else:
                dd_score = 15

        vol_score = 50.0
        if vol_252d is not None:
            if vol_252d > 80:
                vol_score = 90
            elif vol_252d > 50:
                vol_score = 70
            elif vol_252d > 30:
                vol_score = 50
            elif vol_252d > 15:
                vol_score = 30
            else:
                vol_score = 15

        liq_score = liquidity_score if liquidity_score is not None else 50.0
        liq_risk = 100 - liq_score

        gap_score = 50.0
        if gap_freq is not None:
            if gap_freq > 20:
                gap_score = 80
            elif gap_freq > 10:
                gap_score = 60
            elif gap_freq > 5:
                gap_score = 40
            elif gap_freq > 2:
                gap_score = 25
            else:
                gap_score = 15

        evt_score = event_score if event_score is not None else 30.0

        composite = (
            dd_score * 0.20 +
            vol_score * 0.25 +
            liq_risk * 0.15 +
            gap_score * 0.15 +
            evt_score * 0.10 +
            50 * 0.15
        )

        if composite >= 80:
            rating = "extreme"
        elif composite >= 60:
            rating = "high"
        elif composite >= 40:
            rating = "medium"
        elif composite >= 20:
            rating = "low"
        else:
            rating = "very_low"

        return {
            "composite_risk_score": round(composite, 2),
            "risk_rating": rating,
        }

    async def compute_risk_metrics(
        self, symbol: str, as_of_date: date | None = None,
    ) -> dict[str, Any]:
        if as_of_date is None:
            as_of_date = date.today()

        lookback = max(DRAWDOWN_PERIODS["1y"], VOLATILITY_WINDOWS["252d"], GAP_WINDOW) + 10
        start = as_of_date - timedelta(days=lookback)
        prices = await self._get_prices(symbol, start, as_of_date)

        if len(prices) < 10:
            return {"symbol": symbol, "as_of_date": as_of_date.isoformat(), "error": "Insufficient price data"}

        result: dict[str, Any] = {"symbol": symbol, "as_of_date": as_of_date.isoformat()}

        for period_name, days in DRAWDOWN_PERIODS.items():
            period_prices = prices[-min(days, len(prices)):]
            result.update(self._compute_max_drawdown(period_prices, period_name))

        ytd_start = date(as_of_date.year, 1, 1)
        ytd_prices = [p for p in prices if p["trade_date"] >= ytd_start]
        result.update(self._compute_max_drawdown(ytd_prices, "ytd"))

        for win_name, days in VOLATILITY_WINDOWS.items():
            win_prices = prices[-min(days * 2, len(prices)):]
            result.update(self._compute_volatility(win_prices, win_name))

        liq_prices = prices[-min(LIQUIDITY_WINDOW, len(prices)):]
        result.update(self._compute_liquidity(liq_prices))

        result.update(self._compute_gap_risk(prices))

        news_count = await self._get_news_count(symbol)
        result.update(self._compute_event_risk(news_count))

        comp = self._compute_composite_score(
            dd_1y=result.get("max_drawdown_1y"),
            vol_252d=result.get("volatility_252d"),
            liquidity_score=result.get("liquidity_score"),
            gap_freq=result.get("gap_frequency_20d"),
            event_score=result.get("event_risk_score"),
        )
        result.update(comp)

        return result

    async def compute_and_store(
        self, symbol: str, as_of_date: date | None = None,
    ) -> dict[str, Any]:
        existing = await self._session.execute(
            select(RiskMetrics).where(
                RiskMetrics.symbol == symbol,
                RiskMetrics.as_of_date == (as_of_date or date.today()),
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError(f"Risk metrics already exist for {symbol} on {as_of_date or date.today()}")

        metrics = await self.compute_risk_metrics(symbol, as_of_date)
        if "error" in metrics:
            return metrics

        rec = await self._risk_repo.create(
            symbol=symbol, as_of_date=date.fromisoformat(metrics["as_of_date"]),
            max_drawdown_1m=metrics.get("max_drawdown_1m"),
            max_drawdown_3m=metrics.get("max_drawdown_3m"),
            max_drawdown_6m=metrics.get("max_drawdown_6m"),
            max_drawdown_1y=metrics.get("max_drawdown_1y"),
            max_drawdown_ytd=metrics.get("max_drawdown_ytd"),
            volatility_20d=metrics.get("volatility_20d"),
            volatility_60d=metrics.get("volatility_60d"),
            volatility_252d=metrics.get("volatility_252d"),
            avg_daily_volume_20d=metrics.get("avg_daily_volume_20d"),
            avg_dollar_volume_20d=metrics.get("avg_dollar_volume_20d"),
            liquidity_score=metrics.get("liquidity_score"),
            gap_frequency_20d=metrics.get("gap_frequency_20d"),
            avg_gap_pct=metrics.get("avg_gap_pct"),
            max_gap_pct=metrics.get("max_gap_pct"),
            event_risk_score=metrics.get("event_risk_score"),
            news_count_30d=metrics.get("news_count_30d"),
            composite_risk_score=metrics.get("composite_risk_score"),
            risk_rating=metrics.get("risk_rating"),
        )
        metrics["id"] = rec.id
        return metrics

    async def compute_portfolio_risk(
        self, portfolio_id: str, holdings: dict[str, dict[str, Any]],
        as_of_date: date | None = None, store: bool = False,
    ) -> dict[str, Any]:
        if as_of_date is None:
            as_of_date = date.today()

        symbols = list(holdings.keys())
        if not symbols:
            return {"portfolio_id": portfolio_id, "error": "No holdings provided"}

        total_value = sum(h.get("value", 0) or h.get("weight", 0) * 1_000_000 for h in holdings.values())
        weights = {}
        if "weight" in next(iter(holdings.values())):
            total_w = sum(h["weight"] for h in holdings.values())
            weights = {s: h["weight"] / total_w for s, h in holdings.items()}
        else:
            weights = {s: (h.get("value", 0) or 1) / max(total_value, 1) for s, h in holdings.items()}

        lookback = as_of_date - timedelta(days=400)
        all_returns: dict[str, list[float]] = {}
        symbol_metrics: dict[str, dict] = {}
        for sym in symbols:
            metrics = await self.compute_risk_metrics(sym, as_of_date)
            if "error" in metrics:
                continue
            symbol_metrics[sym] = metrics
            prices = await self._get_prices(sym, lookback, as_of_date)
            rets = []
            for i in range(1, len(prices)):
                r = (prices[i]["close"] - prices[i - 1]["close"]) / prices[i - 1]["close"]
                rets.append(r)
            all_returns[sym] = rets

        valid_symbols = [s for s in symbols if s in symbol_metrics]
        if not valid_symbols:
            return {"portfolio_id": portfolio_id, "error": "No valid symbols with data"}

        valid_weights = {s: weights[s] for s in valid_symbols}
        w_sum = sum(valid_weights.values())
        valid_weights = {s: w / w_sum for s, w in valid_weights.items()}
        weight_list = [valid_weights[s] for s in valid_symbols]

        vols = [symbol_metrics[s].get("volatility_252d", 20) for s in valid_symbols]
        for i in range(len(vols)):
            if vols[i] is None or vols[i] <= 0:
                vols[i] = 20

        min_len = min(len(all_returns[s]) for s in valid_symbols)
        aligned_rets = {s: all_returns[s][-min_len:] for s in valid_symbols}
        n = len(aligned_rets[valid_symbols[0]])
        corr_matrix = self._compute_correlation_matrix(aligned_rets, valid_symbols)
        weighted_vol = sum(weight_list[i] * (vols[i] / 100) for i in range(len(valid_symbols)))
        port_variance = 0.0
        for i in range(len(valid_symbols)):
            for j in range(len(valid_symbols)):
                si = vols[i] / 100
                sj = vols[j] / 100
                port_variance += weight_list[i] * weight_list[j] * si * sj * corr_matrix[i][j]
        port_vol = math.sqrt(port_variance) if port_variance > 0 else weighted_vol
        port_mean = sum(
            weight_list[i] * (sum(aligned_rets[valid_symbols[i]]) / n)
            for i in range(len(valid_symbols))
        )

        var_95 = self._compute_var(port_mean, port_vol, 0.95, total_value)
        var_99 = self._compute_var(port_mean, port_vol, 0.99, total_value)
        es_95 = self._compute_expected_shortfall(port_vol, 0.95, total_value)
        conc = sum(w ** 2 for w in weight_list)
        div_ratio = weighted_vol / max(port_vol, 0.0001)
        avg_corr = self._average_correlation(corr_matrix)

        weighted_dd = sum(
            weight_list[i] * (symbol_metrics[valid_symbols[i]].get("max_drawdown_1y") or 0)
            for i in range(len(valid_symbols))
        )
        weighted_gap = sum(
            weight_list[i] * (symbol_metrics[valid_symbols[i]].get("gap_frequency_20d") or 0)
            for i in range(len(valid_symbols))
        )

        dd_score = min(100, max(0, abs(weighted_dd) * 1.5))
        vol_score = min(100, port_vol * 100 * 1.2)
        gap_score = min(100, weighted_gap * 2)
        conc_score = min(100, conc * 100)
        composite = dd_score * 0.25 + vol_score * 0.30 + gap_score * 0.15 + conc_score * 0.15 + 50 * 0.15

        if composite >= 80:
            rating = "extreme"
        elif composite >= 60:
            rating = "high"
        elif composite >= 40:
            rating = "medium"
        elif composite >= 20:
            rating = "low"
        else:
            rating = "very_low"

        result = {
            "portfolio_id": portfolio_id,
            "as_of_date": as_of_date.isoformat(),
            "num_positions": len(valid_symbols),
            "total_value": total_value,
            "weighted_volatility": round(weighted_vol * 100, 4),
            "portfolio_volatility": round(port_vol * 100, 4),
            "portfolio_var_95": round(var_95, 2),
            "portfolio_var_99": round(var_99, 2),
            "expected_shortfall_95": round(es_95, 2),
            "diversification_ratio": round(div_ratio, 4),
            "concentration_risk": round(conc, 4),
            "average_correlation": round(avg_corr, 4),
            "weighted_drawdown": round(weighted_dd, 4),
            "weighted_gap_risk": round(weighted_gap, 4),
            "composite_risk_score": round(composite, 2),
            "risk_rating": rating,
            "holdings": [
                {
                    "symbol": s, "weight": round(valid_weights[s], 4),
                    "volatility": symbol_metrics[s].get("volatility_252d"),
                    "max_drawdown_1y": symbol_metrics[s].get("max_drawdown_1y"),
                    "liquidity_score": symbol_metrics[s].get("liquidity_score"),
                    "risk_rating": symbol_metrics[s].get("risk_rating"),
                }
                for s in valid_symbols
            ],
        }

        if store:
            rec = await self._portfolio_repo.create(
                portfolio_id=portfolio_id, as_of_date=as_of_date,
                num_positions=result["num_positions"],
                total_value=result["total_value"],
                weighted_volatility=result["weighted_volatility"],
                portfolio_var_95=result["portfolio_var_95"],
                portfolio_var_99=result["portfolio_var_99"],
                expected_shortfall_95=result["expected_shortfall_95"],
                diversification_ratio=result["diversification_ratio"],
                concentration_risk=result["concentration_risk"],
                weighted_drawdown=result["weighted_drawdown"],
                weighted_gap_risk=result["weighted_gap_risk"],
                composite_risk_score=result["composite_risk_score"],
                risk_rating=result["risk_rating"],
            )
            result["id"] = rec.id

        return result

    def _compute_correlation_matrix(
        self, returns: dict[str, list[float]], symbols: list[str],
    ) -> list[list[float]]:
        n = len(symbols)
        matrix = [[1.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                r = self._pearson_correlation(returns[symbols[i]], returns[symbols[j]])
                matrix[i][j] = r
                matrix[j][i] = r
        return matrix

    def _pearson_correlation(self, a: list[float], b: list[float]) -> float:
        n = min(len(a), len(b))
        if n < 3:
            return 0.0
        a = a[:n]
        b = b[:n]
        ma = sum(a) / n
        mb = sum(b) / n
        num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
        den = math.sqrt(sum((a[i] - ma) ** 2 for i in range(n))) * math.sqrt(sum((b[i] - mb) ** 2 for i in range(n)))
        return num / den if den != 0 else 0.0

    def _average_correlation(self, matrix: list[list[float]]) -> float:
        n = len(matrix)
        if n < 2:
            return 0.0
        total = 0.0
        count = 0
        for i in range(n):
            for j in range(i + 1, n):
                total += matrix[i][j]
                count += 1
        return total / count if count > 0 else 0.0

    def _compute_var(
        self, mean: float, vol: float, confidence: float, portfolio_value: float = 1.0,
    ) -> float:
        z = {0.95: 1.645, 0.99: 2.326}.get(confidence, 1.645)
        var_pct = -(mean - z * vol)
        return max(0, var_pct * portfolio_value)

    def _compute_expected_shortfall(
        self, vol: float, confidence: float, portfolio_value: float = 1.0,
    ) -> float:
        z = {0.95: 1.645, 0.99: 2.326}.get(confidence, 1.645)
        pdf_z = (1 / math.sqrt(2 * math.pi)) * math.exp(-z * z / 2)
        es_pct = vol * pdf_z / (1 - confidence)
        return es_pct * portfolio_value

    async def get_risk_metrics(
        self, symbol: str, as_of_date: date | None = None,
    ) -> RiskMetrics | None:
        stmt = select(RiskMetrics).where(RiskMetrics.symbol == symbol)
        if as_of_date:
            stmt = stmt.where(RiskMetrics.as_of_date == as_of_date)
        stmt = stmt.order_by(RiskMetrics.as_of_date.desc()).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_historical_risk(
        self, symbol: str, start_date: date | None = None,
        end_date: date | None = None, skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[RiskMetrics], int]:
        stmt = select(RiskMetrics).where(RiskMetrics.symbol == symbol)
        if start_date:
            stmt = stmt.where(RiskMetrics.as_of_date >= start_date)
        if end_date:
            stmt = stmt.where(RiskMetrics.as_of_date <= end_date)
        count_result = await self._session.execute(stmt)
        total = len(count_result.scalars().all())
        stmt = stmt.order_by(RiskMetrics.as_of_date.desc()).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    async def get_portfolio_risk(
        self, portfolio_id: str, as_of_date: date | None = None,
    ) -> PortfolioRisk | None:
        stmt = select(PortfolioRisk).where(PortfolioRisk.portfolio_id == portfolio_id)
        if as_of_date:
            stmt = stmt.where(PortfolioRisk.as_of_date == as_of_date)
        stmt = stmt.order_by(PortfolioRisk.as_of_date.desc()).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_portfolio_history(
        self, portfolio_id: str, skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[PortfolioRisk], int]:
        stmt = select(PortfolioRisk).where(PortfolioRisk.portfolio_id == portfolio_id)
        count_result = await self._session.execute(stmt)
        total = len(count_result.scalars().all())
        stmt = stmt.order_by(PortfolioRisk.as_of_date.desc()).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    async def delete_risk_metrics(self, risk_id: int) -> bool:
        return await self._risk_repo.delete(risk_id)

    async def delete_portfolio_risk(self, pr_id: int) -> bool:
        return await self._portfolio_repo.delete(pr_id)
