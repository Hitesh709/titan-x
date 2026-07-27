import json
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.ai_ranking_v2 import AIRankingV2, RankingModelWeight
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice
from titan_x.models.regime import MarketRegime
from titan_x.models.ranking import StockRanking

logger = structlog.get_logger(__name__)

DEFAULT_WEIGHTS = {
    "technical": 0.25,
    "fundamental": 0.25,
    "sentiment": 0.25,
    "momentum": 0.25,
}

REGIME_WEIGHT_ADJUSTMENTS = {
    "bullish": {"technical": 0.30, "fundamental": 0.20, "sentiment": 0.25, "momentum": 0.25},
    "bearish": {"technical": 0.20, "fundamental": 0.30, "sentiment": 0.30, "momentum": 0.20},
    "volatile": {"technical": 0.15, "fundamental": 0.25, "sentiment": 0.35, "momentum": 0.25},
    "sideways": {"technical": 0.35, "fundamental": 0.25, "sentiment": 0.15, "momentum": 0.25},
}


class AIRankingServiceV2:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.ranking_repo = BaseRepository(session, AIRankingV2)
        self.weight_repo = BaseRepository(session, RankingModelWeight)

    async def rank_all(
        self, as_of_date: date | None = None,
    ) -> list[AIRankingV2]:
        if as_of_date is None:
            as_of_date = date.today()

        result = await self.session.execute(
            select(Company).where(Company.status == "active")
        )
        companies = list(result.scalars().all())
        if not companies:
            return []

        symbols = [c.symbol for c in companies]
        company_map = {c.symbol: c for c in companies}

        regime = await self._get_market_regime(as_of_date)
        weights = await self._compute_dynamic_weights(regime, as_of_date)

        scores = await self._compute_scores(symbols, as_of_date, weights)
        scores.sort(key=lambda x: x["weighted_ai_score"], reverse=True)

        rankings = []
        for idx, entry in enumerate(scores):
            rank = idx + 1
            tier = self._assign_tier(rank)
            is_best = rank == 1
            regime_name = regime.regime_summary or regime.trend_regime if regime else "unknown"

            historical = await self._get_historical_performance(entry["symbol"], as_of_date)

            ranking = AIRankingV2(
                as_of_date=as_of_date, rank=rank, symbol=entry["symbol"],
                company_name=company_map[entry["symbol"]].company_name if entry["symbol"] in company_map else None,
                sector=company_map[entry["symbol"]].sector if entry["symbol"] in company_map else None,
                weighted_ai_score=entry["weighted_ai_score"],
                base_score=entry["base_score"],
                technical_score=entry.get("technical_score"),
                fundamental_score=entry.get("fundamental_score"),
                sentiment_score=entry.get("sentiment_score"),
                momentum_score=entry.get("momentum_score"),
                dynamic_weight_technical=weights.get("technical"),
                dynamic_weight_fundamental=weights.get("fundamental"),
                dynamic_weight_sentiment=weights.get("sentiment"),
                dynamic_weight_momentum=weights.get("momentum"),
                model_confidence=entry["model_confidence"],
                market_regime=regime_name,
                regime_confidence=regime.confidence if regime else None,
                historical_success_rate=historical.get("success_rate"),
                historical_avg_return=historical.get("avg_return"),
                historical_sharpe=historical.get("sharpe"),
                tier=tier,
                is_best_opportunity=is_best,
                explanation_json=json.dumps(self._build_explanation(entry, weights, regime_name, rank, tier)),
            )
            self.session.add(ranking)
            rankings.append(ranking)

        await self.session.flush()

        await self._store_weights("ensemble_v2", as_of_date, weights, regime, as_of_date)

        for r in rankings:
            await self.session.refresh(r)
        return rankings

    async def get_ranking(
        self, symbol: str, as_of_date: date | None = None,
    ) -> AIRankingV2 | None:
        stmt = select(AIRankingV2).where(AIRankingV2.symbol == symbol.upper())
        if as_of_date:
            stmt = stmt.where(AIRankingV2.as_of_date == as_of_date)
        stmt = stmt.order_by(desc(AIRankingV2.as_of_date)).limit(1)
        r = await self.session.execute(stmt)
        return r.scalar_one_or_none()

    async def get_top(self, limit: int = 20, as_of_date: date | None = None) -> list[AIRankingV2]:
        stmt = select(AIRankingV2)
        if as_of_date:
            stmt = stmt.where(AIRankingV2.as_of_date == as_of_date)
        stmt = stmt.order_by(AIRankingV2.rank.asc()).limit(limit)
        r = await self.session.execute(stmt)
        return list(r.scalars().all())

    async def get_weights(self, model_name: str = "ensemble_v2") -> list[RankingModelWeight]:
        r = await self.session.execute(
            select(RankingModelWeight).where(
                RankingModelWeight.model_name == model_name,
            ).order_by(desc(RankingModelWeight.as_of_date)).limit(30)
        )
        return list(r.scalars().all())

    async def _get_market_regime(self, as_of_date: date) -> MarketRegime | None:
        r = await self.session.execute(
            select(MarketRegime).where(MarketRegime.symbol == "MARKET", MarketRegime.as_of_date == as_of_date)
        )
        regime = r.scalar_one_or_none()
        if regime:
            return regime
        r = await self.session.execute(
            select(MarketRegime).where(MarketRegime.symbol == "MARKET").order_by(desc(MarketRegime.as_of_date)).limit(1)
        )
        return r.scalar_one_or_none()

    async def _compute_dynamic_weights(
        self, regime: MarketRegime | None, as_of_date: date,
    ) -> dict[str, float]:
        if regime and regime.trend_regime:
            adj = REGIME_WEIGHT_ADJUSTMENTS.get(regime.trend_regime.lower())
            if adj:
                return adj
        return dict(DEFAULT_WEIGHTS)

    async def _compute_scores(
        self, symbols: list[str], as_of_date: date, weights: dict[str, float],
    ) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(StockRanking).where(
                StockRanking.as_of_date == as_of_date,
                StockRanking.symbol.in_(symbols),
            )
        )
        existing_rankings = {r.symbol: r for r in result.scalars().all()}

        lookback = as_of_date - timedelta(days=60)
        price_result = await self.session.execute(
            select(DailyPrice).where(
                DailyPrice.symbol.in_(symbols),
                DailyPrice.trade_date >= lookback,
                DailyPrice.trade_date <= as_of_date,
            ).order_by(DailyPrice.symbol, DailyPrice.trade_date)
        )
        prices = list(price_result.scalars().all())
        price_map = defaultdict(list)
        for p in prices:
            price_map[p.symbol].append(p)

        scored = []
        for sym in symbols:
            existing = existing_rankings.get(sym)
            sym_prices = price_map.get(sym, [])
            base = existing.composite_score if existing else 50.0

            tech_score = existing.momentum_score if existing else self._score_technical(sym_prices)
            fund_score = existing.financial_health_score if existing else 50.0
            sent_score = existing.corporate_score if existing else 50.0
            mom_score = existing.momentum_score if existing else 50.0

            model_conf = self._compute_model_confidence(tech_score, fund_score, sent_score, mom_score)

            weighted = (
                weights.get("technical", 0.25) * (tech_score or 50) +
                weights.get("fundamental", 0.25) * (fund_score or 50) +
                weights.get("sentiment", 0.25) * (sent_score or 50) +
                weights.get("momentum", 0.25) * (mom_score or 50)
            )

            scored.append({
                "symbol": sym,
                "weighted_ai_score": round(weighted, 1),
                "base_score": round(base, 1),
                "technical_score": round(tech_score, 1) if tech_score else None,
                "fundamental_score": round(fund_score, 1) if fund_score else None,
                "sentiment_score": round(sent_score, 1) if sent_score else None,
                "momentum_score": round(mom_score, 1) if mom_score else None,
                "model_confidence": round(model_conf, 4),
            })
        return scored

    async def _get_historical_performance(self, symbol: str, as_of_date: date) -> dict[str, float | None]:
        start = as_of_date - timedelta(days=365)
        r = await self.session.execute(
            select(AIRankingV2).where(
                AIRankingV2.symbol == symbol,
                AIRankingV2.as_of_date >= start,
            ).order_by(AIRankingV2.as_of_date)
        )
        history = list(r.scalars().all())
        if len(history) < 2:
            return {"success_rate": None, "avg_return": None, "sharpe": None}

        correct = 0
        returns = []
        for i in range(len(history) - 1):
            if history[i].tier in ("top_5", "top_10") and history[i + 1].tier in ("top_5", "top_10"):
                correct += 1
            if history[i].weighted_ai_score > 60:
                returns.append(history[i].weighted_ai_score - 50)

        success_rate = correct / max(len(history) - 1, 1) * 100
        avg_ret = sum(returns) / len(returns) if returns else None
        sharpe = (avg_ret / max(p := sum((r - avg_ret) ** 2 for r in returns) / len(returns) if avg_ret and len(returns) > 1 else 1, 0.01)) if avg_ret else None
        return {
            "success_rate": round(success_rate, 2),
            "avg_return": round(avg_ret, 4) if avg_ret else None,
            "sharpe": round(sharpe, 4) if sharpe else None,
        }

    def _score_technical(self, prices: list) -> float | None:
        if len(prices) < 5:
            return None
        closes = [p.close for p in prices]
        ret_20d = (closes[-1] - closes[-min(21, len(closes))]) / closes[-min(21, len(closes))] if len(closes) >= 2 else 0
        score = 50 + ret_20d * 150
        return max(0, min(100, round(score, 1)))

    def _compute_model_confidence(self, *scores: float | None) -> float:
        valid = [s for s in scores if s is not None]
        if not valid:
            return 0.5
        variance = sum((s - 50) ** 2 for s in valid) / len(valid)
        confidence = min(1.0, max(0.1, variance / 2500))
        return round(confidence, 4)

    async def _store_weights(
        self, model_name: str, as_of_date: date,
        weights: dict[str, float], regime: MarketRegime | None,
        confidence_date: date,
    ) -> None:
        weight = RankingModelWeight(
            model_name=model_name, as_of_date=as_of_date,
            weight_technical=weights.get("technical", 0.25),
            weight_fundamental=weights.get("fundamental", 0.25),
            weight_sentiment=weights.get("sentiment", 0.25),
            weight_momentum=weights.get("momentum", 0.25),
            market_regime=regime.regime_summary if regime else None,
            model_confidence=0.85,
        )
        self.session.add(weight)

    def _assign_tier(self, rank: int) -> str:
        if rank <= 5:
            return "top_5"
        if rank <= 10:
            return "top_10"
        if rank <= 25:
            return "top_25"
        if rank <= 50:
            return "top_50"
        if rank <= 100:
            return "top_100"
        return "unranked"

    def _build_explanation(
        self, entry: dict, weights: dict, regime: str, rank: int, tier: str,
    ) -> dict:
        return {
            "symbol": entry["symbol"],
            "rank": rank,
            "tier": tier,
            "weighted_ai_score": entry["weighted_ai_score"],
            "base_score": entry["base_score"],
            "market_regime": regime,
            "model_confidence": entry["model_confidence"],
            "weights": weights,
            "components": {
                "technical": entry.get("technical_score"),
                "fundamental": entry.get("fundamental_score"),
                "sentiment": entry.get("sentiment_score"),
                "momentum": entry.get("momentum_score"),
            },
            "summary": f"{entry['symbol']} ranked #{rank} ({tier}) with AI score {entry['weighted_ai_score']} "
                       f"in {regime} regime (confidence: {entry['model_confidence']:.2f})",
        }
