from datetime import date

from sqlalchemy import BigInteger, Date, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class SimilarityAnalysis(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "similarity_analyses"
    __table_args__ = (
        Index("ix_sa_symbol", "symbol"),
        Index("ix_sa_created", "created_at"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    query_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    query_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    lookback_days: Mapped[int] = mapped_column(Integer, nullable=False)
    max_matches: Mapped[int] = mapped_column(Integer, nullable=False)
    min_similarity: Mapped[float] = mapped_column(Float, nullable=False)
    total_matches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    worst_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_return_1d: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_return_5d: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_return_10d: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_return_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_return_60d: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_holding_period: Mapped[float | None] = mapped_column(Float, nullable=True)
    optimal_holding_period: Mapped[int | None] = mapped_column(Integer, nullable=True)
    optimal_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class SimilarityMatch(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "similarity_matches"
    __table_args__ = (
        Index("ix_sm_analysis_id", "analysis_id"),
        Index("ix_sm_rank", "analysis_id", "match_rank"),
    )

    analysis_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    match_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    match_symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    match_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    match_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    price_correlation: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_distance: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    forward_return_1d: Mapped[float | None] = mapped_column(Float, nullable=True)
    forward_return_5d: Mapped[float | None] = mapped_column(Float, nullable=True)
    forward_return_10d: Mapped[float | None] = mapped_column(Float, nullable=True)
    forward_return_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    forward_return_60d: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
