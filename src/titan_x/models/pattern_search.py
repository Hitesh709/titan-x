from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class PatternSearchQuery(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "pattern_search_queries"
    __table_args__ = (
        Index("ix_psq_symbol", "symbol"),
        Index("ix_psq_created", "created_at"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    pattern_type: Mapped[str] = mapped_column(String(32), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    lookback_years: Mapped[int] = mapped_column(Integer, nullable=False)
    total_matches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_return_1d: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_return_5d: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_return_10d: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_return_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_return_60d: Mapped[float | None] = mapped_column(Float, nullable=True)
    optimal_holding_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class PatternSearchMatch(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "pattern_search_matches"
    __table_args__ = (
        Index("ix_psm_query_id", "query_id"),
        Index("ix_psm_rank", "query_id", "match_rank"),
    )

    query_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pattern_search_queries.id", ondelete="CASCADE"), nullable=False,
    )
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
    is_winning: Mapped[bool | None] = mapped_column(nullable=True, default=None)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
