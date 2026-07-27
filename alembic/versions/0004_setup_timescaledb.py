"""TimescaleDB: hypertables, compression, retention, continuous aggregates, indexes

Creates the TimescaleDB extension, converts 16 time-series tables into hypertables,
enables compression and retention policies, creates continuous aggregates, and adds
performance indexes.  All operations are idempotent (IF NOT EXISTS / if_not_exists).

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-20 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ── Hypertable configuration ──────────────────────────────────────────────────
# (table_name, time_column, chunk_interval, compression_after, retention_after)
# chunk_interval / compression_after / retention_after are expressed as INTERVAL strings

HYPERTABLE_CONFIG: list[tuple[str, str, str, str, str]] = [
    # Core market data
    ("intraday_prices",       "timestamp",    "1 day",    "7 days",   "365 days"),
    ("daily_prices",          "trade_date",   "1 month",  "14 days",  "3653 days"),  # 10 years
    ("adjusted_prices",       "trade_date",   "1 month",  "14 days",  "3653 days"),
    # Technical & features
    ("technical_indicators",  "trade_date",   "1 month",  "30 days",  "730 days"),
    ("feature_values",        "as_of_date",   "1 month",  "14 days",  "730 days"),
    # Market breadth
    ("market_breadth",        "trade_date",   "1 month",  "30 days",  "730 days"),
    # Predictions & rankings
    ("predictions",           "as_of_date",   "1 month",  "30 days",  "730 days"),
    ("stock_rankings",        "as_of_date",   "1 month",  "30 days",  "730 days"),
    ("market_regimes",        "as_of_date",   "1 month",  "30 days",  "730 days"),
    ("regime_signals",        "as_of_date",   "1 month",  "30 days",  "730 days"),
    # Backtest
    ("backtest_equity_curve", "date",         "1 month",  "30 days",  "730 days"),
    # Macro
    ("macro_indicators",      "as_of_date",   "6 months", "90 days",  "3653 days"),
    ("macro_analyses",        "as_of_date",   "6 months", "90 days",  "3653 days"),
    ("macro_features",        "as_of_date",   "6 months", "90 days",  "3653 days"),
    # Global & sector
    ("global_market_data",    "as_of_date",   "6 months", "90 days",  "3653 days"),
    ("sector_performance",    "as_of_date",   "6 months", "90 days",  "3653 days"),
    # Correlation
    ("correlation_pairs",     "as_of_date",   "1 month",  "30 days",  "730 days"),
    # News
    ("news_articles",         "published_at", "1 day",    "7 days",   "365 days"),
    # Validation
    ("validation_runs",       "started_at",   "1 month",  "30 days",  "730 days"),
    ("validation_anomalies",  "trade_date",   "1 month",  "30 days",  "730 days"),
    ("data_quality_scores",   "score_date",   "1 month",  "30 days",  "730 days"),
]

# ── Continuous Aggregate definitions ──────────────────────────────────────────
# (view_name, hypertable, time_col, aggregation_cols, bucket_interval)

CONTINUOUS_AGGREGATES: list[tuple[str, str, str, str, str]] = [
    # Daily price weekly aggregate
    (
        "cagg_daily_price_weekly",
        "daily_prices",
        "trade_date",
        "symbol, avg(close) as avg_close, max(high) as max_high, min(low) as min_low, "
        "last(close, trade_date) as last_close, sum(volume) as total_volume, "
        "stddev_samp(close) as close_volatility",
        "1 week",
    ),
    # Daily price monthly aggregate
    (
        "cagg_daily_price_monthly",
        "daily_prices",
        "trade_date",
        "symbol, avg(close) as avg_close, max(high) as max_high, min(low) as min_low, "
        "last(close, trade_date) as last_close, sum(volume) as total_volume",
        "1 month",
    ),
    # Feature value weekly aggregate
    (
        "cagg_feature_weekly",
        "feature_values",
        "as_of_date",
        "feature_definition_id, symbol, avg(value) as avg_value, "
        "min(value) as min_value, max(value) as max_value, "
        "last(value, as_of_date) as last_value",
        "1 week",
    ),
    # Technical indicator weekly aggregate
    (
        "cagg_technical_weekly",
        "technical_indicators",
        "trade_date",
        "symbol, indicator, avg(value) as avg_value, "
        "last(value, trade_date) as last_value, "
        "last(value_secondary, trade_date) as last_value2",
        "1 week",
    ),
    # Market breadth weekly aggregate
    (
        "cagg_breadth_weekly",
        "market_breadth",
        "trade_date",
        "avg(advancing) as avg_advancing, avg(declining) as avg_declining, "
        "avg(advance_decline_ratio) as avg_ad_ratio, "
        "last(breadth_oscillator, trade_date) as last_oscillator",
        "1 week",
    ),
]


def _fmt_interval(days_str: str) -> str:
    """Convert a human interval string like '3653 days' to an SQL interval."""
    return f"INTERVAL '{days_str}'"


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Create TimescaleDB extension ───────────────────────────────────
    conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")

    # ── 2. Ensure tables exist (create if missing) ────────────────────────
    # Use create_hypertable which will fail gracefully for tables that
    # already exist when if_not_exists is true.
    for tbl, time_col, chunk_iv, _compress_iv, _retain_iv in HYPERTABLE_CONFIG:
        _create_hypertable(conn, tbl, time_col, chunk_iv)

    # ── 3. Enable compression & set policies ──────────────────────────────
    for tbl, _time_col, _chunk_iv, compress_iv, _retain_iv in HYPERTABLE_CONFIG:
        _enable_compression(conn, tbl, compress_iv)

    # ── 4. Add retention policies ────────────────────────────────────────
    for tbl, time_col, _chunk_iv, _compress_iv, retain_iv in HYPERTABLE_CONFIG:
        _add_retention_policy(conn, tbl, time_col, retain_iv)

    # ── 5. Create continuous aggregates ───────────────────────────────────
    for view_name, hypertable, time_col, agg_cols, bucket_iv in CONTINUOUS_AGGREGATES:
        _create_continuous_aggregate(conn, view_name, hypertable, time_col, agg_cols, bucket_iv)

    # ── 6. Add performance indexes ────────────────────────────────────────
    _add_performance_indexes(conn)


def downgrade() -> None:
    conn = op.get_bind()

    # Remove continuous aggregates
    for view_name, _ht, _tc, _ac, _bi in CONTINUOUS_AGGREGATES:
        conn.exec_driver_sql(f"DROP MATERIALIZED VIEW IF EXISTS {view_name} CASCADE;")

    # Remove retention policies
    for tbl, _tc, _ci, _civ, _ri in HYPERTABLE_CONFIG:
        conn.exec_driver_sql(
            f"SELECT remove_retention_policy('{tbl}', if_exists => true);"
        )

    # Remove compression settings (reverts to default)
    for tbl, _tc, _ci, _civ, _ri in HYPERTABLE_CONFIG:
        conn.exec_driver_sql(
            f"ALTER TABLE {tbl} SET (timescaledb.compress = false);"
        )

    # Drop performance indexes
    _drop_performance_indexes(conn)


# ═══════════════════════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════════════════════

def _create_hypertable(conn, table: str, time_col: str, chunk_interval: str) -> None:
    """Convert a regular table into a TimescaleDB hypertable."""
    sql = (
        f"SELECT create_hypertable("
        f"  '{table}', '{time_col}',"
        f"  chunk_time_interval => {_fmt_interval(chunk_interval)},"
        f"  if_not_exists          => true,"
        f"  migrate_data           => true"
        f");"
    )
    conn.exec_driver_sql(sql)


def _enable_compression(conn, table: str, compress_after: str) -> None:
    """Enable native compression and add a compression policy."""
    conn.exec_driver_sql(
        f"ALTER TABLE {table} SET (timescaledb.compress = true);"
    )
    conn.exec_driver_sql(
        f"SELECT add_compression_policy("
        f"  '{table}', {_fmt_interval(compress_after)}, if_not_exists => true"
        f");"
    )


def _add_retention_policy(conn, table: str, time_col: str, retain_after: str) -> None:
    """Add a data retention policy to drop chunks older than the threshold."""
    conn.exec_driver_sql(
        f"SELECT add_retention_policy("
        f"  '{table}', {_fmt_interval(retain_after)}, if_not_exists => true"
        f");"
    )


def _create_continuous_aggregate(
    conn, view_name: str, hypertable: str,
    time_col: str, agg_cols: str, bucket_interval: str,
) -> None:
    """Create a continuous aggregate materialized view."""
    create_sql = (
        f"CREATE MATERIALIZED VIEW IF NOT EXISTS {view_name}\n"
        f"WITH (timescaledb.continuous) AS\n"
        f"SELECT\n"
        f"  time_bucket({_fmt_interval(bucket_interval)}, {time_col}) AS bucket,\n"
        f"  {agg_cols}\n"
        f"FROM {hypertable}\n"
        f"GROUP BY bucket"
        + (", symbol" if "symbol" in agg_cols else "")
        + (", feature_definition_id" if "feature_definition_id" in agg_cols else "")
        + (", indicator" if "indicator" in agg_cols else "")
        + "\nWITH NO DATA;"
    )
    conn.exec_driver_sql(create_sql)

    # Add refresh policy
    conn.exec_driver_sql(
        f"SELECT add_continuous_aggregate_policy('{view_name}',\n"
        f"  start_offset => {_fmt_interval('30 days')},\n"
        f"  end_offset   => {_fmt_interval('1 hour')},\n"
        f"  schedule_interval => {_fmt_interval('1 hour')},\n"
        f"  if_not_exists => true\n"
        f");"
    )

    # Refresh recent data so the view is immediately usable
    try:
        conn.exec_driver_sql(f"CALL refresh_continuous_aggregate('{view_name}', NULL, NULL);")
    except Exception:
        pass  # may fail on first run if no data; that's ok


def _add_performance_indexes(conn) -> None:
    """Add time-series-optimized indexes for common query patterns."""

    # Intraday prices: fast lookups by (symbol, timestamp) and time-based ordering
    _create_index_if_not_exists(conn, "intraday_prices", "ix_intraday_symbol_ts",
                                "symbol, timestamp DESC")
    _create_index_if_not_exists(conn, "intraday_prices", "ix_intraday_ts_desc",
                                "timestamp DESC")

    # Daily prices: (symbol, trade_date) already has unique constraint;
    # add a covering index for the common case where we query by symbol
    _create_index_if_not_exists(conn, "daily_prices", "ix_daily_symbol_date_desc",
                                "symbol, trade_date DESC")

    # Adjusted prices: same pattern
    _create_index_if_not_exists(conn, "adjusted_prices", "ix_adjusted_symbol_date_desc",
                                "symbol, trade_date DESC")

    # Feature values: queries by (symbol, as_of_date) are most common
    _create_index_if_not_exists(conn, "feature_values", "ix_feature_val_sym_date_desc",
                                "symbol, as_of_date DESC")
    _create_index_if_not_exists(conn, "feature_values", "ix_feature_val_def_date_desc",
                                "feature_definition_id, as_of_date DESC")

    # Technical indicators: (symbol, indicator, trade_date) is the standard access pattern
    _create_index_if_not_exists(conn, "technical_indicators", "ix_tech_ind_sym_ind_date_desc",
                                "symbol, indicator, trade_date DESC")

    # Market breadth: queries usually look at recent dates descending
    _create_index_if_not_exists(conn, "market_breadth", "ix_breadth_date_desc",
                                "trade_date DESC")

    # Predictions: (symbol, as_of_date) or (symbol, horizon)
    _create_index_if_not_exists(conn, "predictions", "ix_pred_sym_date_desc",
                                "symbol, as_of_date DESC")
    _create_index_if_not_exists(conn, "predictions", "ix_pred_sym_horizon_date_desc",
                                "symbol, horizon, as_of_date DESC")

    # Stock rankings: (symbol, as_of_date)
    _create_index_if_not_exists(conn, "stock_rankings", "ix_rank_sym_date_desc",
                                "symbol, as_of_date DESC")
    _create_index_if_not_exists(conn, "stock_rankings", "ix_rank_date_desc",
                                "as_of_date DESC")

    # Market regimes: (symbol, as_of_date)
    _create_index_if_not_exists(conn, "market_regimes", "ix_regime_sym_date_desc",
                                "symbol, as_of_date DESC")

    # Backtest equity curve: (backtest_id, date)
    _create_index_if_not_exists(conn, "backtest_equity_curve", "ix_eq_curve_btid_date",
                                "backtest_id, date")

    # News articles: published_at descending for recent news queries
    _create_index_if_not_exists(conn, "news_articles", "ix_news_published_desc",
                                "published_at DESC")
    _create_index_if_not_exists(conn, "news_articles", "ix_news_symbol_published_desc",
                                "symbol, published_at DESC")

    # Macro indicators: indicator_type + as_of_date
    _create_index_if_not_exists(conn, "macro_indicators", "ix_macro_type_date_desc",
                                "indicator_type, as_of_date DESC")

    # Global market data: symbol + as_of_date
    _create_index_if_not_exists(conn, "global_market_data", "ix_global_sym_date_desc",
                                "symbol, as_of_date DESC")

    # Sector performance: sector + as_of_date
    _create_index_if_not_exists(conn, "sector_performance", "ix_sector_date_desc",
                                "sector, as_of_date DESC")

    # Correlation pairs: symbol + as_of_date
    _create_index_if_not_exists(conn, "correlation_pairs", "ix_corr_sym_date_desc",
                                "symbol, as_of_date DESC")

    # Validation runs: started_at descending
    _create_index_if_not_exists(conn, "validation_runs", "ix_valrun_started_desc",
                                "started_at DESC")

    # Validation anomalies: (run_id, trade_date)
    _create_index_if_not_exists(conn, "validation_anomalies", "ix_valanom_run_date",
                                "run_id, trade_date DESC")


def _drop_performance_indexes(conn) -> None:
    indexes = [
        "ix_intraday_symbol_ts", "ix_intraday_ts_desc",
        "ix_daily_symbol_date_desc",
        "ix_adjusted_symbol_date_desc",
        "ix_feature_val_sym_date_desc", "ix_feature_val_def_date_desc",
        "ix_tech_ind_sym_ind_date_desc",
        "ix_breadth_date_desc",
        "ix_pred_sym_date_desc", "ix_pred_sym_horizon_date_desc",
        "ix_rank_sym_date_desc", "ix_rank_date_desc",
        "ix_regime_sym_date_desc",
        "ix_eq_curve_btid_date",
        "ix_news_published_desc", "ix_news_symbol_published_desc",
        "ix_macro_type_date_desc",
        "ix_global_sym_date_desc",
        "ix_sector_date_desc",
        "ix_corr_sym_date_desc",
        "ix_valrun_started_desc",
        "ix_valanom_run_date",
    ]
    for idx_name in indexes:
        conn.exec_driver_sql(f"DROP INDEX IF EXISTS {idx_name};")


def _create_index_if_not_exists(conn, table: str, index_name: str, columns: str) -> None:
    """Create an index if it does not already exist."""
    conn.exec_driver_sql(
        f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({columns});"
    )
