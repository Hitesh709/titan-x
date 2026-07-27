from datetime import date

from sqlalchemy import Date, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class GlobalMarketData(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "global_market_data"
    __table_args__ = (
        UniqueConstraint("symbol", "as_of_date", name="uq_global_mkt_sym_date"),
        Index("ix_global_mkt_type", "data_type"),
        Index("ix_global_mkt_region", "region"),
        Index("ix_global_mkt_symbol", "symbol"),
        Index("ix_global_mkt_date", "as_of_date"),
    )

    data_type: Mapped[str] = mapped_column(String(16), nullable=False)
    region: Mapped[str] = mapped_column(String(16), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class GlobalAnalysis(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "global_analyses"
    __table_args__ = (UniqueConstraint("as_of_date", name="uq_global_analysis_date"),)

    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    us_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    europe_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    asia_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    futures_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    vix_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    dxy_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    global_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    global_sentiment: Mapped[str | None] = mapped_column(String(16), nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class GlobalCondition(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "global_conditions"
    __table_args__ = (UniqueConstraint("snapshot_date", name="uq_global_cond_date"),)

    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    feature_vector: Mapped[str] = mapped_column(Text, nullable=False)
    region_scores_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome_returns_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class GlobalSimilarityResult(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "global_similarity_results"

    query_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    matched_date: Mapped[date] = mapped_column(Date, nullable=False)
    similarity_pct: Mapped[float] = mapped_column(Float, nullable=False)
    historical_outcomes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    winning_stocks_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    losing_stocks_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    avg_return_1d: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_return_5d: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_return_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_return_60d: Mapped[float | None] = mapped_column(Float, nullable=True)
