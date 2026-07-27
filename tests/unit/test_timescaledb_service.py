"""Tests for the TimescaleDB management service and API.

TimescaleDB is a PostgreSQL extension and is not available on SQLite.
All tests use mocks for the database interactions and verify that the
service methods construct correct queries, handle results, and manage
edge cases properly.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.services.timescaledb_service import (
    HYPERTABLE_CONFIG,
    TimescaleDBService,
    _serialize_row,
    _serialize_rows,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def service(mock_session: AsyncMock) -> TimescaleDBService:
    return TimescaleDBService(mock_session)


def _mock_result(rows: list[dict]):
    """Create a mock SQLAlchemy result that behaves like mappings().all()."""
    mock = MagicMock()
    mappings_mock = MagicMock()

    class FakeRow(dict):
        def __getattr__(self, name):
            return self[name]

    mapping_rows = [FakeRow(r) for r in rows]

    mappings_mock.all = MagicMock(return_value=mapping_rows)
    mappings_mock.first = MagicMock(return_value=mapping_rows[0] if mapping_rows else None)
    mock.mappings = MagicMock(return_value=mappings_mock)
    mock.scalar = MagicMock(return_value=rows[0].get(list(rows[0].keys())[0]) if rows else None)

    mock.__iter__ = MagicMock(return_value=iter(mapping_rows))

    return mock


def _mock_scalar_result(value):
    """Create a mock result that returns a scalar value."""
    mock = MagicMock()
    mock.scalar = MagicMock(return_value=value)
    return mock


# ── Serializer tests ─────────────────────────────────────────────────────────


class TestSerializers:
    def test_serialize_row_date(self):
        row = {"d": date(2026, 7, 20), "n": 42}
        result = _serialize_row(row)
        assert result["d"] == "2026-07-20"
        assert result["n"] == 42

    def test_serialize_row_datetime(self):
        row = {"dt": datetime(2026, 7, 20, 10, 30, 0), "x": 1.5}
        result = _serialize_row(row)
        assert result["dt"] == "2026-07-20T10:30:00"

    def test_serialize_row_decimal(self):
        row = {"v": Decimal("123.45")}
        result = _serialize_row(row)
        assert result["v"] == 123.45

    def test_serialize_row_bytes(self):
        row = {"b": b"hello"}
        result = _serialize_row(row)
        assert result["b"] == "hello"

    def test_serialize_row_mixed(self):
        row = {
            "name": "test",
            "num": 100,
            "dt": date(2026, 1, 1),
            "dec": Decimal("99.99"),
            "flag": True,
        }
        result = _serialize_row(row)
        assert result["name"] == "test"
        assert result["num"] == 100
        assert result["dt"] == "2026-01-01"
        assert result["dec"] == 99.99
        assert result["flag"] is True

    def test_serialize_rows(self):
        rows = [
            {"d": date(2026, 1, 1), "v": Decimal("1.0")},
            {"d": date(2026, 1, 2), "v": Decimal("2.0")},
        ]
        result = _serialize_rows(rows)
        assert len(result) == 2
        assert result[0]["d"] == "2026-01-01"
        assert result[1]["v"] == 2.0


# ── TimescaleDBService tests ─────────────────────────────────────────────────


class TestIsTimescaleDBAvailable:
    async def test_available(self, mock_session, service):
        mock_session.execute.return_value = _mock_scalar_result("timescaledb")
        result = await service.is_timescaledb_available()
        assert result is True
        mock_session.execute.assert_called_once()
        sql = mock_session.execute.call_args[0][0]
        assert "pg_extension" in str(sql)

    async def test_not_available(self, mock_session, service):
        mock_session.execute.return_value = _mock_scalar_result(None)
        result = await service.is_timescaledb_available()
        assert result is False


class TestListHypertables:
    async def test_returns_hypertables(self, mock_session, service):
        mock_session.execute.return_value = _mock_result([
            {
                "hypertable_name": "daily_prices",
                "table_schema": "public",
                "num_chunks": 24,
                "compression_state": "compressed",
                "total_size_bytes": "1048576",
            },
        ])
        result = await service.list_hypertables()
        assert len(result) == 1
        assert result[0]["hypertable_name"] == "daily_prices"
        assert result[0]["num_chunks"] == 24

    async def test_empty(self, mock_session, service):
        mock_session.execute.return_value = _mock_result([])
        result = await service.list_hypertables()
        assert result == []


class TestGetHypertableDetails:
    async def test_found(self, mock_session, service):
        mock_session.execute.return_value = _mock_result([
            {
                "hypertable_name": "feature_values",
                "table_schema": "public",
                "table_owner": "app_user",
                "num_chunks": 12,
                "compression_state": "compressed",
                "total_size_bytes": "524288",
                "chunk_time_interval": "1 mon",
                "associated_schema_name": "_timescaledb_internal",
                "associated_table_prefix": "_hyper_2",
            },
        ])
        result = await service.get_hypertable_details("feature_values")
        assert result is not None
        assert result["hypertable_name"] == "feature_values"
        assert result["num_chunks"] == 12

    async def test_not_found(self, mock_session, service):
        mock_session.execute.return_value = _mock_result([])
        result = await service.get_hypertable_details("nonexistent")
        assert result is None


class TestListChunks:
    async def test_all_chunks(self, mock_session, service):
        mock_session.execute.return_value = _mock_result([
            {
                "chunk_name": "_hyper_1_1_chunk",
                "hypertable_name": "daily_prices",
                "range_start": "2026-01-01",
                "range_end": "2026-02-01",
                "is_compressed": True,
                "size_bytes": "65536",
            },
        ])
        result = await service.list_chunks()
        assert len(result) == 1
        assert result[0]["hypertable_name"] == "daily_prices"

    async def test_filter_by_table(self, mock_session, service):
        mock_session.execute.return_value = _mock_result([
            {
                "chunk_name": "_hyper_2_1_chunk",
                "hypertable_name": "intraday_prices",
                "range_start": "2026-07-20",
                "range_end": "2026-07-21",
                "is_compressed": False,
                "size_bytes": "4096",
            },
        ])
        result = await service.list_chunks("intraday_prices")
        assert len(result) == 1
        # Verify WHERE clause was used
        sql = str(mock_session.execute.call_args[0][0])
        assert "hypertable_name = :table_name" in sql or ":table_name" in sql


class TestListCompressionPolicies:
    async def test_returns_policies(self, mock_session, service):
        mock_session.execute.return_value = _mock_result([
            {
                "hypertable_name": "daily_prices",
                "compress_after": "14 days",
                "schedule_interval": "1 day",
            },
        ])
        result = await service.list_compression_policies()
        assert len(result) == 1
        assert result[0]["hypertable_name"] == "daily_prices"
        assert "14 days" in str(result[0]["compress_after"])

    async def test_empty(self, mock_session, service):
        mock_session.execute.return_value = _mock_result([])
        result = await service.list_compression_policies()
        assert result == []


class TestListRetentionPolicies:
    async def test_returns_policies(self, mock_session, service):
        mock_session.execute.return_value = _mock_result([
            {
                "hypertable_name": "intraday_prices",
                "retention_period": "365 days",
                "schedule_interval": "1 day",
            },
        ])
        result = await service.list_retention_policies()
        assert len(result) == 1
        assert result[0]["hypertable_name"] == "intraday_prices"

    async def test_empty(self, mock_session, service):
        mock_session.execute.return_value = _mock_result([])
        result = await service.list_retention_policies()
        assert result == []


class TestListContinuousAggregates:
    async def test_returns_caggs(self, mock_session, service):
        mock_session.execute.return_value = _mock_result([
            {
                "view_name": "cagg_daily_price_weekly",
                "materialization_hypertable_schema": "_timescaledb_internal",
                "materialization_hypertable_name": "_hyper_3_1_chunk",
                "compression_enabled": True,
            },
        ])
        result = await service.list_continuous_aggregates()
        assert len(result) == 1
        assert result[0]["view_name"] == "cagg_daily_price_weekly"
        assert result[0]["compression_enabled"] is True


class TestRefreshContinuousAggregate:
    async def test_refresh(self, mock_session, service):
        mock_session.execute.return_value = MagicMock()
        result = await service.refresh_continuous_aggregate("cagg_daily_price_weekly")
        assert result["status"] == "ok"
        assert result["view"] == "cagg_daily_price_weekly"
        mock_session.commit.assert_called_once()


class TestGetChunkDetailedStats:
    async def test_returns_stats(self, mock_session, service):
        mock_session.execute.return_value = _mock_result([
            {
                "chunk_name": "_hyper_1_1_chunk",
                "hypertable_name": "daily_prices",
                "range_start": "2026-01-01",
                "range_end": "2026-02-01",
                "is_compressed": True,
                "chunk_size_bytes": "65536",
                "index_size_bytes": "16384",
                "toast_size_bytes": "1024",
            },
        ])
        result = await service.get_chunk_detailed_stats("daily_prices")
        assert len(result) == 1
        d = result[0]
        assert d["chunk_name"] == "_hyper_1_1_chunk"
        assert d["is_compressed"] is True
        assert d["chunk_size_bytes"] == "65536"


class TestGetCompressionStats:
    async def test_returns_stats(self, mock_session, service):
        mock_session.execute.return_value = _mock_result([
            {
                "hypertable_name": "daily_prices",
                "compression_state": "compressed",
                "before_compression_bytes": "1048576",
                "after_compression_bytes": "262144",
                "compression_ratio": "4.0",
            },
        ])
        result = await service.get_compression_stats("daily_prices")
        assert result["hypertable_name"] == "daily_prices"
        assert float(result["compression_ratio"]) == 4.0

    async def test_not_found(self, mock_session, service):
        mock_session.execute.return_value = _mock_result([])
        result = await service.get_compression_stats("unknown")
        assert result["table"] == "unknown"
        assert result["compression_state"] == "not_found"


class TestReorderChunks:
    async def test_reorder(self, mock_session, service):
        mock_session.execute.return_value = MagicMock()
        result = await service.reorder_chunks("daily_prices", "ix_daily_symbol_date_desc")
        assert result["status"] == "ok"
        assert result["table"] == "daily_prices"
        mock_session.commit.assert_called_once()
        sql = str(mock_session.execute.call_args[0][0])
        assert "reorder_chunk" in sql


class TestGetStatsSummary:
    async def test_returns_summary(self, mock_session, service):
        mock_session.execute.return_value = _mock_result([
            {
                "hypertable_name": "daily_prices",
                "table_schema": "public",
                "num_chunks": 24,
                "compression_state": "compressed",
                "total_size_bytes": "1048576",
            },
            {
                "hypertable_name": "intraday_prices",
                "table_schema": "public",
                "num_chunks": 180,
                "compression_state": "compressed",
                "total_size_bytes": "2097152",
            },
        ])
        # We need to set up multiple returns for the various queries in get_stats_summary
        # It calls multiple methods — easiest is to patch individual methods
        with (
            patch.object(service, "list_hypertables", return_value=[
                {"hypertable_name": "daily_prices", "num_chunks": 24, "total_size_bytes": "1048576"},
                {"hypertable_name": "intraday_prices", "num_chunks": 180, "total_size_bytes": "2097152"},
            ]),
            patch.object(service, "list_compression_policies", return_value=[
                {"hypertable_name": "daily_prices", "compress_after": "14 days", "schedule_interval": "1 day"},
            ]),
            patch.object(service, "list_retention_policies", return_value=[
                {"hypertable_name": "intraday_prices", "retention_period": "365 days", "schedule_interval": "1 day"},
            ]),
            patch.object(service, "list_continuous_aggregates", return_value=[
                {"view_name": "cagg_daily_price_weekly", "compression_enabled": True},
            ]),
        ):
            result = await service.get_stats_summary()
            assert result["hyperatables_count"] == 2
            assert result["total_chunks"] == 204
            assert result["compression_policies"] == 1
            assert result["retention_policies"] == 1
            assert result["continuous_aggregates"] == 1
            assert "detailed" in result


# ── HYPERTABLE_CONFIG validation ─────────────────────────────────────────────


class TestHypertableConfig:
    def test_all_tables_have_config(self):
        """Every entry in HYPERTABLE_CONFIG has required keys."""
        for name, cfg in HYPERTABLE_CONFIG.items():
            assert "time_col" in cfg, f"{name} missing time_col"
            assert "chunk_interval" in cfg, f"{name} missing chunk_interval"
            assert isinstance(name, str)
            assert isinstance(cfg["time_col"], str)
            assert isinstance(cfg["chunk_interval"], str)

    def test_time_columns_are_reasonable(self):
        """Time column names match common patterns."""
        for name, cfg in HYPERTABLE_CONFIG.items():
            tc = cfg["time_col"]
            assert tc in (
                "timestamp", "trade_date", "as_of_date", "date",
                "published_at", "started_at", "score_date",
            ), f"{name}: unexpected time column '{tc}'"
