import json
import math
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import and_, case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from titan_x.db.repository import BaseRepository
from titan_x.models.corporate_tracking import (
    CorporateAnalysis,
    InsiderTrade,
    PromoterTransaction,
    ShareholdingPattern,
)

logger = structlog.get_logger(__name__)

PROMOTER_LOOKBACK_DAYS = 365
INSIDER_LOOKBACK_DAYS = 180
SHAREHOLDING_LOOKBACK_QUARTERS = 4


class CorporateTrackingService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._promoter_repo = BaseRepository(session, PromoterTransaction)
        self._insider_repo = BaseRepository(session, InsiderTrade)
        self._shareholding_repo = BaseRepository(session, ShareholdingPattern)
        self._analysis_repo = BaseRepository(session, CorporateAnalysis)

    # ------------------------------------------------------------------
    # Promoter Transactions
    # ------------------------------------------------------------------

    async def create_promoter_transaction(self, **kwargs: Any) -> PromoterTransaction:
        if "value" not in kwargs or kwargs.get("value") is None:
            qty = kwargs.get("quantity", 0)
            price = kwargs.get("price", 0)
            kwargs["value"] = qty * price
        return await self._promoter_repo.create(**kwargs)

    async def get_promoter_transaction(self, transaction_id: int) -> PromoterTransaction | None:
        return await self._promoter_repo.get(transaction_id)

    async def list_promoter_transactions(
        self,
        company_id: int | None = None,
        transaction_type: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[PromoterTransaction], int]:
        query = select(PromoterTransaction)
        count_query = select(func.count()).select_from(PromoterTransaction)
        if company_id is not None:
            query = query.where(PromoterTransaction.company_id == company_id)
            count_query = count_query.where(PromoterTransaction.company_id == company_id)
        if transaction_type is not None:
            query = query.where(PromoterTransaction.transaction_type == transaction_type)
            count_query = count_query.where(PromoterTransaction.transaction_type == transaction_type)
        if from_date is not None:
            query = query.where(PromoterTransaction.transaction_date >= from_date)
            count_query = count_query.where(PromoterTransaction.transaction_date >= from_date)
        if to_date is not None:
            query = query.where(PromoterTransaction.transaction_date <= to_date)
            count_query = count_query.where(PromoterTransaction.transaction_date <= to_date)
        total = (await self._session.execute(count_query)).scalar() or 0
        query = query.order_by(PromoterTransaction.transaction_date.desc()).offset(skip).limit(limit)
        rows = (await self._session.execute(query)).scalars().all()
        return rows, total

    async def update_promoter_transaction(self, transaction_id: int, **kwargs: Any) -> PromoterTransaction | None:
        if "value" in kwargs and kwargs["value"] is None:
            kwargs.pop("value")
        if "value" not in kwargs and "quantity" in kwargs and "price" in kwargs:
            kwargs["value"] = kwargs["quantity"] * kwargs["price"]
        return await self._promoter_repo.update(transaction_id, **kwargs)

    async def delete_promoter_transaction(self, transaction_id: int) -> bool:
        return await self._promoter_repo.delete(transaction_id)

    # ------------------------------------------------------------------
    # Insider Trades
    # ------------------------------------------------------------------

    async def create_insider_trade(self, **kwargs: Any) -> InsiderTrade:
        if "value" not in kwargs or kwargs.get("value") is None:
            qty = kwargs.get("quantity", 0)
            price = kwargs.get("price", 0)
            kwargs["value"] = qty * price
        return await self._insider_repo.create(**kwargs)

    async def get_insider_trade(self, trade_id: int) -> InsiderTrade | None:
        return await self._insider_repo.get(trade_id)

    async def list_insider_trades(
        self,
        company_id: int | None = None,
        transaction_type: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[InsiderTrade], int]:
        query = select(InsiderTrade)
        count_query = select(func.count()).select_from(InsiderTrade)
        if company_id is not None:
            query = query.where(InsiderTrade.company_id == company_id)
            count_query = count_query.where(InsiderTrade.company_id == company_id)
        if transaction_type is not None:
            query = query.where(InsiderTrade.transaction_type == transaction_type)
            count_query = count_query.where(InsiderTrade.transaction_type == transaction_type)
        if from_date is not None:
            query = query.where(InsiderTrade.transaction_date >= from_date)
            count_query = count_query.where(InsiderTrade.transaction_date >= from_date)
        if to_date is not None:
            query = query.where(InsiderTrade.transaction_date <= to_date)
            count_query = count_query.where(InsiderTrade.transaction_date <= to_date)
        total = (await self._session.execute(count_query)).scalar() or 0
        query = query.order_by(InsiderTrade.transaction_date.desc()).offset(skip).limit(limit)
        rows = (await self._session.execute(query)).scalars().all()
        return rows, total

    async def update_insider_trade(self, trade_id: int, **kwargs: Any) -> InsiderTrade | None:
        if "value" in kwargs and kwargs["value"] is None:
            kwargs.pop("value")
        if "value" not in kwargs and "quantity" in kwargs and "price" in kwargs:
            kwargs["value"] = kwargs["quantity"] * kwargs["price"]
        return await self._insider_repo.update(trade_id, **kwargs)

    async def delete_insider_trade(self, trade_id: int) -> bool:
        return await self._insider_repo.delete(trade_id)

    # ------------------------------------------------------------------
    # Shareholding Patterns
    # ------------------------------------------------------------------

    async def create_shareholding_pattern(self, **kwargs: Any) -> ShareholdingPattern:
        return await self._shareholding_repo.create(**kwargs)

    async def get_shareholding_pattern(self, pattern_id: int) -> ShareholdingPattern | None:
        return await self._shareholding_repo.get(pattern_id)

    async def list_shareholding_patterns(
        self,
        company_id: int | None = None,
        category: str | None = None,
        year: int | None = None,
        quarter: int | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[ShareholdingPattern], int]:
        query = select(ShareholdingPattern)
        count_query = select(func.count()).select_from(ShareholdingPattern)
        if company_id is not None:
            query = query.where(ShareholdingPattern.company_id == company_id)
            count_query = count_query.where(ShareholdingPattern.company_id == company_id)
        if category is not None:
            query = query.where(ShareholdingPattern.category == category)
            count_query = count_query.where(ShareholdingPattern.category == category)
        if year is not None:
            query = query.where(ShareholdingPattern.year == year)
            count_query = count_query.where(ShareholdingPattern.year == year)
        if quarter is not None:
            query = query.where(ShareholdingPattern.quarter == quarter)
            count_query = count_query.where(ShareholdingPattern.quarter == quarter)
        total = (await self._session.execute(count_query)).scalar() or 0
        query = query.order_by(ShareholdingPattern.year.desc(), ShareholdingPattern.quarter.desc()).offset(skip).limit(limit)
        rows = (await self._session.execute(query)).scalars().all()
        return rows, total

    async def update_shareholding_pattern(self, pattern_id: int, **kwargs: Any) -> ShareholdingPattern | None:
        return await self._shareholding_repo.update(pattern_id, **kwargs)

    async def delete_shareholding_pattern(self, pattern_id: int) -> bool:
        return await self._shareholding_repo.delete(pattern_id)

    # ------------------------------------------------------------------
    # AI: Promoter Activity Analysis
    # ------------------------------------------------------------------

    async def analyze_promoter_activity(self, company_id: int) -> dict[str, Any]:
        cutoff = date.today() - timedelta(days=PROMOTER_LOOKBACK_DAYS)
        result = await self._session.execute(
            select(PromoterTransaction)
            .where(
                PromoterTransaction.company_id == company_id,
                PromoterTransaction.transaction_date >= cutoff,
            )
            .order_by(PromoterTransaction.transaction_date.asc())
        )
        transactions = result.scalars().all()

        if not transactions:
            return {
                "buying_score": 50.0,
                "selling_score": 50.0,
                "net_flow": 0,
                "buy_volume": 0,
                "sell_volume": 0,
                "total_transactions": 0,
                "buy_count": 0,
                "sell_count": 0,
                "insights": ["No promoter transactions in the last year"],
            }

        buys = [t for t in transactions if t.transaction_type == "buy"]
        sells = [t for t in transactions if t.transaction_type == "sell"]
        buy_volume = abs(sum(t.quantity for t in buys))
        sell_volume = abs(sum(t.quantity for t in sells))
        buy_value = sum(t.value for t in buys)
        sell_value = sum(t.value for t in sells)
        net_flow = buy_volume - sell_volume

        today = date.today()
        weighted_buy_value = sum(
            t.value * max(0.1, 1.0 - (today - t.transaction_date).days / PROMOTER_LOOKBACK_DAYS)
            for t in buys
        )
        weighted_sell_value = sum(
            t.value * max(0.1, 1.0 - (today - t.transaction_date).days / PROMOTER_LOOKBACK_DAYS)
            for t in sells
        )

        total_weighted = weighted_buy_value + weighted_sell_value
        if total_weighted == 0:
            buying_score = 50.0
            selling_score = 50.0
        else:
            raw_buy_score = (weighted_buy_value / total_weighted) * 100
            buying_score = min(100, max(0, raw_buy_score * 1.5))
            raw_sell_score = (weighted_sell_value / total_weighted) * 100
            selling_score = min(100, max(0, raw_sell_score * 1.5))

        unique_buy_promoters = len(set(t.promoter_name for t in buys))
        unique_sell_promoters = len(set(t.promoter_name for t in sells))
        cluster_buying = unique_buy_promoters >= 2 and len(buys) >= 3
        concentrated_selling = unique_sell_promoters <= 1 and len(sells) >= 2

        avg_buy_price = sum(t.price * t.quantity for t in buys) / buy_volume if buy_volume > 0 else 0
        avg_sell_price = sum(t.price * t.quantity for t in sells) / sell_volume if sell_volume > 0 else 0

        insights = []
        if net_flow > 0:
            insights.append(f"Net promoter buying of {net_flow:,} shares over the last year")
        elif net_flow < 0:
            insights.append(f"Net promoter selling of {abs(net_flow):,} shares over the last year")
        else:
            insights.append("Promoter activity is balanced between buying and selling")

        if buy_volume > 3 * sell_volume and sell_volume > 0:
            insights.append("Strong promoter buying dominance — bullish signal")
        elif sell_volume > 3 * buy_volume and buy_volume > 0:
            insights.append("Heavy promoter selling — caution warranted")

        if cluster_buying:
            insights.append(f"Cluster buying detected — {unique_buy_promoters} distinct promoters accumulating")
        if concentrated_selling:
            insights.append("Concentrated selling by a single promoter — monitor closely")

        if avg_buy_price > 0 and avg_sell_price > 0 and avg_sell_price > avg_buy_price:
            insights.append("Promoters are selling at higher prices than recent buys — profit-taking pattern")
        elif avg_buy_price > 0 and avg_sell_price > 0 and avg_buy_price > avg_sell_price:
            insights.append("Promoters buying at higher prices than recent sells — confidence signal")

        return {
            "buying_score": round(buying_score, 2),
            "selling_score": round(selling_score, 2),
            "net_flow": net_flow,
            "buy_volume": buy_volume,
            "sell_volume": sell_volume,
            "buy_value": round(buy_value, 2),
            "sell_value": round(sell_value, 2),
            "total_transactions": len(transactions),
            "buy_count": len(buys),
            "sell_count": len(sells),
            "unique_buy_promoters": unique_buy_promoters,
            "unique_sell_promoters": unique_sell_promoters,
            "cluster_buying": cluster_buying,
            "concentrated_selling": concentrated_selling,
            "avg_buy_price": round(avg_buy_price, 2) if avg_buy_price > 0 else None,
            "avg_sell_price": round(avg_sell_price, 2) if avg_sell_price > 0 else None,
            "insights": insights,
        }

    # ------------------------------------------------------------------
    # AI: Insider Sentiment Analysis
    # ------------------------------------------------------------------

    async def analyze_insider_sentiment(self, company_id: int) -> dict[str, Any]:
        cutoff = date.today() - timedelta(days=INSIDER_LOOKBACK_DAYS)
        result = await self._session.execute(
            select(InsiderTrade)
            .where(
                InsiderTrade.company_id == company_id,
                InsiderTrade.transaction_date >= cutoff,
            )
            .order_by(InsiderTrade.transaction_date.asc())
        )
        trades = result.scalars().all()

        if not trades:
            return {
                "sentiment_score": 50.0,
                "buy_sell_ratio": 1.0,
                "total_trades": 0,
                "insights": ["No insider trades in the last 6 months"],
            }

        buys = [t for t in trades if t.transaction_type == "buy"]
        sells = [t for t in trades if t.transaction_type == "sell"]
        buy_count = len(buys)
        sell_count = len(sells)
        buy_volume = abs(sum(t.quantity for t in buys))
        sell_volume = abs(sum(t.quantity for t in sells))

        designation_weight = {
            "promoter": 2.0,
            "director": 1.5,
            "ceo": 1.8,
            "cfo": 1.5,
            "chairman": 2.0,
            "whole-time director": 1.5,
            "independent director": 0.8,
            "key managerial personnel": 1.2,
            "employee": 0.5,
        }

        weighted_buy = sum(
            designation_weight.get(t.designation.lower().strip() if t.designation else "", 1.0)
            * t.value
            for t in buys
        )
        weighted_sell = sum(
            designation_weight.get(t.designation.lower().strip() if t.designation else "", 1.0)
            * t.value
            for t in sells
        )

        total_weighted = weighted_buy + weighted_sell
        if total_weighted == 0:
            sentiment_score = 50.0
        else:
            raw_sentiment = (weighted_buy / total_weighted) * 100
            sentiment_score = min(100, max(0, raw_sentiment * 1.3))

        buy_sell_ratio = buy_count / sell_count if sell_count > 0 else float("inf")

        unusual_groups = []
        if len(trades) >= 3:
            for i in range(len(trades) - 1):
                gap = (trades[i + 1].transaction_date - trades[i].transaction_date).days
                if gap <= 3 and trades[i].transaction_type != trades[i + 1].transaction_type:
                    unusual_groups.append((trades[i], trades[i + 1]))

        derivative_trades = [t for t in trades if t.is_derivative]

        insights = []
        if buy_sell_ratio is not None and buy_sell_ratio >= 3:
            insights.append(f"Strong insider buying with {buy_sell_ratio:.1f}:1 buy/sell ratio")
        elif buy_sell_ratio is not None and buy_sell_ratio <= 0.33 and buy_sell_ratio > 0:
            insights.append(f"Heavy insider selling with {1/buy_sell_ratio:.1f}:1 sell/buy ratio")
        elif buy_sell_ratio == 0:
            insights.append("Heavy insider selling with no insider buying")

        if weighted_buy > 2 * weighted_sell and weighted_sell > 0:
            insights.append("High-value insiders (directors/promoters) are accumulating — bullish")
        elif weighted_sell > 2 * weighted_buy and weighted_buy > 0:
            insights.append("High-value insiders reducing positions — caution")

        if unusual_groups:
            insights.append(f"Detected {len(unusual_groups)} instances of mixed buy/sell clustering")

        if derivative_trades:
            insights.append(f"{len(derivative_trades)} derivative transactions — insiders hedging or speculating")

        return {
            "sentiment_score": round(sentiment_score, 2),
            "buy_sell_ratio": round(buy_sell_ratio, 2) if buy_sell_ratio != float("inf") else None,
            "total_trades": len(trades),
            "buy_count": buy_count,
            "sell_count": sell_count,
            "buy_volume": buy_volume,
            "sell_volume": sell_volume,
            "weighted_buy_value": round(weighted_buy, 2),
            "weighted_sell_value": round(weighted_sell, 2),
            "derivative_trades": len(derivative_trades),
            "unusual_clusters": len(unusual_groups),
            "insights": insights,
        }

    # ------------------------------------------------------------------
    # AI: Shareholding Trend Analysis
    # ------------------------------------------------------------------

    async def analyze_shareholding_trends(self, company_id: int) -> dict[str, Any]:
        result = await self._session.execute(
            select(ShareholdingPattern)
            .where(ShareholdingPattern.company_id == company_id)
            .order_by(ShareholdingPattern.year.desc(), ShareholdingPattern.quarter.desc())
        )
        patterns = result.scalars().all()

        if not patterns:
            return {
                "trend_score": 50.0,
                "total_records": 0,
                "insights": ["No shareholding data available"],
            }

        categories = {}
        for p in patterns:
            categories.setdefault(p.category, []).append(p)

        trends: dict[str, Any] = {}
        for category, records in categories.items():
            records.sort(key=lambda r: (-r.year, -r.quarter))
            latest = records[0]
            prev = records[1] if len(records) > 1 else None
            change = latest.change_percentage if latest.change_percentage is not None else (
                latest.percentage - prev.percentage if prev else 0.0
            )
            qoq_changes = []
            for i in range(len(records) - 1):
                c = records[i].percentage - records[i + 1].percentage
                qoq_changes.append(c)
            avg_qoq = sum(qoq_changes) / len(qoq_changes) if qoq_changes else 0.0
            direction = "increasing" if change > 0 else ("decreasing" if change < 0 else "stable")
            trends[category] = {
                "latest_percentage": latest.percentage,
                "change": round(change, 2),
                "direction": direction,
                "avg_qoq_change": round(avg_qoq, 2),
                "records_analyzed": len(records),
            }

        promoter_trend = trends.get("promoter", {})
        fii_trend = trends.get("fii", {})
        dii_trend = trends.get("dii", {})
        retail_trend = trends.get("retail", {})

        trend_score = 50.0
        score_factors = []

        if promoter_trend.get("direction") == "increasing":
            trend_score += 10
            score_factors.append(("promoter_increasing", 10))
        elif promoter_trend.get("direction") == "decreasing":
            trend_score -= 15
            score_factors.append(("promoter_decreasing", -15))

        if fii_trend.get("direction") == "increasing":
            trend_score += 8
            score_factors.append(("fii_increasing", 8))
        elif fii_trend.get("direction") == "decreasing":
            trend_score -= 8
            score_factors.append(("fii_decreasing", -8))

        if dii_trend.get("direction") == "increasing":
            trend_score -= 5
            score_factors.append(("dii_increasing", -5))
        elif dii_trend.get("direction") == "decreasing":
            trend_score += 5
            score_factors.append(("dii_decreasing", 5))

        if retail_trend.get("direction") == "increasing":
            trend_score -= 5
            score_factors.append(("retail_increasing", -5))
        elif retail_trend.get("direction") == "decreasing":
            trend_score += 3
            score_factors.append(("retail_decreasing", 3))

        if (
            promoter_trend.get("direction") == "increasing"
            and fii_trend.get("direction") == "increasing"
        ):
            trend_score += 5
            score_factors.append(("promoter_fii_convergence", 5))
        elif (
            promoter_trend.get("direction") == "decreasing"
            and fii_trend.get("direction") == "decreasing"
        ):
            trend_score -= 10
            score_factors.append(("promoter_fii_divergence", -10))

        trend_score = min(100, max(0, trend_score))

        insights = []
        if promoter_trend.get("direction") == "increasing":
            insights.append(f"Promoter holding is increasing ({promoter_trend['change']:+.2f}%) — strong alignment signal")
        elif promoter_trend.get("direction") == "decreasing":
            insights.append(f"Promoter holding is decreasing ({promoter_trend['change']:+.2f}%) — concerning")

        if fii_trend.get("direction") == "increasing":
            insights.append(f"FIIs increasing stake ({fii_trend['change']:+.2f}%) — institutional confidence")
        elif fii_trend.get("direction") == "decreasing":
            insights.append(f"FIIs reducing stake ({fii_trend['change']:+.2f}%) — institutional caution")

        if dii_trend.get("direction") == "increasing":
            insights.append(f"DIIs increasing stake ({dii_trend['change']:+.2f}%) — domestic institutional support")

        if retail_trend.get("direction") == "increasing":
            insights.append(f"Retail participation rising ({retail_trend['change']:+.2f}%) — retail enthusiasm")
        elif retail_trend.get("direction") == "decreasing":
            insights.append(f"Retail participation declining ({retail_trend['change']:+.2f}%)")

        return {
            "trend_score": round(trend_score, 2),
            "total_records": len(patterns),
            "categories_analyzed": list(trends.keys()),
            "category_trends": trends,
            "score_factors": score_factors,
            "insights": insights,
        }

    # ------------------------------------------------------------------
    # AI: Full Corporate Analysis
    # ------------------------------------------------------------------

    def _compute_signal(self, weighted_score: float) -> str:
        if weighted_score >= 80:
            return "strong_buy"
        if weighted_score >= 65:
            return "buy"
        if weighted_score >= 45:
            return "hold"
        if weighted_score >= 30:
            return "sell"
        return "strong_sell"

    def _compute_confidence(self, promoter_data: dict, insider_data: dict, shareholding_data: dict) -> float:
        confidence = 50.0
        if promoter_data.get("total_transactions", 0) >= 5:
            confidence += 10
        elif promoter_data.get("total_transactions", 0) >= 2:
            confidence += 5
        if insider_data.get("total_trades", 0) >= 5:
            confidence += 10
        elif insider_data.get("total_trades", 0) >= 2:
            confidence += 5
        if shareholding_data.get("total_records", 0) >= 4:
            confidence += 10
        elif shareholding_data.get("total_records", 0) >= 2:
            confidence += 5
        return min(100, max(0, confidence))

    async def generate_analysis(self, company_id: int) -> CorporateAnalysis:
        promoter_data = await self.analyze_promoter_activity(company_id)
        insider_data = await self.analyze_insider_sentiment(company_id)
        shareholding_data = await self.analyze_shareholding_trends(company_id)

        promoter_buying_score = promoter_data.get("buying_score", 50.0)
        promoter_selling_score = promoter_data.get("selling_score", 50.0)
        insider_sentiment_score = insider_data.get("sentiment_score", 50.0)
        shareholding_trend_score = shareholding_data.get("trend_score", 50.0)

        promoter_net = promoter_data.get("net_flow", 0)
        promoter_weight = 0.30 if abs(promoter_net) > 0 else 0.15
        insider_weight = 0.25 if insider_data.get("total_trades", 0) > 0 else 0.15
        shareholding_weight = 0.45 if shareholding_data.get("total_records", 0) > 0 else 0.20

        total_weight = promoter_weight + insider_weight + shareholding_weight
        weighted_score = (
            (promoter_buying_score * promoter_weight)
            + (insider_sentiment_score * insider_weight)
            + (shareholding_trend_score * shareholding_weight)
        ) / total_weight

        if promoter_selling_score > promoter_buying_score:
            weighted_score = weighted_score * 0.85

        weighted_score = min(100, max(0, weighted_score))
        signal = self._compute_signal(weighted_score)
        confidence = self._compute_confidence(promoter_data, insider_data, shareholding_data)

        all_insights = []
        all_insights.extend(promoter_data.get("insights", []))
        all_insights.extend(insider_data.get("insights", []))
        all_insights.extend(shareholding_data.get("insights", []))

        analysis_dict = {
            "promoter_buying_score": round(promoter_buying_score, 2),
            "promoter_selling_score": round(promoter_selling_score, 2),
            "insider_sentiment_score": round(insider_sentiment_score, 2),
            "shareholding_trend_score": round(shareholding_trend_score, 2),
            "weighted_score": round(weighted_score, 2),
            "signal": signal,
            "confidence": round(confidence, 2),
            "promoter_analysis": promoter_data,
            "insider_analysis": insider_data,
            "shareholding_analysis": shareholding_data,
        }

        return await self._analysis_repo.create(
            company_id=company_id,
            analysis_date=date.today(),
            promoter_buying_score=round(promoter_buying_score, 2),
            promoter_selling_score=round(promoter_selling_score, 2),
            insider_sentiment_score=round(insider_sentiment_score, 2),
            shareholding_trend_score=round(shareholding_trend_score, 2),
            weighted_score=round(weighted_score, 2),
            signal=signal,
            confidence=round(confidence, 2),
            insights_json=json.dumps({
                "insights": all_insights,
                "score_factors": shareholding_data.get("score_factors", []),
                "category_trends": shareholding_data.get("category_trends", {}),
            }),
        )

    async def get_analysis(self, analysis_id: int) -> CorporateAnalysis | None:
        return await self._analysis_repo.get(analysis_id)

    async def list_analyses(
        self,
        company_id: int | None = None,
        signal: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[CorporateAnalysis], int]:
        query = select(CorporateAnalysis)
        count_query = select(func.count()).select_from(CorporateAnalysis)
        if company_id is not None:
            query = query.where(CorporateAnalysis.company_id == company_id)
            count_query = count_query.where(CorporateAnalysis.company_id == company_id)
        if signal is not None:
            query = query.where(CorporateAnalysis.signal == signal)
            count_query = count_query.where(CorporateAnalysis.signal == signal)
        total = (await self._session.execute(count_query)).scalar() or 0
        query = query.order_by(CorporateAnalysis.generated_at.desc()).offset(skip).limit(limit)
        rows = (await self._session.execute(query)).scalars().all()
        return rows, total

    async def get_latest_analysis(self, company_id: int) -> CorporateAnalysis | None:
        result = await self._session.execute(
            select(CorporateAnalysis)
            .where(CorporateAnalysis.company_id == company_id)
            .order_by(CorporateAnalysis.generated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def delete_analysis(self, analysis_id: int) -> bool:
        return await self._analysis_repo.delete(analysis_id)
