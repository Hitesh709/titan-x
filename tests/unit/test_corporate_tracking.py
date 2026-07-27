import json
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.corporate_tracking import (
    CorporateAnalysis,
    InsiderTrade,
    PromoterTransaction,
    ShareholdingPattern,
)
from titan_x.services.corporate_tracking_service import CorporateTrackingService


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///")

    from sqlalchemy import event
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
async def company(session: AsyncSession) -> Company:
    c = Company(symbol="TEST", company_name="Test Corp", isin="IN00001", exchange="NSE", sector="Technology")
    session.add(c)
    await session.flush()
    return c


@pytest_asyncio.fixture
def svc(session: AsyncSession) -> CorporateTrackingService:
    return CorporateTrackingService(session)


# ============================================================
# PROMOTER TRANSACTION CRUD
# ============================================================

class TestPromoterTransactionCRUD:
    @pytest.mark.asyncio
    async def test_create(self, svc: CorporateTrackingService, company: Company):
        result = await svc.create_promoter_transaction(
            company_id=company.id, promoter_name="Founder",
            transaction_type="buy", quantity=1000, price=150.0,
            transaction_date=date.today(),
        )
        assert result.promoter_name == "Founder"
        assert result.transaction_type == "buy"
        assert result.value == 150000.0

    @pytest.mark.asyncio
    async def test_create_sell(self, svc: CorporateTrackingService, company: Company):
        result = await svc.create_promoter_transaction(
            company_id=company.id, promoter_name="Founder",
            transaction_type="sell", quantity=500, price=200.0,
            transaction_date=date.today(),
        )
        assert result.transaction_type == "sell"
        assert result.value == 100000.0

    @pytest.mark.asyncio
    async def test_get(self, svc: CorporateTrackingService, company: Company):
        created = await svc.create_promoter_transaction(
            company_id=company.id, promoter_name="P1",
            transaction_type="buy", quantity=100, price=50.0,
            transaction_date=date.today(),
        )
        result = await svc.get_promoter_transaction(created.id)
        assert result is not None
        assert result.id == created.id

    @pytest.mark.asyncio
    async def test_get_not_found(self, svc: CorporateTrackingService):
        assert await svc.get_promoter_transaction(9999) is None

    @pytest.mark.asyncio
    async def test_list(self, svc: CorporateTrackingService, company: Company):
        for i in range(3):
            await svc.create_promoter_transaction(
                company_id=company.id, promoter_name=f"P{i}",
                transaction_type="buy", quantity=100, price=50.0,
                transaction_date=date.today(),
            )
        rows, total = await svc.list_promoter_transactions()
        assert total == 3

    @pytest.mark.asyncio
    async def test_list_filtered(self, svc: CorporateTrackingService, company: Company):
        await svc.create_promoter_transaction(
            company_id=company.id, promoter_name="P1",
            transaction_type="buy", quantity=100, price=50.0,
            transaction_date=date.today(),
        )
        await svc.create_promoter_transaction(
            company_id=company.id, promoter_name="P2",
            transaction_type="sell", quantity=50, price=60.0,
            transaction_date=date.today(),
        )
        rows, total = await svc.list_promoter_transactions(transaction_type="sell")
        assert total == 1

    @pytest.mark.asyncio
    async def test_update(self, svc: CorporateTrackingService, company: Company):
        created = await svc.create_promoter_transaction(
            company_id=company.id, promoter_name="Old",
            transaction_type="buy", quantity=100, price=50.0,
            transaction_date=date.today(),
        )
        result = await svc.update_promoter_transaction(created.id, quantity=200)
        assert result is not None
        assert result.quantity == 200

    @pytest.mark.asyncio
    async def test_delete(self, svc: CorporateTrackingService, company: Company):
        created = await svc.create_promoter_transaction(
            company_id=company.id, promoter_name="Del",
            transaction_type="buy", quantity=100, price=50.0,
            transaction_date=date.today(),
        )
        assert await svc.delete_promoter_transaction(created.id) is True
        assert await svc.get_promoter_transaction(created.id) is None

    @pytest.mark.asyncio
    async def test_delete_not_found(self, svc: CorporateTrackingService):
        assert await svc.delete_promoter_transaction(9999) is False


# ============================================================
# INSIDER TRADE CRUD
# ============================================================

class TestInsiderTradeCRUD:
    @pytest.mark.asyncio
    async def test_create(self, svc: CorporateTrackingService, company: Company):
        result = await svc.create_insider_trade(
            company_id=company.id, insider_name="Director A",
            designation="CEO", transaction_type="buy",
            quantity=500, price=100.0, transaction_date=date.today(),
        )
        assert result.insider_name == "Director A"
        assert result.value == 50000.0

    @pytest.mark.asyncio
    async def test_create_derivative(self, svc: CorporateTrackingService, company: Company):
        result = await svc.create_insider_trade(
            company_id=company.id, insider_name="Director B",
            transaction_type="sell", quantity=1000, price=80.0,
            transaction_date=date.today(),
            is_derivative=True, derivative_type="stock_option",
            exercise_price=50.0,
        )
        assert result.is_derivative is True
        assert result.derivative_type == "stock_option"

    @pytest.mark.asyncio
    async def test_list_filtered(self, svc: CorporateTrackingService, company: Company):
        await svc.create_insider_trade(
            company_id=company.id, insider_name="I1",
            transaction_type="buy", quantity=100, price=50.0,
            transaction_date=date.today(),
        )
        await svc.create_insider_trade(
            company_id=company.id, insider_name="I2",
            transaction_type="sell", quantity=200, price=55.0,
            transaction_date=date.today(),
        )
        rows, total = await svc.list_insider_trades(transaction_type="buy")
        assert total == 1

    @pytest.mark.asyncio
    async def test_update(self, svc: CorporateTrackingService, company: Company):
        created = await svc.create_insider_trade(
            company_id=company.id, insider_name="Old",
            transaction_type="buy", quantity=100, price=50.0,
            transaction_date=date.today(),
        )
        result = await svc.update_insider_trade(created.id, quantity=300)
        assert result.quantity == 300

    @pytest.mark.asyncio
    async def test_delete(self, svc: CorporateTrackingService, company: Company):
        created = await svc.create_insider_trade(
            company_id=company.id, insider_name="Del",
            transaction_type="buy", quantity=100, price=50.0,
            transaction_date=date.today(),
        )
        assert await svc.delete_insider_trade(created.id) is True


# ============================================================
# SHAREHOLDING PATTERN CRUD
# ============================================================

class TestShareholdingPatternCRUD:
    @pytest.mark.asyncio
    async def test_create(self, svc: CorporateTrackingService, company: Company):
        result = await svc.create_shareholding_pattern(
            company_id=company.id, filing_date=date(2025, 6, 30),
            quarter=1, year=2025, category="promoter",
            shares_held=1000000, percentage=65.0, change_percentage=1.5,
        )
        assert result.category == "promoter"
        assert result.percentage == 65.0

    @pytest.mark.asyncio
    async def test_list_filtered(self, svc: CorporateTrackingService, company: Company):
        await svc.create_shareholding_pattern(
            company_id=company.id, filing_date=date(2025, 3, 31),
            quarter=4, year=2024, category="promoter",
            percentage=60.0,
        )
        await svc.create_shareholding_pattern(
            company_id=company.id, filing_date=date(2025, 6, 30),
            quarter=1, year=2025, category="fii",
            percentage=15.0,
        )
        rows, total = await svc.list_shareholding_patterns(category="promoter")
        assert total == 1

    @pytest.mark.asyncio
    async def test_update(self, svc: CorporateTrackingService, company: Company):
        created = await svc.create_shareholding_pattern(
            company_id=company.id, filing_date=date(2025, 6, 30),
            quarter=1, year=2025, category="promoter",
            percentage=60.0,
        )
        result = await svc.update_shareholding_pattern(created.id, percentage=65.0)
        assert result.percentage == 65.0

    @pytest.mark.asyncio
    async def test_delete(self, svc: CorporateTrackingService, company: Company):
        created = await svc.create_shareholding_pattern(
            company_id=company.id, filing_date=date(2025, 6, 30),
            quarter=1, year=2025, category="promoter",
            percentage=60.0,
        )
        assert await svc.delete_shareholding_pattern(created.id) is True


# ============================================================
# AI: PROMOTER ACTIVITY ANALYSIS
# ============================================================

class TestPromoterAnalysis:
    @pytest.mark.asyncio
    async def test_no_transactions(self, svc: CorporateTrackingService, company: Company):
        result = await svc.analyze_promoter_activity(company.id)
        assert result["buying_score"] == 50.0
        assert result["selling_score"] == 50.0
        assert result["total_transactions"] == 0
        assert "No promoter transactions" in result["insights"][0]

    @pytest.mark.asyncio
    async def test_all_buys(self, svc: CorporateTrackingService, company: Company):
        for i in range(5):
            await svc.create_promoter_transaction(
                company_id=company.id, promoter_name="Founder",
                transaction_type="buy", quantity=1000, price=100.0 + i,
                transaction_date=date.today() - timedelta(days=i * 10),
            )
        result = await svc.analyze_promoter_activity(company.id)
        assert result["buying_score"] > result["selling_score"]
        assert result["net_flow"] > 0
        assert result["buy_count"] == 5
        assert result["sell_count"] == 0

    @pytest.mark.asyncio
    async def test_all_sells(self, svc: CorporateTrackingService, company: Company):
        for i in range(3):
            await svc.create_promoter_transaction(
                company_id=company.id, promoter_name="Founder",
                transaction_type="sell", quantity=500, price=200.0 + i,
                transaction_date=date.today() - timedelta(days=i * 5),
            )
        result = await svc.analyze_promoter_activity(company.id)
        assert result["selling_score"] > result["buying_score"]
        assert result["net_flow"] < 0

    @pytest.mark.asyncio
    async def test_mixed_activity(self, svc: CorporateTrackingService, company: Company):
        await svc.create_promoter_transaction(
            company_id=company.id, promoter_name="Founder",
            transaction_type="buy", quantity=10000, price=100.0,
            transaction_date=date.today() - timedelta(days=30),
        )
        await svc.create_promoter_transaction(
            company_id=company.id, promoter_name="Founder",
            transaction_type="sell", quantity=2000, price=120.0,
            transaction_date=date.today() - timedelta(days=5),
        )
        result = await svc.analyze_promoter_activity(company.id)
        assert result["net_flow"] > 0
        assert result["cluster_buying"] is True or result["cluster_buying"] is False

    @pytest.mark.asyncio
    async def test_multiple_promoters(self, svc: CorporateTrackingService, company: Company):
        for name in ["P1", "P2", "P3"]:
            await svc.create_promoter_transaction(
                company_id=company.id, promoter_name=name,
                transaction_type="buy", quantity=500, price=100.0,
                transaction_date=date.today() - timedelta(days=10),
            )
        result = await svc.analyze_promoter_activity(company.id)
        assert result["unique_buy_promoters"] == 3
        assert result["cluster_buying"] is True

    @pytest.mark.asyncio
    async def test_date_filtered(self, svc: CorporateTrackingService, company: Company):
        old = date.today() - timedelta(days=400)
        await svc.create_promoter_transaction(
            company_id=company.id, promoter_name="Old",
            transaction_type="buy", quantity=1000, price=50.0,
            transaction_date=old,
        )
        result = await svc.analyze_promoter_activity(company.id)
        assert result["total_transactions"] == 0


# ============================================================
# AI: INSIDER SENTIMENT ANALYSIS
# ============================================================

class TestInsiderSentimentAnalysis:
    @pytest.mark.asyncio
    async def test_no_trades(self, svc: CorporateTrackingService, company: Company):
        result = await svc.analyze_insider_sentiment(company.id)
        assert result["sentiment_score"] == 50.0
        assert result["total_trades"] == 0

    @pytest.mark.asyncio
    async def test_bullish_sentiment(self, svc: CorporateTrackingService, company: Company):
        for i in range(5):
            await svc.create_insider_trade(
                company_id=company.id, insider_name="CEO",
                designation="CEO", transaction_type="buy",
                quantity=1000, price=100.0,
                transaction_date=date.today() - timedelta(days=i),
            )
        result = await svc.analyze_insider_sentiment(company.id)
        assert result["sentiment_score"] > 70
        assert result["buy_count"] == 5
        assert result["sell_count"] == 0

    @pytest.mark.asyncio
    async def test_bearish_sentiment(self, svc: CorporateTrackingService, company: Company):
        for i in range(3):
            await svc.create_insider_trade(
                company_id=company.id, insider_name="Director",
                designation="Director", transaction_type="sell",
                quantity=5000, price=150.0,
                transaction_date=date.today() - timedelta(days=i * 2),
            )
        result = await svc.analyze_insider_sentiment(company.id)
        assert result["sentiment_score"] < 40

    @pytest.mark.asyncio
    async def test_designation_weighting(self, svc: CorporateTrackingService, company: Company):
        await svc.create_insider_trade(
            company_id=company.id, insider_name="CEO",
            designation="CEO", transaction_type="buy",
            quantity=1000, price=100.0, transaction_date=date.today(),
        )
        await svc.create_insider_trade(
            company_id=company.id, insider_name="Employee",
            designation="Employee", transaction_type="sell",
            quantity=10000, price=100.0, transaction_date=date.today(),
        )
        result = await svc.analyze_insider_sentiment(company.id)
        assert result["sentiment_score"] > 0

    @pytest.mark.asyncio
    async def test_derivative_trades(self, svc: CorporateTrackingService, company: Company):
        await svc.create_insider_trade(
            company_id=company.id, insider_name="Director",
            designation="Director", transaction_type="buy",
            quantity=1000, price=100.0, transaction_date=date.today(),
            is_derivative=True, derivative_type="stock_option",
        )
        result = await svc.analyze_insider_sentiment(company.id)
        assert result["derivative_trades"] == 1

    @pytest.mark.asyncio
    async def test_unusual_clustering(self, svc: CorporateTrackingService, company: Company):
        today = date.today()
        await svc.create_insider_trade(
            company_id=company.id, insider_name="D1",
            designation="Director", transaction_type="buy",
            quantity=1000, price=100.0, transaction_date=today,
        )
        await svc.create_insider_trade(
            company_id=company.id, insider_name="D2",
            designation="Director", transaction_type="sell",
            quantity=2000, price=101.0, transaction_date=today + timedelta(days=1),
        )
        await svc.create_insider_trade(
            company_id=company.id, insider_name="D3",
            designation="Director", transaction_type="buy",
            quantity=1500, price=102.0, transaction_date=today + timedelta(days=2),
        )
        result = await svc.analyze_insider_sentiment(company.id)
        assert result["total_trades"] == 3


# ============================================================
# AI: SHAREHOLDING TREND ANALYSIS
# ============================================================

class TestShareholdingTrendAnalysis:
    @pytest.mark.asyncio
    async def test_no_data(self, svc: CorporateTrackingService, company: Company):
        result = await svc.analyze_shareholding_trends(company.id)
        assert result["trend_score"] == 50.0
        assert result["total_records"] == 0

    @pytest.mark.asyncio
    async def test_promoter_increasing(self, svc: CorporateTrackingService, company: Company):
        await svc.create_shareholding_pattern(
            company_id=company.id, filing_date=date(2024, 12, 31),
            quarter=4, year=2024, category="promoter",
            percentage=60.0,
        )
        await svc.create_shareholding_pattern(
            company_id=company.id, filing_date=date(2025, 3, 31),
            quarter=1, year=2025, category="promoter",
            percentage=62.0, change_percentage=2.0,
        )
        await svc.create_shareholding_pattern(
            company_id=company.id, filing_date=date(2025, 6, 30),
            quarter=2, year=2025, category="promoter",
            percentage=65.0, change_percentage=3.0,
        )
        result = await svc.analyze_shareholding_trends(company.id)
        assert result["trend_score"] > 55
        assert result["category_trends"]["promoter"]["direction"] == "increasing"

    @pytest.mark.asyncio
    async def test_promoter_decreasing(self, svc: CorporateTrackingService, company: Company):
        await svc.create_shareholding_pattern(
            company_id=company.id, filing_date=date(2024, 12, 31),
            quarter=4, year=2024, category="promoter",
            percentage=65.0,
        )
        await svc.create_shareholding_pattern(
            company_id=company.id, filing_date=date(2025, 3, 31),
            quarter=1, year=2025, category="promoter",
            percentage=60.0,
        )
        result = await svc.analyze_shareholding_trends(company.id)
        assert result["category_trends"]["promoter"]["direction"] == "decreasing"
        assert result["trend_score"] < 50

    @pytest.mark.asyncio
    async def test_multiple_categories(self, svc: CorporateTrackingService, company: Company):
        for cat in ["promoter", "fii", "dii", "retail"]:
            await svc.create_shareholding_pattern(
                company_id=company.id, filing_date=date(2025, 6, 30),
                quarter=1, year=2025, category=cat,
                percentage={"promoter": 60, "fii": 15, "dii": 12, "retail": 13}[cat],
            )
        result = await svc.analyze_shareholding_trends(company.id)
        assert len(result["categories_analyzed"]) == 4

    @pytest.mark.asyncio
    async def test_promoter_fii_convergence(self, svc: CorporateTrackingService, company: Company):
        await svc.create_shareholding_pattern(
            company_id=company.id, filing_date=date(2024, 12, 31),
            quarter=4, year=2024, category="promoter", percentage=60.0,
        )
        await svc.create_shareholding_pattern(
            company_id=company.id, filing_date=date(2025, 6, 30),
            quarter=2, year=2025, category="promoter", percentage=63.0,
        )
        await svc.create_shareholding_pattern(
            company_id=company.id, filing_date=date(2024, 12, 31),
            quarter=4, year=2024, category="fii", percentage=12.0,
        )
        await svc.create_shareholding_pattern(
            company_id=company.id, filing_date=date(2025, 6, 30),
            quarter=2, year=2025, category="fii", percentage=15.0,
        )
        result = await svc.analyze_shareholding_trends(company.id)
        assert result["trend_score"] >= 50


# ============================================================
# AI: FULL CORPORATE ANALYSIS
# ============================================================

class TestCorporateAnalysis:
    @pytest.mark.asyncio
    async def test_generate_analysis(self, svc: CorporateTrackingService, company: Company):
        result = await svc.generate_analysis(company.id)
        assert result.company_id == company.id
        assert result.analysis_date == date.today()
        assert result.weighted_score is not None
        assert result.signal in ("strong_buy", "buy", "hold", "sell", "strong_sell")
        assert result.confidence is not None

    @pytest.mark.asyncio
    async def test_generate_with_data(self, svc: CorporateTrackingService, company: Company):
        await svc.create_promoter_transaction(
            company_id=company.id, promoter_name="Founder",
            transaction_type="buy", quantity=10000, price=100.0,
            transaction_date=date.today() - timedelta(days=5),
        )
        await svc.create_insider_trade(
            company_id=company.id, insider_name="CEO",
            designation="CEO", transaction_type="buy",
            quantity=5000, price=100.0,
            transaction_date=date.today() - timedelta(days=3),
        )
        await svc.create_shareholding_pattern(
            company_id=company.id, filing_date=date(2025, 6, 30),
            quarter=1, year=2025, category="promoter",
            percentage=65.0,
        )
        result = await svc.generate_analysis(company.id)
        insights = json.loads(result.insights_json)
        assert len(insights["insights"]) > 0
        assert result.weighted_score >= 0
        assert result.confidence >= 0

    @pytest.mark.asyncio
    async def test_get_latest(self, svc: CorporateTrackingService, company: Company):
        await svc.generate_analysis(company.id)
        latest = await svc.get_latest_analysis(company.id)
        assert latest is not None
        assert latest.company_id == company.id

    @pytest.mark.asyncio
    async def test_list_analyses(self, svc: CorporateTrackingService, company: Company):
        await svc.generate_analysis(company.id)
        rows, total = await svc.list_analyses()
        assert total == 1

    @pytest.mark.asyncio
    async def test_list_by_signal(self, svc: CorporateTrackingService, company: Company):
        result = await svc.generate_analysis(company.id)
        rows, total = await svc.list_analyses(signal=result.signal)
        assert total == 1

    @pytest.mark.asyncio
    async def test_get_analysis(self, svc: CorporateTrackingService, company: Company):
        created = await svc.generate_analysis(company.id)
        result = await svc.get_analysis(created.id)
        assert result is not None
        assert result.id == created.id

    @pytest.mark.asyncio
    async def test_delete_analysis(self, svc: CorporateTrackingService, company: Company):
        created = await svc.generate_analysis(company.id)
        assert await svc.delete_analysis(created.id) is True
        assert await svc.get_analysis(created.id) is None

    @pytest.mark.asyncio
    async def test_signal_computation(self, svc: CorporateTrackingService):
        assert svc._compute_signal(85) == "strong_buy"
        assert svc._compute_signal(70) == "buy"
        assert svc._compute_signal(55) == "hold"
        assert svc._compute_signal(35) == "sell"
        assert svc._compute_signal(20) == "strong_sell"


# ============================================================
# EDGE CASES
# ============================================================

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_promoter_transaction_auto_value(self, svc: CorporateTrackingService, company: Company):
        r = await svc.create_promoter_transaction(
            company_id=company.id, promoter_name="P",
            transaction_type="buy", quantity=100, price=200.0,
            transaction_date=date.today(),
        )
        assert r.value == 20000.0

    @pytest.mark.asyncio
    async def test_insider_trade_auto_value(self, svc: CorporateTrackingService, company: Company):
        r = await svc.create_insider_trade(
            company_id=company.id, insider_name="I",
            transaction_type="buy", quantity=50, price=500.0,
            transaction_date=date.today(),
        )
        assert r.value == 25000.0

    @pytest.mark.asyncio
    async def test_promoter_update_value(self, svc: CorporateTrackingService, company: Company):
        r = await svc.create_promoter_transaction(
            company_id=company.id, promoter_name="P",
            transaction_type="buy", quantity=100, price=50.0,
            value=5000.0, transaction_date=date.today(),
        )
        updated = await svc.update_promoter_transaction(r.id, quantity=200)
        assert updated.value == 5000.0

    @pytest.mark.asyncio
    async def test_insider_update_no_value_recalc(self, svc: CorporateTrackingService, company: Company):
        r = await svc.create_insider_trade(
            company_id=company.id, insider_name="I",
            transaction_type="buy", quantity=100, price=50.0,
            transaction_date=date.today(),
        )
        updated = await svc.update_insider_trade(r.id, quantity=200)
        assert updated.value == 5000.0
