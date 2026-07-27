import hashlib
import math
from datetime import date, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.feature_engineering import FeatureDefinition, FeatureValue
from titan_x.models.financial_analysis import QuarterlyResult
from titan_x.models.market_breadth import MarketBreadth
from titan_x.models.macro import MacroIndicator
from titan_x.models.news import NewsArticle
from titan_x.models.news_nlp import NewsNLPAnalysis
from titan_x.models.price import DailyPrice
from titan_x.services.feature_engineering_service import FeatureEngineeringService


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
async def svc(session: AsyncSession) -> FeatureEngineeringService:
    return FeatureEngineeringService(session)


@pytest_asyncio.fixture
async def price_data(session: AsyncSession):
    today = date.today()
    base = today - timedelta(days=265)
    idx = 0
    for i in range(270):
        d = base + timedelta(days=i)
        if d.weekday() < 5 and d <= today:
            p = 100.0 + idx * 0.2 + (idx % 5 - 2)
            session.add(DailyPrice(
                symbol="TEST", trade_date=d,
                open=p, high=p + 1.5, low=p - 1.5, close=p + 0.3,
                volume=1_000_000 + idx * 5_000,
            ))
            idx += 1
    await session.flush()


@pytest_asyncio.fixture
async def financial_data(session: AsyncSession):
    session.add(Company(symbol="TEST", company_name="Test Corp", isin="IN1234567890",
                        exchange="NSE", market_cap=500_000_000_000))
    session.add(QuarterlyResult(
        symbol="TEST", fiscal_year=2026, quarter=1, revenue=100_000_000, cost_of_revenue=60_000_000,
        gross_profit=40_000_000, operating_expenses=20_000_000, operating_income=20_000_000,
        net_income=15_000_000, eps_basic=15.0, eps_diluted=14.5,
        gross_margin=0.40, operating_margin=0.20, net_margin=0.15,
        revenue_qoq_growth=0.05, revenue_yoy_growth=0.12,
        eps_qoq_growth=0.03, eps_yoy_growth=0.10,
        filing_date=date.today() - timedelta(days=30),
    ))
    await session.flush()


@pytest_asyncio.fixture
async def news_data(session: AsyncSession):
    today = date.today()
    for i in range(3):
        d = today - timedelta(days=i * 2)
        url = f"https://test.com/{i}"
        article = NewsArticle(
            symbol="TEST", title=f"Test article {i}",
            summary="Test summary", content="Test content",
            source="test", source_id=f"src_{i}", url=url,
            url_hash=hashlib.sha256(url.encode()).hexdigest(),
            published_at=datetime.combine(d, datetime.min.time()),
            language="en",
        )
        session.add(article)
        await session.flush()
        session.add(NewsNLPAnalysis(
            article_id=article.id,
            is_processed=True, processed_at=datetime.utcnow(),
            sentiment_label="positive" if i % 2 == 0 else "negative",
            sentiment_positive=0.8 if i % 2 == 0 else 0.3,
            sentiment_negative=0.1 if i % 2 == 0 else 0.6,
            sentiment_neutral=0.1,
            sentiment_confidence=0.9,
        ))
    await session.flush()


@pytest_asyncio.fixture
async def macro_data(session: AsyncSession):
    session.add(MacroIndicator(
        indicator_type="interest_rate", as_of_date=date.today() - timedelta(days=5),
        value=6.5, unit="%", source="RBI",
    ))
    session.add(MacroIndicator(
        indicator_type="inflation_rate", as_of_date=date.today() - timedelta(days=5),
        value=4.2, unit="%", source="MOSPI",
    ))
    session.add(MacroIndicator(
        indicator_type="gdp_growth", as_of_date=date.today() - timedelta(days=5),
        value=7.0, unit="%", source="MOSPI",
    ))
    await session.flush()


@pytest_asyncio.fixture
async def breadth_data(session: AsyncSession):
    today = date.today()
    base = today - timedelta(days=25)
    for i in range(20):
        d = base + timedelta(days=i)
        if d.weekday() < 5 and d <= today:
            session.add(MarketBreadth(
                trade_date=d, advancing=1500 + i * 10, declining=1200 - i * 5,
                unchanged=100, total_stocks=2800,
                advancing_volume=1_500_000_000 + i * 10_000_000,
                declining_volume=1_200_000_000 - i * 5_000_000,
                unchanged_volume=100_000_000,
                total_volume=2_800_000_000,
                new_highs=50 + i, new_lows=20 - i,
                advance_decline_ratio=1.25 + i * 0.01,
                advance_decline_line=300 + i * 5,
                volume_breadth_ratio=1.1,
                breadth_oscillator=0.5 + i * 0.02,
                index_strength_score=0.6,
            ))
    await session.flush()


# ============================================================
# DEFINITION MANAGEMENT
# ============================================================

class TestDefinitionManagement:
    @pytest.mark.asyncio
    async def test_register_feature(self, svc: FeatureEngineeringService):
        fd = await svc.register_feature("test_feature", "price", description="A test feature")
        assert fd.name == "test_feature"
        assert fd.category == "price"
        assert fd.version == "1.0.0"
        assert fd.is_active is True

    @pytest.mark.asyncio
    async def test_register_duplicate_returns_existing(self, svc: FeatureEngineeringService):
        fd1 = await svc.register_feature("dup_feat", "volume")
        fd2 = await svc.register_feature("dup_feat", "volume")
        assert fd1.id == fd2.id

    @pytest.mark.asyncio
    async def test_get_feature_definition(self, svc: FeatureEngineeringService):
        await svc.register_feature("get_test", "price")
        fd = await svc.get_feature_definition("get_test")
        assert fd is not None
        assert fd.name == "get_test"

    @pytest.mark.asyncio
    async def test_get_feature_definition_not_found(self, svc: FeatureEngineeringService):
        fd = await svc.get_feature_definition("nonexistent")
        assert fd is None

    @pytest.mark.asyncio
    async def test_list_definitions(self, svc: FeatureEngineeringService):
        await svc.register_feature("feat_a", "price")
        await svc.register_feature("feat_b", "volume")
        fds = await svc.list_definitions()
        assert len(fds) >= 2

    @pytest.mark.asyncio
    async def test_list_definitions_by_category(self, svc: FeatureEngineeringService):
        await svc.register_feature("price_feat", "price")
        await svc.register_feature("vol_feat", "volume")
        fds = await svc.list_definitions(category="price")
        assert all(f.category == "price" for f in fds)

    @pytest.mark.asyncio
    async def test_create_new_version(self, svc: FeatureEngineeringService):
        fd1 = await svc.register_feature("version_test", "price")
        fd2 = await svc.create_new_version("version_test")
        assert fd2.version == "1.0.1"
        assert fd2.is_active is True
        # old version deactivated
        assert fd1.is_active is False

    @pytest.mark.asyncio
    async def test_get_specific_version(self, svc: FeatureEngineeringService):
        await svc.register_feature("ver_spec", "price")
        await svc.create_new_version("ver_spec")
        v1 = await svc.get_feature_definition("ver_spec", version="1.0.0")
        v2 = await svc.get_feature_definition("ver_spec", version="1.0.1")
        assert v1 is not None
        assert v2 is not None
        assert v1.version == "1.0.0"
        assert v2.version == "1.0.1"


# ============================================================
# PRICE FEATURES
# ============================================================

class TestPriceFeatures:
    @pytest.mark.asyncio
    async def test_price_return_1d(self, svc: FeatureEngineeringService, price_data):
        results = await svc.compute_all_features("TEST")
        assert results["price"] > 0
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "price_return_1d")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None
        assert isinstance(fv.value, float)

    @pytest.mark.asyncio
    async def test_price_return_5d(self, svc: FeatureEngineeringService, price_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "price_return_5d")
        )
        assert r.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_price_return_20d(self, svc: FeatureEngineeringService, price_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "price_return_20d")
        )
        assert r.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_log_return_1d(self, svc: FeatureEngineeringService, price_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "log_return_1d")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None
        assert isinstance(fv.value, float)

    @pytest.mark.asyncio
    async def test_sma_20(self, svc: FeatureEngineeringService, price_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "sma_20")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None
        assert fv.value > 0

    @pytest.mark.asyncio
    async def test_sma_50(self, svc: FeatureEngineeringService, price_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "sma_50")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None
        assert fv.value > 0

    @pytest.mark.asyncio
    async def test_ema_12(self, svc: FeatureEngineeringService, price_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "ema_12")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None

    @pytest.mark.asyncio
    async def test_bollinger_width(self, svc: FeatureEngineeringService, price_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "bollinger_width")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None
        assert fv.value >= 0

    @pytest.mark.asyncio
    async def test_price_position(self, svc: FeatureEngineeringService, price_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "price_position")
        )
        assert r.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_price_features_count(self, svc: FeatureEngineeringService, price_data):
        results = await svc.compute_all_features("TEST")
        assert results["price"] >= 8  # most price features computed


# ============================================================
# VOLUME FEATURES
# ============================================================

class TestVolumeFeatures:
    @pytest.mark.asyncio
    async def test_volume_sma_5(self, svc: FeatureEngineeringService, price_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "volume_sma_5")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None and fv.value > 0

    @pytest.mark.asyncio
    async def test_volume_ratio_5(self, svc: FeatureEngineeringService, price_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "volume_ratio_5")
        )
        assert r.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_vwap_20(self, svc: FeatureEngineeringService, price_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "vwap_20")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None and fv.value > 0

    @pytest.mark.asyncio
    async def test_obv(self, svc: FeatureEngineeringService, price_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "obv")
        )
        assert r.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_volume_features_count(self, svc: FeatureEngineeringService, price_data):
        results = await svc.compute_all_features("TEST")
        assert results["volume"] >= 4


# ============================================================
# MOMENTUM FEATURES
# ============================================================

class TestMomentumFeatures:
    @pytest.mark.asyncio
    async def test_rsi_14(self, svc: FeatureEngineeringService, price_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "rsi_14")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None
        assert 0 <= fv.value <= 100

    @pytest.mark.asyncio
    async def test_macd(self, svc: FeatureEngineeringService, price_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "macd")
        )
        assert r.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_macd_signal(self, svc: FeatureEngineeringService, price_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "macd_signal")
        )
        assert r.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_stoch_k(self, svc: FeatureEngineeringService, price_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "stoch_k")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None
        assert 0 <= fv.value <= 100

    @pytest.mark.asyncio
    async def test_roc_10(self, svc: FeatureEngineeringService, price_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "roc_10")
        )
        assert r.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_momentum_features_count(self, svc: FeatureEngineeringService, price_data):
        results = await svc.compute_all_features("TEST")
        assert results["momentum"] >= 4


# ============================================================
# VOLATILITY FEATURES
# ============================================================

class TestVolatilityFeatures:
    @pytest.mark.asyncio
    async def test_historical_vol_20(self, svc: FeatureEngineeringService, price_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "historical_vol_20")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None
        assert fv.value >= 0

    @pytest.mark.asyncio
    async def test_historical_vol_60(self, svc: FeatureEngineeringService, price_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "historical_vol_60")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None

    @pytest.mark.asyncio
    async def test_atr_14(self, svc: FeatureEngineeringService, price_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "atr_14")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None
        assert fv.value >= 0

    @pytest.mark.asyncio
    async def test_high_low_range_14(self, svc: FeatureEngineeringService, price_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "high_low_range_14")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None
        assert fv.value >= 0

    @pytest.mark.asyncio
    async def test_parkinson_vol_20(self, svc: FeatureEngineeringService, price_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "parkinson_vol_20")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None

    @pytest.mark.asyncio
    async def test_volatility_features_count(self, svc: FeatureEngineeringService, price_data):
        results = await svc.compute_all_features("TEST")
        assert results["volatility"] >= 3  # at least some computed


# ============================================================
# FINANCIAL FEATURES
# ============================================================

class TestFinancialFeatures:
    @pytest.mark.asyncio
    async def test_eps_diluted(self, svc: FeatureEngineeringService, price_data, financial_data):
        results = await svc.compute_all_features("TEST")
        assert results["financial"] > 0
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "eps_diluted")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None
        assert fv.value == 14.5

    @pytest.mark.asyncio
    async def test_pe_ratio(self, svc: FeatureEngineeringService, price_data, financial_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "pe_ratio")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None
        assert fv.value > 0

    @pytest.mark.asyncio
    async def test_market_cap_crore(self, svc: FeatureEngineeringService, price_data, financial_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "market_cap_crore")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None
        assert fv.value == 50000.0  # 500B / 1e7

    @pytest.mark.asyncio
    async def test_revenue_growth_yoy(self, svc: FeatureEngineeringService, price_data, financial_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "revenue_growth_yoy")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None
        assert abs(fv.value - 0.12) < 0.001

    @pytest.mark.asyncio
    async def test_financial_features_count(self, svc: FeatureEngineeringService, price_data, financial_data):
        results = await svc.compute_all_features("TEST")
        assert results["financial"] >= 4


# ============================================================
# NEWS FEATURES
# ============================================================

class TestNewsFeatures:
    @pytest.mark.asyncio
    async def test_news_count_7d(self, svc: FeatureEngineeringService, news_data):
        results = await svc.compute_all_features("TEST")
        assert results["news"] > 0
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "news_count_7d")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None
        assert fv.value >= 1

    @pytest.mark.asyncio
    async def test_sentiment_score_7d(self, svc: FeatureEngineeringService, news_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "sentiment_score_7d")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None
        assert 0 <= fv.value <= 1

    @pytest.mark.asyncio
    async def test_positive_news_ratio_7d(self, svc: FeatureEngineeringService, news_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "positive_news_ratio_7d")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None
        assert 0 <= fv.value <= 1

    @pytest.mark.asyncio
    async def test_avg_sentiment_confidence(self, svc: FeatureEngineeringService, news_data):
        await svc.compute_all_features("TEST")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "avg_sentiment_confidence")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None


# ============================================================
# MACRO FEATURES
# ============================================================

class TestMacroFeatures:
    @pytest.mark.asyncio
    async def test_interest_rate(self, svc: FeatureEngineeringService, macro_data):
        results = await svc.compute_all_features("SYMBOL")  # symbol doesn't matter for macro
        assert results["macro"] > 0
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "interest_rate")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None
        assert fv.value == 6.5

    @pytest.mark.asyncio
    async def test_inflation_rate(self, svc: FeatureEngineeringService, macro_data):
        await svc.compute_all_features("SYMBOL")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "inflation_rate")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None
        assert fv.value == 4.2

    @pytest.mark.asyncio
    async def test_gdp_growth(self, svc: FeatureEngineeringService, macro_data):
        await svc.compute_all_features("SYMBOL")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "gdp_growth")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None
        assert fv.value == 7.0

    @pytest.mark.asyncio
    async def test_macro_features_count(self, svc: FeatureEngineeringService, macro_data):
        results = await svc.compute_all_features("SYMBOL")
        assert results["macro"] >= 3


# ============================================================
# MARKET BREADTH FEATURES
# ============================================================

class TestBreadthFeatures:
    @pytest.mark.asyncio
    async def test_advance_decline_ratio(self, svc: FeatureEngineeringService, breadth_data):
        results = await svc.compute_all_features("SYMBOL")
        assert results["breadth"] > 0
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "advance_decline_ratio")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None
        assert fv.value > 0

    @pytest.mark.asyncio
    async def test_new_highs_lows_ratio(self, svc: FeatureEngineeringService, breadth_data):
        await svc.compute_all_features("SYMBOL")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "new_highs_lows_ratio")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None
        assert fv.value > 0

    @pytest.mark.asyncio
    async def test_breadth_oscillator(self, svc: FeatureEngineeringService, breadth_data):
        await svc.compute_all_features("SYMBOL")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "breadth_oscillator")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None

    @pytest.mark.asyncio
    async def test_advance_decline_line(self, svc: FeatureEngineeringService, breadth_data):
        await svc.compute_all_features("SYMBOL")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "advance_decline_line")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None

    @pytest.mark.asyncio
    async def test_breadth_momentum_5d(self, svc: FeatureEngineeringService, breadth_data):
        await svc.compute_all_features("SYMBOL")
        r = await svc.session.execute(
            select(FeatureValue).join(FeatureDefinition)
            .where(FeatureDefinition.name == "breadth_momentum_5d")
        )
        fv = r.scalar_one_or_none()
        assert fv is not None

    @pytest.mark.asyncio
    async def test_breadth_features_count(self, svc: FeatureEngineeringService, breadth_data):
        results = await svc.compute_all_features("SYMBOL")
        assert results["breadth"] >= 3


# ============================================================
# COMPUTE SINGLE FEATURE
# ============================================================

class TestComputeSingleFeature:
    @pytest.mark.asyncio
    async def test_compute_single_price_feature(self, svc: FeatureEngineeringService, price_data):
        # First register the definition
        await svc.register_feature("price_return_1d", "price")
        value = await svc.compute_feature("price_return_1d", "TEST")
        assert value is not None
        assert isinstance(value, float)

    @pytest.mark.asyncio
    async def test_compute_single_unknown_feature(self, svc: FeatureEngineeringService):
        value = await svc.compute_feature("nonexistent", "TEST")
        assert value is None


# ============================================================
# VALUE QUERIES
# ============================================================

class TestValueQueries:
    @pytest.mark.asyncio
    async def test_get_values_by_symbol(self, svc: FeatureEngineeringService, price_data):
        await svc.compute_all_features("TEST")
        values = await svc.get_values(symbol="TEST")
        assert len(values) > 0
        assert all(v.symbol == "TEST" for v in values)

    @pytest.mark.asyncio
    async def test_get_values_by_feature(self, svc: FeatureEngineeringService, price_data):
        await svc.compute_all_features("TEST")
        values = await svc.get_values(feature_name="sma_20")
        assert len(values) > 0

    @pytest.mark.asyncio
    async def test_get_values_by_category(self, svc: FeatureEngineeringService, price_data):
        await svc.compute_all_features("TEST")
        values = await svc.get_values(category="price")
        assert len(values) > 0
        assert all(v.definition.category == "price" for v in values)

    @pytest.mark.asyncio
    async def test_get_values_empty(self, svc: FeatureEngineeringService):
        values = await svc.get_values(symbol="NONEXISTENT")
        assert len(values) == 0


# ============================================================
# CLEAR OLD VALUES
# ============================================================

class TestClearOldValues:
    @pytest.mark.asyncio
    async def test_clear_old_values(self, svc: FeatureEngineeringService, price_data):
        await svc.compute_all_features("TEST")
        deleted = await svc.clear_old_values(older_than_days=0)
        assert deleted >= 0


# ============================================================
# EDGE CASES
# ============================================================

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_no_data_no_crash(self, svc: FeatureEngineeringService):
        results = await svc.compute_all_features("EMPTY")
        for category, count in results.items():
            assert count >= 0

    @pytest.mark.asyncio
    async def test_insufficient_price_data(self, svc: FeatureEngineeringService, session: AsyncSession):
        today = date.today()
        if today.weekday() < 5:
            session.add(DailyPrice(symbol="FEW", trade_date=today, open=100, high=101, low=99, close=100.5, volume=1_000_000))
        await session.flush()
        results = await svc.compute_all_features("FEW")
        # Most features need more data, so counts should be 0 or low
        assert results["price"] <= 1

    @pytest.mark.asyncio
    async def test_upsert_same_value_twice(self, svc: FeatureEngineeringService, price_data):
        results1 = await svc.compute_all_features("TEST")
        results2 = await svc.compute_all_features("TEST")
        # Second compute should upsert, not fail
        assert results2["price"] >= 0

    @pytest.mark.asyncio
    async def test_compute_all_returns_all_categories(self, svc: FeatureEngineeringService):
        results = await svc.compute_all_features("EMPTY")
        assert set(results.keys()) == {
            "price", "volume", "momentum", "volatility",
            "financial", "news", "macro", "breadth",
        }

    @pytest.mark.asyncio
    async def test_feature_definition_version_default(self, svc: FeatureEngineeringService):
        fd = await svc.register_feature("default_version_test", "price")
        assert fd.version == "1.0.0"
