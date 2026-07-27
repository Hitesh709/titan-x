import json
import math
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.macro import MacroAnalysis, MacroFeature, MacroIndicator


class MacroService:
    def __init__(self, session: AsyncSession):
        self.session = session

    INDICATOR_TYPES = ["interest_rate", "inflation", "gdp", "currency", "bond_yield", "oil", "gold"]

    # ============================================================
    # RECORD INDICATOR
    # ============================================================

    async def record_indicator(
        self, indicator_type: str, as_of_date: date, value: float,
        unit: str | None = None, source: str | None = None,
        description: str | None = None,
    ) -> MacroIndicator:
        ind = MacroIndicator(
            indicator_type=indicator_type,
            as_of_date=as_of_date,
            value=value,
            unit=unit, source=source, description=description,
        )
        self.session.add(ind)
        await self.session.flush()
        await self.session.refresh(ind)
        return ind

    async def get_indicator(self, indicator_type: str, as_of_date: date | None = None) -> MacroIndicator | None:
        stmt = select(MacroIndicator).where(MacroIndicator.indicator_type == indicator_type)
        if as_of_date:
            stmt = stmt.where(MacroIndicator.as_of_date == as_of_date)
        stmt = stmt.order_by(MacroIndicator.as_of_date.desc()).limit(1)
        r = await self.session.execute(stmt)
        return r.scalar_one_or_none()

    async def list_indicators(
        self, indicator_type: str | None = None, limit: int = 100, offset: int = 0,
    ) -> list[MacroIndicator]:
        stmt = select(MacroIndicator)
        if indicator_type:
            stmt = stmt.where(MacroIndicator.indicator_type == indicator_type)
        stmt = stmt.order_by(MacroIndicator.as_of_date.desc()).offset(offset).limit(limit)
        r = await self.session.execute(stmt)
        return list(r.scalars().all())

    # ============================================================
    # ANALYZE — compute per-indicator scores + composite
    # ============================================================

    async def analyze(self, as_of_date: date | None = None) -> MacroAnalysis:
        if as_of_date is None:
            as_of_date = date.today()

        scores = {}
        details = {}

        for itype in self.INDICATOR_TYPES:
            score, detail = await self._score_indicator(itype, as_of_date)
            scores[itype] = score
            details[itype] = detail

        # Composite macro score (equal weight)
        valid = [v for v in scores.values() if v is not None]
        composite = round(sum(valid) / len(valid), 1) if valid else 50.0

        # Macro regime
        ir_score = scores.get("interest_rate") or 50
        infl_score = scores.get("inflation") or 50
        gdp_score = scores.get("gdp") or 50

        if ir_score > 60 and infl_score > 60:
            macro_regime = "tightening"
        elif ir_score < 40 and infl_score < 40:
            macro_regime = "accommodative"
        elif ir_score > 60 and infl_score < 40:
            macro_regime = "restrictive"
        elif ir_score < 40 and infl_score > 60:
            macro_regime = "loose"
        else:
            macro_regime = "neutral"

        # Growth-inflation regime
        if gdp_score >= 55 and infl_score < 45:
            growth_inflation_regime = "goldilocks"
        elif gdp_score >= 55 and infl_score >= 55:
            growth_inflation_regime = "overheating"
        elif gdp_score < 45 and infl_score >= 55:
            growth_inflation_regime = "stagflation"
        elif gdp_score < 45 and infl_score < 45:
            growth_inflation_regime = "recession"
        else:
            growth_inflation_regime = "transitional"

        # Risk regime
        if composite >= 60:
            risk_regime = "risk_on"
        elif composite <= 40:
            risk_regime = "risk_off"
        else:
            risk_regime = "neutral"

        analysis = MacroAnalysis(
            as_of_date=as_of_date,
            interest_rate_score=scores.get("interest_rate"),
            inflation_score=scores.get("inflation"),
            gdp_score=scores.get("gdp"),
            currency_score=scores.get("currency"),
            bond_yield_score=scores.get("bond_yield"),
            oil_score=scores.get("oil"),
            gold_score=scores.get("gold"),
            composite_macro_score=composite,
            macro_regime=macro_regime,
            growth_inflation_regime=growth_inflation_regime,
            risk_regime=risk_regime,
            details_json=json.dumps(details, default=str),
        )
        self.session.add(analysis)
        await self.session.flush()
        await self.session.refresh(analysis)
        return analysis

    async def get_analysis(self, as_of_date: date | None = None) -> MacroAnalysis | None:
        stmt = select(MacroAnalysis)
        if as_of_date:
            stmt = stmt.where(MacroAnalysis.as_of_date == as_of_date)
        stmt = stmt.order_by(MacroAnalysis.as_of_date.desc()).limit(1)
        r = await self.session.execute(stmt)
        return r.scalar_one_or_none()

    async def list_analyses(self, limit: int = 30, offset: int = 0) -> list[MacroAnalysis]:
        r = await self.session.execute(
            select(MacroAnalysis).order_by(MacroAnalysis.as_of_date.desc()).offset(offset).limit(limit)
        )
        return list(r.scalars().all())

    # ============================================================
    # GENERATE AI FEATURES
    # ============================================================

    async def generate_features(self, as_of_date: date | None = None) -> list[MacroFeature]:
        if as_of_date is None:
            as_of_date = date.today()

        analysis = await self.get_analysis(as_of_date) or await self.analyze(as_of_date)
        features = []

        for itype in self.INDICATOR_TYPES:
            vals = await self._get_indicator_values(itype, as_of_date, lookback=365)
            if not vals:
                continue

            current = vals[-1]["value"]
            prev_month = vals[-2]["value"] if len(vals) >= 2 else current
            prev_year = vals[-12]["value"] if len(vals) >= 12 else current

            mom_chg = round(current - prev_month, 4)
            yoy_chg = round(current - prev_year, 4)
            mom_pct = round((current - prev_month) / prev_month * 100, 4) if prev_month != 0 else 0
            yoy_pct = round((current - prev_year) / prev_year * 100, 4) if prev_year != 0 else 0

            all_vals = [v["value"] for v in vals]
            mean_v = sum(all_vals) / len(all_vals)
            std_v = self._std(all_vals)
            zscore = round((current - mean_v) / std_v, 4) if std_v > 0 else 0

            three_mo = vals[-3:] if len(vals) >= 3 else vals
            trend_change = three_mo[-1]["value"] - three_mo[0]["value"] if len(three_mo) >= 2 else 0
            trend_dir = "up" if trend_change > 0 else "down" if trend_change < 0 else "stable"

            features.append(MacroFeature(
                feature_name=f"{itype}_value", as_of_date=as_of_date, value=current,
                category=itype, description=f"Current {itype} value",
            ))
            features.append(MacroFeature(
                feature_name=f"{itype}_mom_change", as_of_date=as_of_date, value=mom_chg,
                category=itype, description=f"Month-over-month change in {itype}",
            ))
            features.append(MacroFeature(
                feature_name=f"{itype}_yoy_change", as_of_date=as_of_date, value=yoy_chg,
                category=itype, description=f"Year-over-year change in {itype}",
            ))
            features.append(MacroFeature(
                feature_name=f"{itype}_mom_pct", as_of_date=as_of_date, value=mom_pct,
                category=itype, description=f"Month-over-month % change in {itype}",
            ))
            features.append(MacroFeature(
                feature_name=f"{itype}_yoy_pct", as_of_date=as_of_date, value=yoy_pct,
                category=itype, description=f"Year-over-year % change in {itype}",
            ))
            features.append(MacroFeature(
                feature_name=f"{itype}_zscore", as_of_date=as_of_date, value=zscore,
                category=itype, description=f"Z-score vs 1-year history for {itype}",
            ))
            features.append(MacroFeature(
                feature_name=f"{itype}_trend_3m", as_of_date=as_of_date,
                value=1.0 if trend_dir == "up" else -1.0 if trend_dir == "down" else 0.0,
                category=itype, description=f"3-month trend direction for {itype}",
            ))

        # Composite features
        for suffix, val in [
            ("composite_macro_score", analysis.composite_macro_score or 50.0),
            ("macro_regime_code", self._regime_code(analysis.macro_regime or "neutral")),
            ("growth_inflation_regime_code", self._regime_code(analysis.growth_inflation_regime or "transitional")),
            ("risk_regime_code", self._regime_code(analysis.risk_regime or "neutral")),
        ]:
            features.append(MacroFeature(
                feature_name=f"macro_{suffix}", as_of_date=as_of_date, value=val,
                category="composite", description=f"Macro {suffix}",
            ))

        for f in features:
            self.session.add(f)
        await self.session.flush()
        for f in features:
            await self.session.refresh(f)
        return features

    async def get_features(
        self, feature_name: str | None = None, category: str | None = None, limit: int = 50,
    ) -> list[MacroFeature]:
        stmt = select(MacroFeature)
        if feature_name:
            stmt = stmt.where(MacroFeature.feature_name == feature_name)
        if category:
            stmt = stmt.where(MacroFeature.category == category)
        stmt = stmt.order_by(MacroFeature.as_of_date.desc()).limit(limit)
        r = await self.session.execute(stmt)
        return list(r.scalars().all())

    # ============================================================
    # PRIVATE HELPERS
    # ============================================================

    async def _score_indicator(self, indicator_type: str, as_of_date: date) -> tuple[float | None, dict]:
        vals = await self._get_indicator_values(indicator_type, as_of_date, lookback=365)
        if not vals:
            return None, {"reason": "no_data"}

        current = vals[-1]["value"]
        all_vals = [v["value"] for v in vals]
        mean_v = sum(all_vals) / len(all_vals)
        std_v = self._std(all_vals)
        zscore = (current - mean_v) / std_v if std_v > 0 else 0

        mom = (current - vals[-2]["value"]) / vals[-2]["value"] if len(vals) >= 2 and vals[-2]["value"] != 0 else 0
        yoy = (current - vals[-12]["value"]) / vals[-12]["value"] if len(vals) >= 12 and vals[-12]["value"] != 0 else 0

        score = 50.0
        detail = {"current": current, "mean": round(mean_v, 4), "std": round(std_v, 4), "zscore": round(zscore, 4)}

        if indicator_type == "interest_rate":
            score += zscore * 8
            score += mom * 100
            detail["mom"] = round(mom, 4)
        elif indicator_type == "inflation":
            score += zscore * 5  # moderate weight
            score += yoy * 50
            detail["yoy"] = round(yoy, 4)
        elif indicator_type == "gdp":
            score += zscore * 10  # high weight
            score += yoy * 80
            detail["yoy"] = round(yoy, 4)
        elif indicator_type == "currency":
            score += zscore * 3  # low weight
            detail["direction"] = "stronger" if zscore > 0 else "weaker"
        elif indicator_type == "bond_yield":
            score += zscore * 6
            detail["yield_change"] = round(mom * 100, 4)
        elif indicator_type == "oil":
            score += zscore * 4
            detail["mom"] = round(mom, 4)
        elif indicator_type == "gold":
            score += zscore * 4
            detail["mom"] = round(mom, 4)

        return max(0, min(100, round(score, 1))), detail

    async def _get_indicator_values(self, indicator_type: str, as_of_date: date, lookback: int = 365) -> list[dict]:
        lb = as_of_date - timedelta(days=lookback)
        r = await self.session.execute(
            select(MacroIndicator).where(
                MacroIndicator.indicator_type == indicator_type,
                MacroIndicator.as_of_date >= lb,
                MacroIndicator.as_of_date <= as_of_date,
            ).order_by(MacroIndicator.as_of_date.asc())
        )
        return [{"date": ind.as_of_date, "value": ind.value} for ind in r.scalars().all()]

    def _std(self, vals: list[float]) -> float:
        if len(vals) < 2:
            return 0
        m = sum(vals) / len(vals)
        return math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals))

    def _regime_code(self, regime: str) -> float:
        codes = {
            "tightening": 0.9, "accommodative": 0.1, "restrictive": 0.8, "loose": 0.2,
            "neutral": 0.5, "risk_on": 0.9, "risk_off": 0.1,
            "goldilocks": 0.9, "overheating": 0.7, "stagflation": 0.2, "recession": 0.1,
            "transitional": 0.5,
        }
        return codes.get(regime, 0.5)
