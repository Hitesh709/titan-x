"""TimescaleDB management service.

Provides methods to inspect and manage hypertables, compression, retention,
continuous aggregates, chunk statistics, and overall TimescaleDB health.
"""
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

HYPERTABLE_CONFIG: dict[str, dict[str, str]] = {
    "intraday_prices":       {"time_col": "timestamp",     "chunk_interval": "1 day"},
    "daily_prices":          {"time_col": "trade_date",    "chunk_interval": "1 month"},
    "adjusted_prices":       {"time_col": "trade_date",    "chunk_interval": "1 month"},
    "technical_indicators":  {"time_col": "trade_date",    "chunk_interval": "1 month"},
    "feature_values":        {"time_col": "as_of_date",    "chunk_interval": "1 month"},
    "market_breadth":        {"time_col": "trade_date",    "chunk_interval": "1 month"},
    "predictions":           {"time_col": "as_of_date",    "chunk_interval": "1 month"},
    "stock_rankings":        {"time_col": "as_of_date",    "chunk_interval": "1 month"},
    "market_regimes":        {"time_col": "as_of_date",    "chunk_interval": "1 month"},
    "regime_signals":        {"time_col": "as_of_date",    "chunk_interval": "1 month"},
    "backtest_equity_curve": {"time_col": "date",          "chunk_interval": "1 month"},
    "macro_indicators":      {"time_col": "as_of_date",    "chunk_interval": "6 months"},
    "macro_analyses":        {"time_col": "as_of_date",    "chunk_interval": "6 months"},
    "macro_features":        {"time_col": "as_of_date",    "chunk_interval": "6 months"},
    "global_market_data":    {"time_col": "as_of_date",    "chunk_interval": "6 months"},
    "sector_performance":    {"time_col": "as_of_date",    "chunk_interval": "6 months"},
    "correlation_pairs":     {"time_col": "as_of_date",    "chunk_interval": "1 month"},
    "news_articles":         {"time_col": "published_at",  "chunk_interval": "1 day"},
    "validation_runs":       {"time_col": "started_at",    "chunk_interval": "1 month"},
    "validation_anomalies":  {"time_col": "trade_date",    "chunk_interval": "1 month"},
    "data_quality_scores":   {"time_col": "score_date",    "chunk_interval": "1 month"},
}


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw dict row to JSON-safe values."""
    result = {}
    for k, v in row.items():
        if isinstance(v, (date, datetime)):
            result[k] = v.isoformat()
        elif isinstance(v, Decimal):
            result[k] = float(v)
        elif isinstance(v, bytes):
            result[k] = v.decode("utf-8", errors="replace")
        else:
            result[k] = v
    return result


def _serialize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_serialize_row(r) for r in rows]


class TimescaleDBService:
    """Service for managing TimescaleDB hypertables, policies, and aggregates."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def is_timescaledb_available(self) -> bool:
        """Check if the TimescaleDB extension is installed and loaded."""
        result = await self.session.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'timescaledb';")
        )
        return result.scalar() is not None

    async def list_hypertables(self) -> list[dict[str, Any]]:
        """List all hypertables and their metadata."""
        result = await self.session.execute(
            text("""
                SELECT
                    hypertable_name,
                    table_schema,
                    num_chunks,
                    compression_state,
                    approx_total_size AS total_size_bytes
                FROM timescaledb_information.hypertables
                ORDER BY hypertable_name;
            """)
        )
        return _serialize_rows(result.mappings().all())

    async def get_hypertable_details(self, table_name: str) -> dict[str, Any] | None:
        """Get details for a specific hypertable."""
        result = await self.session.execute(
            text("""
                SELECT
                    hypertable_name,
                    table_schema,
                    table_owner,
                    num_chunks,
                    compression_state,
                    approx_total_size AS total_size_bytes,
                    chunk_time_interval,
                    associated_schema_name,
                    associated_table_prefix
                FROM timescaledb_information.hypertables
                WHERE hypertable_name = :table_name;
            """),
            {"table_name": table_name},
        )
        row = result.mappings().first()
        return _serialize_row(dict(row)) if row else None

    async def list_chunks(self, table_name: str | None = None) -> list[dict[str, Any]]:
        """List chunks for all hypertables (or a specific one)."""
        if table_name:
            result = await self.session.execute(
                text("""
                    SELECT
                        chunk_name,
                        hypertable_name,
                        range_start,
                        range_end,
                        is_compressed,
                        table_size AS size_bytes
                    FROM timescaledb_information.chunks
                    WHERE hypertable_name = :table_name
                    ORDER BY range_start;
                """),
                {"table_name": table_name},
            )
        else:
            result = await self.session.execute(
                text("""
                    SELECT
                        chunk_name,
                        hypertable_name,
                        range_start,
                        range_end,
                        is_compressed,
                        table_size AS size_bytes
                    FROM timescaledb_information.chunks
                    ORDER BY hypertable_name, range_start;
                """)
            )
        return _serialize_rows(result.mappings().all())

    async def list_compression_policies(self) -> list[dict[str, Any]]:
        """List all compression policies."""
        result = await self.session.execute(
            text("""
                SELECT
                    hypertable_name,
                    compress_after::text,
                    schedule_interval
                FROM timescaledb_information.compression_policies
                ORDER BY hypertable_name;
            """)
        )
        return _serialize_rows(result.mappings().all())

    async def list_retention_policies(self) -> list[dict[str, Any]]:
        """List all retention policies."""
        result = await self.session.execute(
            text("""
                SELECT
                    hypertable_name,
                    retention_period::text,
                    schedule_interval
                FROM timescaledb_information.retention_policies
                ORDER BY hypertable_name;
            """)
        )
        return _serialize_rows(result.mappings().all())

    async def list_continuous_aggregates(self) -> list[dict[str, Any]]:
        """List all continuous aggregates and their refresh policies."""
        result = await self.session.execute(
            text("""
                SELECT
                    view_name,
                    materialization_hypertable_schema,
                    materialization_hypertable_name,
                    compression_enabled
                FROM timescaledb_information.continuous_aggregates
                ORDER BY view_name;
            """)
        )
        return _serialize_rows(result.mappings().all())

    async def refresh_continuous_aggregate(
        self, view_name: str,
    ) -> dict[str, Any]:
        """Manually refresh a continuous aggregate view."""
        await self.session.execute(
            text(f"CALL refresh_continuous_aggregate('{view_name}', NULL, NULL);")
        )
        await self.session.commit()
        return {"status": "ok", "view": view_name}

    async def get_chunk_detailed_stats(self, table_name: str) -> list[dict[str, Any]]:
        """Get detailed chunk statistics (size, row counts, compression ratio)."""
        result = await self.session.execute(
            text("""
                SELECT
                    ch.chunk_name,
                    ch.hypertable_name,
                    ch.range_start,
                    ch.range_end,
                    ch.is_compressed,
                    ch.table_size AS chunk_size_bytes,
                    ch.index_size AS index_size_bytes,
                    ch.toast_size AS toast_size_bytes
                FROM timescaledb_information.chunks ch
                WHERE ch.hypertable_name = :table_name
                ORDER BY ch.range_start;
            """),
            {"table_name": table_name},
        )
        return _serialize_rows(result.mappings().all())

    async def get_compression_stats(self, table_name: str) -> dict[str, Any]:
        """Get compression statistics for a hypertable."""
        result = await self.session.execute(
            text("""
                SELECT
                    hypertable_name,
                    compression_state,
                    approx_total_size AS before_compression_bytes,
                    compressed_total_size AS after_compression_bytes,
                    compression_ratio
                FROM timescaledb_information.hypertables
                WHERE hypertable_name = :table_name;
            """),
            {"table_name": table_name},
        )
        row = result.mappings().first()
        if not row:
            return {"table": table_name, "compression_state": "not_found"}
        return _serialize_row(dict(row))

    async def reorder_chunks(self, table_name: str, index_name: str) -> dict[str, Any]:
        """Reorder chunks on disk for a hypertable using a specific index."""
        await self.session.execute(
            text(f"""
                SELECT reorder_chunk(c, index => '{index_name}', verbose => false)
                FROM show_chunks('{table_name}') c;
            """)
        )
        await self.session.commit()
        return {"status": "ok", "table": table_name, "index": index_name}

    async def get_stats_summary(self) -> dict[str, Any]:
        """Return a summary dashboard of all TimescaleDB-related stats."""
        hypertables = await self.list_hypertables()
        compression = await self.list_compression_policies()
        retention = await self.list_retention_policies()
        caggs = await self.list_continuous_aggregates()

        total_chunks = sum(
            h.get("num_chunks", 0) or 0 for h in hypertables
        )
        total_size_bytes = sum(
            int(h.get("total_size_bytes", "0").rstrip(" bytes").replace(",", "") or "0")
            for h in hypertables
        )

        return {
            "hyperatables_count": len(hypertables),
            "total_chunks": total_chunks,
            "total_size_bytes": total_size_bytes,
            "compression_policies": len(compression),
            "retention_policies": len(retention),
            "continuous_aggregates": len(caggs),
            "detailed": {
                "hypertables": hypertables,
                "compression_policies": compression,
                "retention_policies": retention,
                "continuous_aggregates": caggs,
            },
        }
