import json
import math
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.global_market import (
    GlobalAnalysis,
    GlobalCondition,
    GlobalMarketData,
    GlobalSimilarityResult,
)
from titan_x.models.price import DailyPrice


class GlobalMarketService:
    def __init__(self, session: AsyncSession):
        self.session = session

    REGIONS = {
        "us": ["SPX", "NDX", "DJI"],
        "europe": ["FTSE", "DAX", "CAC"],
        "asia": ["NKY", "HSI", "SHCOMP"],
    }
    FUTURES_SYMBOLS = ["ES", "NQ", "YM", "RTY"]
    VIX_SYMBOL = "VIX"
    DXY_SYMBOL = "DXY"

    # ============================================================
    # RECORD MARKET DATA
    # ============================================================

    async def record_data(
        self, data_type: str, region: str, symbol: str, as_of_date: date,
        value: float, change_pct: float | None = None, source: str | None = None,
    ) -> GlobalMarketData:
        d = GlobalMarketData(
            data_type=data_type, region=region, symbol=symbol.upper(),
            as_of_date=as_of_date, value=value, change_pct=change_pct, source=source,
        )
        self.session.add(d)
        await self.session.flush()
        await self.session.refresh(d)
        return d

    async def get_data(self, symbol: str, as_of_date: date | None = None) -> GlobalMarketData | None:
        stmt = select(GlobalMarketData).where(GlobalMarketData.symbol == symbol.upper())
        if as_of_date:
            stmt = stmt.where(GlobalMarketData.as_of_date == as_of_date)
        stmt = stmt.order_by(GlobalMarketData.as_of_date.desc()).limit(1)
        r = await self.session.execute(stmt)
        return r.scalar_one_or_none()

    async def list_data(self, region: str | None = None, data_type: str | None = None, limit: int = 50) -> list[GlobalMarketData]:
        stmt = select(GlobalMarketData)
        if region:
            stmt = stmt.where(GlobalMarketData.region == region)
        if data_type:
            stmt = stmt.where(GlobalMarketData.data_type == data_type)
        stmt = stmt.order_by(GlobalMarketData.as_of_date.desc()).limit(limit)
        r = await self.session.execute(stmt)
        return list(r.scalars().all())

    # ============================================================
    # ANALYZE — compute regional + global scores
    # ============================================================

    async def analyze(self, as_of_date: date | None = None) -> GlobalAnalysis:
        if as_of_date is None:
            as_of_date = date.today()

        scores = {}
        details = {}

        for region, symbols in self.REGIONS.items():
            score, detail = await self._score_region(region, symbols, as_of_date)
            scores[region] = score
            details[region] = detail

        for label, syms in [("futures", self.FUTURES_SYMBOLS)]:
            score, detail = await self._score_region(label, syms, as_of_date)
            scores[label] = score
            details[label] = detail

        vix_data = await self._get_recent_data(self.VIX_SYMBOL, as_of_date)
        if vix_data:
            v = vix_data[-1]["value"]
            # VIX < 15 = low fear (high score), VIX > 30 = high fear (low score)
            vix_score = max(0, min(100, round(100 - (v - 10) * 3, 1)))
            scores["vix"] = vix_score
            details["vix"] = {"value": v, "score": vix_score}
        else:
            scores["vix"] = 50.0
            details["vix"] = {"reason": "no_data"}

        dxy_data = await self._get_recent_data(self.DXY_SYMBOL, as_of_date)
        if dxy_data:
            dxy_vals = [d["value"] for d in dxy_data]
            mean_dxy = sum(dxy_vals) / len(dxy_vals)
            std_dxy = self._std(dxy_vals)
            z = (dxy_data[-1]["value"] - mean_dxy) / std_dxy if std_dxy > 0 else 0
            dxy_score = max(0, min(100, round(50 - z * 5, 1)))
            scores["dxy"] = dxy_score
            details["dxy"] = {"value": dxy_data[-1]["value"], "zscore": round(z, 4), "score": dxy_score}
        else:
            scores["dxy"] = 50.0
            details["dxy"] = {"reason": "no_data"}

        valid = [v for v in scores.values() if v is not None]
        global_score = round(sum(valid) / len(valid), 1) if valid else 50.0

        if global_score >= 60:
            sentiment = "bullish"
        elif global_score <= 40:
            sentiment = "bearish"
        else:
            sentiment = "neutral"

        analysis = GlobalAnalysis(
            as_of_date=as_of_date,
            us_score=scores.get("us"),
            europe_score=scores.get("europe"),
            asia_score=scores.get("asia"),
            futures_score=scores.get("futures"),
            vix_score=scores.get("vix"),
            dxy_score=scores.get("dxy"),
            global_score=global_score,
            global_sentiment=sentiment,
            details_json=json.dumps(details, default=str),
        )
        self.session.add(analysis)
        await self.session.flush()
        await self.session.refresh(analysis)
        return analysis

    async def get_analysis(self, as_of_date: date | None = None) -> GlobalAnalysis | None:
        stmt = select(GlobalAnalysis)
        if as_of_date:
            stmt = stmt.where(GlobalAnalysis.as_of_date == as_of_date)
        stmt = stmt.order_by(GlobalAnalysis.as_of_date.desc()).limit(1)
        r = await self.session.execute(stmt)
        return r.scalar_one_or_none()

    async def list_analyses(self, limit: int = 30, offset: int = 0) -> list[GlobalAnalysis]:
        r = await self.session.execute(
            select(GlobalAnalysis).order_by(GlobalAnalysis.as_of_date.desc()).offset(offset).limit(limit)
        )
        return list(r.scalars().all())

    # ============================================================
    # HISTORICAL SIMILARITY SEARCH
    # ============================================================

    async def build_condition_snapshot(self, as_of_date: date | None = None) -> GlobalCondition:
        if as_of_date is None:
            as_of_date = date.today()

        analysis = await self.get_analysis(as_of_date) or await self.analyze(as_of_date)
        feat_vec = [
            analysis.us_score or 50,
            analysis.europe_score or 50,
            analysis.asia_score or 50,
            analysis.futures_score or 50,
            analysis.vix_score or 50,
            analysis.dxy_score or 50,
            analysis.global_score or 50,
        ]

        outcomes = {}
        for sym in ["SPX", "NDX", "NKY", "HSI"]:
            outcomes[sym] = await self._get_forward_returns(sym, as_of_date)

        condition = GlobalCondition(
            snapshot_date=as_of_date,
            feature_vector=json.dumps(feat_vec),
            region_scores_json=json.dumps({
                "us": analysis.us_score, "europe": analysis.europe_score,
                "asia": analysis.asia_score, "futures": analysis.futures_score,
                "vix": analysis.vix_score, "dxy": analysis.dxy_score,
                "global": analysis.global_score,
            }),
            outcome_returns_json=json.dumps(outcomes, default=str),
            metadata_json=json.dumps({"sentiment": analysis.global_sentiment}),
        )
        self.session.add(condition)
        await self.session.flush()
        await self.session.refresh(condition)
        return condition

    async def search_similar(
        self, as_of_date: date | None = None, top_n: int = 5,
    ) -> list[GlobalSimilarityResult]:
        if as_of_date is None:
            as_of_date = date.today()

        query_analysis = await self.get_analysis(as_of_date) or await self.analyze(as_of_date)
        query_vec = [
            query_analysis.us_score or 50,
            query_analysis.europe_score or 50,
            query_analysis.asia_score or 50,
            query_analysis.futures_score or 50,
            query_analysis.vix_score or 50,
            query_analysis.dxy_score or 50,
            query_analysis.global_score or 50,
        ]

        conditions_result = await self.session.execute(
            select(GlobalCondition).where(
                GlobalCondition.snapshot_date < as_of_date
            ).order_by(GlobalCondition.snapshot_date.desc())
        )
        all_conditions = list(conditions_result.scalars().all())

        scored = []
        for cond in all_conditions:
            try:
                stored_vec = json.loads(cond.feature_vector)
            except (json.JSONDecodeError, TypeError):
                continue
            sim = self._cosine_similarity(query_vec, stored_vec)
            scored.append((sim, cond))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_n]

        results = []
        for sim, cond in top:
            outcomes = json.loads(cond.outcome_returns_json) if cond.outcome_returns_json else {}
            winning = {}
            losing = {}
            avg_1d, avg_5d, avg_20d, avg_60d = [], [], [], []
            for sym, rets in outcomes.items():
                r1 = rets.get("1d")
                r5 = rets.get("5d")
                r20 = rets.get("20d")
                r60 = rets.get("60d")
                if r1 is not None:
                    avg_1d.append(r1)
                    if r1 > 0:
                        winning[sym] = r1
                    else:
                        losing[sym] = r1
                if r5 is not None:
                    avg_5d.append(r5)
                if r20 is not None:
                    avg_20d.append(r20)
                if r60 is not None:
                    avg_60d.append(r60)

            sim_result = GlobalSimilarityResult(
                query_date=as_of_date,
                matched_date=cond.snapshot_date,
                similarity_pct=round(sim * 100, 1),
                historical_outcomes_json=json.dumps(outcomes, default=str),
                winning_stocks_json=json.dumps(winning, default=str),
                losing_stocks_json=json.dumps(losing, default=str),
                avg_return_1d=round(sum(avg_1d) / len(avg_1d), 4) if avg_1d else None,
                avg_return_5d=round(sum(avg_5d) / len(avg_5d), 4) if avg_5d else None,
                avg_return_20d=round(sum(avg_20d) / len(avg_20d), 4) if avg_20d else None,
                avg_return_60d=round(sum(avg_60d) / len(avg_60d), 4) if avg_60d else None,
            )
            self.session.add(sim_result)
            await self.session.flush()
            await self.session.refresh(sim_result)
            results.append(sim_result)

        return results

    async def get_similarity_results(self, query_date: date | None = None, limit: int = 10) -> list[GlobalSimilarityResult]:
        stmt = select(GlobalSimilarityResult)
        if query_date:
            stmt = stmt.where(GlobalSimilarityResult.query_date == query_date)
        stmt = stmt.order_by(GlobalSimilarityResult.created_at.desc()).limit(limit)
        r = await self.session.execute(stmt)
        return list(r.scalars().all())

    # ============================================================
    # PRIVATE HELPERS
    # ============================================================

    async def _score_region(self, label: str, symbols: list[str], as_of_date: date) -> tuple[float | None, dict]:
        changes = []
        detail = {}
        for sym in symbols:
            data = await self._get_recent_data(sym, as_of_date, lookback=30)
            if data and len(data) >= 2:
                cp = (data[-1]["value"] - data[-2]["value"]) / data[-2]["value"]
                changes.append(cp)
                detail[sym] = {"current": data[-1]["value"], "change_pct": round(cp, 4)}
            else:
                detail[sym] = {"reason": "no_data"}

        if not changes:
            return None, detail

        mom_1d = changes[-1] if changes else 0
        recent = changes[-5:] if len(changes) >= 5 else changes
        avg_chg = sum(recent) / len(recent) if recent else 0

        score = 50 + avg_chg * 200 + mom_1d * 100
        detail["avg_change_pct"] = round(avg_chg, 4)
        detail["momentum_1d"] = round(mom_1d, 4)
        return max(0, min(100, round(score, 1))), detail

    async def _get_recent_data(self, symbol: str, as_of_date: date, lookback: int = 60) -> list[dict]:
        lb = as_of_date - timedelta(days=lookback)
        r = await self.session.execute(
            select(GlobalMarketData).where(
                GlobalMarketData.symbol == symbol.upper(),
                GlobalMarketData.as_of_date >= lb,
                GlobalMarketData.as_of_date <= as_of_date,
            ).order_by(GlobalMarketData.as_of_date.asc())
        )
        return [{"date": d.as_of_date, "value": d.value} for d in r.scalars().all()]

    async def _get_forward_returns(self, symbol: str, as_of_date: date) -> dict:
        r = await self.session.execute(
            select(DailyPrice).where(
                DailyPrice.symbol == symbol,
                DailyPrice.trade_date >= as_of_date,
            ).order_by(DailyPrice.trade_date.asc())
        )
        prices = list(r.scalars().all())
        if not prices:
            return {}

        base_price = prices[0].close
        if base_price <= 0:
            return {}

        def _ret(days: int) -> float | None:
            target_date = as_of_date + timedelta(days=days)
            target = next((p for p in prices if p.trade_date >= target_date), None) or prices[-1]
            return round((target.close - base_price) / base_price, 4)

        return {"1d": _ret(1), "5d": _ret(5), "20d": _ret(20), "60d": _ret(60)}

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        if len(a) != len(b) or not a:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def _std(self, vals: list[float]) -> float:
        if len(vals) < 2:
            return 0
        m = sum(vals) / len(vals)
        return math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals))
