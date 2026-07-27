import json
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.macro import MacroAnalysis, MacroFeature, MacroIndicator
from titan_x.services.macro_service import MacroService


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fks(dbapi_con, _rec):
        cursor = dbapi_con.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()


@pytest_asyncio.fixture
def svc(session: AsyncSession) -> MacroService:
    return MacroService(session)


@pytest_asyncio.fixture
async def macro_data(svc: MacroService):
    """Seed 24 months of macro indicator data."""
    base = date(2024, 1, 1)
    for i in range(24):
        d = base + timedelta(days=30 * i)
        await svc.record_indicator("interest_rate", d, 6.5 + (i % 3) * 0.1, unit="%", source="RBI")
        await svc.record_indicator("inflation", d, 4.5 + (i % 4) * 0.3, unit="%", source="CPI")
        await svc.record_indicator("gdp", d, 6.0 + (i % 6) * 0.2, unit="%", source="MOSPI")
        await svc.record_indicator("currency", d, 82.5 + (i % 5) * 0.5, unit="INR/USD", source="RBI")
        await svc.record_indicator("bond_yield", d, 7.0 + (i % 4) * 0.15, unit="%", source="CCIL")
        await svc.record_indicator("oil", d, 75 + (i % 8) * 2, unit="USD/bbl", source="WTI")
        await svc.record_indicator("gold", d, 1900 + (i % 6) * 10, unit="USD/oz", source="LBMA")


# ============================================================
# INDICATORS
# ============================================================

class TestIndicators:
    @pytest.mark.asyncio
    async def test_record_indicator(self, svc: MacroService):
        ind = await svc.record_indicator("interest_rate", date(2025, 6, 1), 6.25, "%", "RBI", "Repo rate")
        assert ind.indicator_type == "interest_rate"
        assert ind.value == 6.25
        assert ind.unit == "%"
        assert ind.source == "RBI"

    @pytest.mark.asyncio
    async def test_get_latest_indicator(self, svc: MacroService, macro_data):
        ind = await svc.get_indicator("oil")
        assert ind is not None
        assert ind.indicator_type == "oil"

    @pytest.mark.asyncio
    async def test_get_indicator_by_date(self, svc: MacroService, macro_data):
        ind = await svc.get_indicator("gdp", date(2024, 1, 1))
        assert ind is not None
        assert ind.value == 6.0

    @pytest.mark.asyncio
    async def test_get_indicator_not_found(self, svc: MacroService):
        ind = await svc.get_indicator("unknown")
        assert ind is None

    @pytest.mark.asyncio
    async def test_list_indicators(self, svc: MacroService, macro_data):
        results = await svc.list_indicators(limit=5)
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_list_indicators_by_type(self, svc: MacroService, macro_data):
        results = await svc.list_indicators(indicator_type="gold", limit=10)
        assert len(results) > 0
        assert all(r.indicator_type == "gold" for r in results)

    @pytest.mark.asyncio
    async def test_list_indicators_by_type_empty(self, svc: MacroService):
        results = await svc.list_indicators(indicator_type="unknown")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_all_indicator_types(self, svc: MacroService, macro_data):
        for t in MacroService.INDICATOR_TYPES:
            ind = await svc.get_indicator(t)
            assert ind is not None, f"Missing {t}"
            assert ind.value > 0


# ============================================================
# MACRO ANALYSIS
# ============================================================

class TestMacroAnalysis:
    @pytest.mark.asyncio
    async def test_analyze_returns_scores(self, svc: MacroService, macro_data):
        result = await svc.analyze(date(2025, 6, 1))
        assert result.composite_macro_score is not None
        assert result.interest_rate_score is not None
        assert result.inflation_score is not None
        assert result.gdp_score is not None
        assert result.currency_score is not None
        assert result.bond_yield_score is not None
        assert result.oil_score is not None
        assert result.gold_score is not None
        assert 0 <= result.composite_macro_score <= 100

    @pytest.mark.asyncio
    async def test_analyze_regime(self, svc: MacroService, macro_data):
        result = await svc.analyze(date(2025, 6, 1))
        assert result.macro_regime in ("tightening", "accommodative", "restrictive", "loose", "neutral")
        assert result.growth_inflation_regime in ("goldilocks", "overheating", "stagflation", "recession", "transitional")
        assert result.risk_regime in ("risk_on", "risk_off", "neutral")

    @pytest.mark.asyncio
    async def test_analyze_no_data(self, svc: MacroService):
        result = await svc.analyze(date(2025, 6, 1))
        assert result.composite_macro_score == 50.0

    @pytest.mark.asyncio
    async def test_analyze_details_json(self, svc: MacroService, macro_data):
        result = await svc.analyze(date(2025, 6, 1))
        details = json.loads(result.details_json)
        for t in MacroService.INDICATOR_TYPES:
            assert t in details

    @pytest.mark.asyncio
    async def test_get_analysis(self, svc: MacroService, macro_data):
        a1 = await svc.analyze(date(2025, 6, 1))
        a2 = await svc.get_analysis(date(2025, 6, 1))
        assert a2 is not None
        assert a2.id == a1.id

    @pytest.mark.asyncio
    async def test_get_latest_analysis(self, svc: MacroService, macro_data):
        await svc.analyze(date(2025, 5, 1))
        latest = await svc.analyze(date(2025, 6, 1))
        fetched = await svc.get_analysis()
        assert fetched.id == latest.id

    @pytest.mark.asyncio
    async def test_get_analysis_not_found(self, svc: MacroService):
        result = await svc.get_analysis(date(2020, 1, 1))
        assert result is None

    @pytest.mark.asyncio
    async def test_list_analyses(self, svc: MacroService, macro_data):
        for i in range(5):
            await svc.analyze(date(2025, 1, 1) + timedelta(days=30 * i))
        results = await svc.list_analyses(limit=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_rising_rates_score(self, svc: MacroService, macro_data):
        result = await svc.analyze(date(2025, 6, 1))
        assert result.interest_rate_score is not None

    @pytest.mark.asyncio
    async def test_goldilocks_detection(self, svc: MacroService, macro_data):
        result = await svc.analyze(date(2025, 6, 1))
        # With high GDP and moderate inflation, could be goldilocks
        assert result.growth_inflation_regime is not None


# ============================================================
# MACRO FEATURES
# ============================================================

class TestMacroFeatures:
    @pytest.mark.asyncio
    async def test_generate_features(self, svc: MacroService, macro_data):
        features = await svc.generate_features(date(2025, 6, 1))
        assert len(features) > 0
        names = [f.feature_name for f in features]
        assert "interest_rate_value" in names
        assert "inflation_mom_pct" in names
        assert "gdp_yoy_pct" in names
        assert "currency_zscore" in names
        assert "macro_composite_macro_score" in names

    @pytest.mark.asyncio
    async def test_feature_categories(self, svc: MacroService, macro_data):
        features = await svc.generate_features(date(2025, 6, 1))
        categories = set(f.category for f in features)
        assert "composite" in categories
        assert "interest_rate" in categories
        assert "inflation" in categories

    @pytest.mark.asyncio
    async def test_feature_values(self, svc: MacroService, macro_data):
        features = await svc.generate_features(date(2025, 6, 1))
        for f in features:
            assert f.value is not None
            assert f.feature_name is not None

    @pytest.mark.asyncio
    async def test_get_features_by_name(self, svc: MacroService, macro_data):
        await svc.generate_features(date(2025, 6, 1))
        results = await svc.get_features(feature_name="oil_value")
        assert len(results) >= 1
        assert results[0].feature_name == "oil_value"

    @pytest.mark.asyncio
    async def test_get_features_by_category(self, svc: MacroService, macro_data):
        await svc.generate_features(date(2025, 6, 1))
        results = await svc.get_features(category="composite")
        assert len(results) >= 1
        assert all(r.category == "composite" for r in results)

    @pytest.mark.asyncio
    async def test_get_features_empty(self, svc: MacroService):
        results = await svc.get_features(feature_name="nonexistent")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_features_include_trend_direction(self, svc: MacroService, macro_data):
        features = await svc.generate_features(date(2025, 6, 1))
        trend_features = [f for f in features if "trend_3m" in f.feature_name]
        assert len(trend_features) >= len(MacroService.INDICATOR_TYPES)
        for f in trend_features:
            assert f.value in (-1.0, 0.0, 1.0)

    @pytest.mark.asyncio
    async def test_features_include_zscore(self, svc: MacroService, macro_data):
        features = await svc.generate_features(date(2025, 6, 1))
        zscores = [f for f in features if "zscore" in f.feature_name]
        assert len(zscores) >= len(MacroService.INDICATOR_TYPES)

    @pytest.mark.asyncio
    async def test_regime_code_features(self, svc: MacroService, macro_data):
        features = await svc.generate_features(date(2025, 6, 1))
        codes = [f for f in features if "regime_code" in f.feature_name]
        assert len(codes) >= 3
        for c in codes:
            assert 0 <= c.value <= 1.0

    @pytest.mark.asyncio
    async def test_no_data_features(self, svc: MacroService):
        features = await svc.generate_features(date(2025, 6, 1))
        assert len(features) > 0
        # composite features should still exist
        names = [f.feature_name for f in features]
        assert "macro_composite_macro_score" in names

    @pytest.mark.asyncio
    async def test_yoy_change_features(self, svc: MacroService, macro_data):
        features = await svc.generate_features(date(2025, 6, 1))
        yoy = [f for f in features if "yoy_change" in f.feature_name]
        assert len(yoy) >= len(MacroService.INDICATOR_TYPES)
