import json

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from titan_x.db.base import Base
from titan_x.models.feature_store import (
    FeatureLineage,
    FeatureOfflineStore,
    FeatureStoreDef,
    FeatureStoreEntity,
    FeatureStoreValue,
    FeatureValidationResult,
    FeatureValidationRule,
    FeatureVersion,
)
from titan_x.services.feature_store_service import FeatureStoreService

ASYNC_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(ASYNC_DB_URL, echo=False)

    @sa_event.listens_for(eng.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s


pytestmark = pytest.mark.asyncio


# ── Entities ──

class TestEntities:
    async def test_create_entity(self, session):
        svc = FeatureStoreService(session)
        e = await svc.create_entity("stock", description="Stock features", metadata={"source": "nse"})
        assert e.id is not None
        assert e.name == "stock"
        assert e.status == "active"

    async def test_get_entity(self, session):
        svc = FeatureStoreService(session)
        e = await svc.create_entity("test_entity")
        got = await svc.get_entity(e.id)
        assert got is not None and got.id == e.id

    async def test_get_entity_by_name(self, session):
        svc = FeatureStoreService(session)
        await svc.create_entity("find_me")
        got = await svc.get_entity_by_name("find_me")
        assert got is not None and got.name == "find_me"

    async def test_get_entity_by_name_not_found(self, session):
        svc = FeatureStoreService(session)
        assert await svc.get_entity_by_name("nonexistent") is None

    async def test_list_entities(self, session):
        svc = FeatureStoreService(session)
        await svc.create_entity("a")
        await svc.create_entity("b")
        items = await svc.list_entities()
        assert len(items) == 2


# ── Feature Definitions ──

class TestFeatureDefinitions:
    async def test_create_feature(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(
            ent.id, "close_price",
            display_name="Close Price",
            feature_type="numerical",
            source="daily_price",
            tags=["price", "core"],
            is_online=True, is_offline=True,
        )
        assert fd.id is not None
        assert fd.name == "close_price"
        assert fd.feature_type == "numerical"
        assert fd.is_online is True
        assert fd.is_offline is True
        assert fd.immutable is False

    async def test_create_feature_immutable(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "isin", immutable=True)
        assert fd.immutable is True

    async def test_get_feature(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("e")
        fd = await svc.create_feature(ent.id, "f")
        got = await svc.get_feature(fd.id)
        assert got is not None and got.id == fd.id

    async def test_get_feature_by_name(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        await svc.create_feature(ent.id, "volume")
        got = await svc.get_feature_by_name(ent.id, "volume")
        assert got is not None and got.name == "volume"

    async def test_list_features(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        await svc.create_feature(ent.id, "open")
        await svc.create_feature(ent.id, "high")
        items = await svc.list_features(entity_id=ent.id)
        assert len(items) == 2

    async def test_list_features_filter_type(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        await svc.create_feature(ent.id, "close", feature_type="numerical")
        await svc.create_feature(ent.id, "sector", feature_type="categorical")
        items = await svc.list_features(feature_type="categorical")
        assert len(items) == 1
        assert items[0].name == "sector"

    async def test_update_feature(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "test_feat")
        updated = await svc.update_feature(fd.id, display_name="Updated Name", tags=["tag1"])
        assert updated is not None
        assert updated.display_name == "Updated Name"
        assert "tag1" in (json.loads(updated.tags_json) if updated.tags_json else [])

    async def test_update_feature_not_found(self, session):
        svc = FeatureStoreService(session)
        assert await svc.update_feature(9999, display_name="x") is None


# ── Versions ──

class TestVersions:
    async def test_create_version(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "close")
        fv = await svc.create_version(fd.id, "2.0.0", change_log="Added scaling")
        assert fv.id is not None
        assert fv.version == "2.0.0"
        assert fv.change_log == "Added scaling"

    async def test_initial_version_auto_created(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "volume")
        versions = await svc.list_versions(fd.id)
        assert len(versions) == 1
        assert versions[0].version == "1.0.0"

    async def test_list_versions(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "close")
        await svc.create_version(fd.id, "2.0.0")
        await svc.create_version(fd.id, "3.0.0")
        items = await svc.list_versions(fd.id)
        assert len(items) == 3


# ── Online Store ──

class TestOnlineStore:
    async def test_set_and_get_value(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "close")
        await svc.set_online_value(fd.id, "AAPL", "150.25", value_type="numerical")
        value = await svc.get_online_value(fd.id, "AAPL")
        assert value == "150.25"

    async def test_get_value_not_found(self, session):
        svc = FeatureStoreService(session)
        assert await svc.get_online_value(1, "NONEXIST") is None

    async def test_set_overwrites_existing(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "close")
        await svc.set_online_value(fd.id, "AAPL", "100")
        await svc.set_online_value(fd.id, "AAPL", "200")
        value = await svc.get_online_value(fd.id, "AAPL")
        assert value == "200"

    async def test_ttl_expiry(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "close")
        await svc.set_online_value(fd.id, "AAPL", "150", ttl_seconds=0)
        value = await svc.get_online_value(fd.id, "AAPL")
        assert value is None

    async def test_get_online_features(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        f1 = await svc.create_feature(ent.id, "close")
        f2 = await svc.create_feature(ent.id, "volume")
        await svc.set_online_value(f1.id, "AAPL", "150")
        await svc.set_online_value(f2.id, "AAPL", "1000000")
        result = await svc.get_online_features([f1.id, f2.id, 9999], "AAPL")
        assert result[f1.id] == "150"
        assert result[f2.id] == "1000000"
        assert result[9999] is None

    async def test_delete_online_value(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "close")
        await svc.set_online_value(fd.id, "AAPL", "150")
        ok = await svc.delete_online_value(fd.id, "AAPL")
        assert ok is True
        assert await svc.get_online_value(fd.id, "AAPL") is None

    async def test_purge_expired(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "close")
        await svc.set_online_value(fd.id, "AAPL", "150", ttl_seconds=0)
        await svc.set_online_value(fd.id, "MSFT", "300", ttl_seconds=3600)
        count = await svc.purge_expired_values()
        assert count == 1


# ── Offline Store ──

class TestOfflineStore:
    async def test_set_offline_batch(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "close")
        values = [
            {"entity_key": "AAPL", "value": "150.25", "value_type": "numerical"},
            {"entity_key": "MSFT", "value": "300.50", "value_type": "numerical"},
        ]
        rows = await svc.set_offline_batch(fd.id, values, batch_id="batch_001")
        assert len(rows) == 2
        assert rows[0].batch_id == "batch_001"

    async def test_get_offline_values(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "close")
        await svc.set_offline_batch(fd.id, [
            {"entity_key": "AAPL", "value": "150"},
            {"entity_key": "MSFT", "value": "300"},
        ], batch_id="b1")
        items = await svc.get_offline_values(fd.id, batch_id="b1")
        assert len(items) == 2

    async def test_get_offline_values_filter_entity(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "close")
        await svc.set_offline_batch(fd.id, [
            {"entity_key": "AAPL", "value": "150"},
            {"entity_key": "MSFT", "value": "300"},
        ], batch_id="b1")
        items = await svc.get_offline_values(fd.id, batch_id="b1", entity_key="AAPL")
        assert len(items) == 1
        assert items[0].entity_key == "AAPL"

    async def test_get_offline_dataset(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        f1 = await svc.create_feature(ent.id, "close")
        f2 = await svc.create_feature(ent.id, "volume")
        await svc.set_offline_batch(f1.id, [
            {"entity_key": "AAPL", "value": "150"},
            {"entity_key": "MSFT", "value": "300"},
        ], batch_id="b1")
        await svc.set_offline_batch(f2.id, [
            {"entity_key": "AAPL", "value": "1000000"},
            {"entity_key": "MSFT", "value": "2000000"},
        ], batch_id="b1")
        data = await svc.get_offline_dataset([f1.id, f2.id], batch_id="b1")
        assert len(data) == 2
        keys = {d["entity_key"] for d in data}
        assert keys == {"AAPL", "MSFT"}


# ── Lineage ──

class TestLineage:
    async def test_add_lineage(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "close")
        fl = await svc.add_lineage(
            fd.id, source_type="table", source_name="daily_price",
            source_version="1.0",
            transformation_description="Raw close price",
            dependencies=[],
        )
        assert fl.id is not None
        assert fl.source_type == "table"

    async def test_get_lineage(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "rsi")
        await svc.add_lineage(fd.id, "derived", "close_price")
        await svc.add_lineage(fd.id, "derived", "avg_gain")
        items = await svc.get_lineage(fd.id)
        assert len(items) == 2

    async def test_get_lineage_graph(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        close = await svc.create_feature(ent.id, "close")
        rsi = await svc.create_feature(ent.id, "rsi")
        await svc.add_lineage(
            rsi.id, source_type="derived", source_name="rsi_calc",
            dependencies=[close.id],
        )
        graph = await svc.get_lineage_graph(rsi.id)
        assert graph["feature"]["name"] == "rsi"
        assert len(graph["upstream"]) >= 1


# ── Validation Rules ──

class TestValidationRules:
    async def test_create_rule(self, session):
        svc = FeatureStoreService(session)
        rule = await svc.create_validation_rule(
            "no_nulls", "null_check",
            description="Value must not be null",
        )
        assert rule.id is not None
        assert rule.name == "no_nulls"
        assert rule.rule_type == "null_check"
        assert rule.severity == "error"

    async def test_create_rule_for_feature(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "close")
        rule = await svc.create_validation_rule(
            "close_range", "range", feature_id=fd.id,
            config={"min": 0, "max": 100000},
        )
        assert rule.feature_id == fd.id

    async def test_list_rules(self, session):
        svc = FeatureStoreService(session)
        await svc.create_validation_rule("r1", "null_check")
        await svc.create_validation_rule("r2", "range")
        items = await svc.list_validation_rules()
        assert len(items) == 2

    async def test_list_rules_filter_feature(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "close")
        await svc.create_validation_rule("global_rule", "null_check")
        await svc.create_validation_rule("close_range", "range", feature_id=fd.id)
        items = await svc.list_validation_rules(feature_id=fd.id)
        assert len(items) == 2


# ── Validation ──

class TestValidation:
    async def test_validate_null_check_pass(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "close")
        await svc.create_validation_rule("no_null", "null_check", feature_id=fd.id)
        results = await svc.validate_value(fd.id, "150.25")
        passed = [r for r in results if r.status == "passed"]
        assert len(passed) >= 1

    async def test_validate_null_check_fail(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "close")
        await svc.create_validation_rule("no_null", "null_check", feature_id=fd.id)
        results = await svc.validate_value(fd.id, "")
        failed = [r for r in results if r.status == "failed"]
        assert len(failed) >= 1
        assert "null or empty" in failed[0].message

    async def test_validate_range_pass(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "close")
        await svc.create_validation_rule("price_range", "range", feature_id=fd.id, config={"min": 0, "max": 1000})
        results = await svc.validate_value(fd.id, "500")
        assert all(r.status == "passed" for r in results)

    async def test_validate_range_fail(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "close")
        await svc.create_validation_rule("price_range", "range", feature_id=fd.id, config={"min": 0, "max": 100})
        results = await svc.validate_value(fd.id, "500")
        failed = [r for r in results if r.status == "failed"]
        assert len(failed) >= 1

    async def test_validate_type_check(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "volume")
        await svc.create_validation_rule("must_be_num", "type_check", feature_id=fd.id, config={"type": "numerical"})
        results = await svc.validate_value(fd.id, "1000000")
        assert all(r.status == "passed" for r in results)

    async def test_validate_type_check_fail(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "volume")
        await svc.create_validation_rule("must_be_num", "type_check", feature_id=fd.id, config={"type": "integer"})
        results = await svc.validate_value(fd.id, "not_a_number")
        failed = [r for r in results if r.status in ("failed", "error")]
        assert len(failed) >= 1

    async def test_validate_regex(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "isin")
        await svc.create_validation_rule("isin_format", "regex", feature_id=fd.id, config={"pattern": r"^[A-Z]{2}[A-Z0-9]{10}$"})
        results = await svc.validate_value(fd.id, "US0378331005")
        assert all(r.status == "passed" for r in results)

    async def test_validate_regex_fail(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "isin")
        await svc.create_validation_rule("isin_format", "regex", feature_id=fd.id, config={"pattern": r"^[A-Z]{2}[A-Z0-9]{10}$"})
        results = await svc.validate_value(fd.id, "invalid")
        failed = [r for r in results if r.status == "failed"]
        assert len(failed) >= 1

    async def test_get_validation_results(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "close")
        await svc.create_validation_rule("no_null", "null_check", feature_id=fd.id)
        await svc.validate_value(fd.id, "150", batch_id="batch_1")
        results = await svc.get_validation_results(feature_id=fd.id)
        assert len(results) >= 1


# ── Cache ──

class TestCache:
    async def test_cache_stats_empty(self, session):
        svc = FeatureStoreService(session)
        stats = await svc.get_cache_hit_rate()
        assert stats["total"] == 0
        assert stats["hit_rate"] == 1.0

    async def test_cache_stats(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "close")
        await svc.set_online_value(fd.id, "AAPL", "150", ttl_seconds=3600)
        await svc.set_online_value(fd.id, "MSFT", "300", ttl_seconds=0)
        stats = await svc.get_cache_hit_rate()
        assert stats["total"] == 2
        assert stats["expired"] == 1

    async def test_warm_cache(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "close")
        values = [
            {"entity_key": "AAPL", "value": "150", "value_type": "numerical"},
            {"entity_key": "MSFT", "value": "300"},
        ]
        count = await svc.warm_cache(fd.id, values, ttl_seconds=3600)
        assert count == 2
        v1 = await svc.get_online_value(fd.id, "AAPL")
        assert v1 == "150"

    async def test_clear_cache(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        f1 = await svc.create_feature(ent.id, "close")
        f2 = await svc.create_feature(ent.id, "volume")
        await svc.set_online_value(f1.id, "AAPL", "150")
        await svc.set_online_value(f2.id, "AAPL", "1000000")
        count = await svc.clear_cache(feature_id=f1.id)
        assert count == 1
        assert await svc.get_online_value(f1.id, "AAPL") is None
        assert await svc.get_online_value(f2.id, "AAPL") is not None

    async def test_clear_all_cache(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "close")
        await svc.set_online_value(fd.id, "AAPL", "150")
        await svc.set_online_value(fd.id, "MSFT", "300")
        count = await svc.clear_cache()
        assert count == 2
        assert await svc.get_online_value(fd.id, "AAPL") is None


# ── Integration ──

class TestIntegration:
    async def test_full_feature_lifecycle(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock", description="Stock market entities")
        assert ent.name == "stock"

        fd = await svc.create_feature(
            ent.id, "close_price",
            display_name="Close Price",
            feature_type="numerical",
            source="daily_prices",
            tags=["price", "ohlc"],
            is_online=True, is_offline=True,
        )
        assert fd.name == "close_price"

        versions = await svc.list_versions(fd.id)
        assert len(versions) == 1
        assert versions[0].version == "1.0.0"

        await svc.set_online_value(fd.id, "AAPL", "150.25", value_type="numerical", ttl_seconds=3600)
        value = await svc.get_online_value(fd.id, "AAPL")
        assert value == "150.25"

        await svc.set_offline_batch(fd.id, [
            {"entity_key": "AAPL", "value": "150.25", "value_type": "numerical"},
            {"entity_key": "MSFT", "value": "300.50", "value_type": "numerical"},
        ], batch_id="daily_20240101")
        offline = await svc.get_offline_values(fd.id, batch_id="daily_20240101")
        assert len(offline) == 2

        fl = await svc.add_lineage(
            fd.id, source_type="table", source_name="daily_prices",
            source_version="1.0",
            transformation_description="Raw close from daily prices",
        )
        assert fl.source_name == "daily_prices"

        rule = await svc.create_validation_rule(
            "price_positive", "range", feature_id=fd.id,
            config={"min": 0, "max": 100000},
        )
        results = await svc.validate_value(fd.id, "150.25")
        passed = [r for r in results if r.status == "passed"]
        assert len(passed) >= 1

        stats = await svc.get_cache_hit_rate()
        assert stats["total"] >= 1

        await svc.clear_cache(feature_id=fd.id)
        assert await svc.get_online_value(fd.id, "AAPL") is None

    async def test_validation_multiple_rules(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        fd = await svc.create_feature(ent.id, "close")
        await svc.create_validation_rule("no_null", "null_check", feature_id=fd.id)
        await svc.create_validation_rule("positive", "range", feature_id=fd.id, config={"min": 0})
        await svc.create_validation_rule("is_num", "type_check", feature_id=fd.id, config={"type": "numerical"})
        results = await svc.validate_value(fd.id, "150.25")
        assert len(results) == 3

    async def test_offline_dataset_multi_feature(self, session):
        svc = FeatureStoreService(session)
        ent = await svc.create_entity("stock")
        f1 = await svc.create_feature(ent.id, "close")
        f2 = await svc.create_feature(ent.id, "volume")
        f3 = await svc.create_feature(ent.id, "sector", feature_type="categorical")

        batch = "b2"
        await svc.set_offline_batch(f1.id, [
            {"entity_key": "AAPL", "value": "150"},
            {"entity_key": "MSFT", "value": "300"},
            {"entity_key": "GOOG", "value": "200"},
        ], batch_id=batch)
        await svc.set_offline_batch(f2.id, [
            {"entity_key": "AAPL", "value": "1e6"},
            {"entity_key": "MSFT", "value": "2e6"},
            {"entity_key": "GOOG", "value": "500k"},
        ], batch_id=batch)
        await svc.set_offline_batch(f3.id, [
            {"entity_key": "AAPL", "value": "Tech"},
            {"entity_key": "MSFT", "value": "Tech"},
            {"entity_key": "GOOG", "value": "Tech"},
        ], batch_id=batch)

        dataset = await svc.get_offline_dataset(
            [f1.id, f2.id, f3.id],
            batch_id=batch,
            entity_keys=["AAPL", "MSFT"],
        )
        assert len(dataset) == 2
        for row in dataset:
            assert row["entity_key"] in ("AAPL", "MSFT")
