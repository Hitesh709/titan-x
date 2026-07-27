from datetime import date

from sqlalchemy import Boolean, Date, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class AIRankingV2(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_ranking_v2"
    __table_args__ = (
        UniqueConstraint("symbol", "as_of_date", name="uq_airv2_sym_date"),
        Index("ix_airv2_score", "weighted_ai_score"),
        Index("ix_airv2_tier", "tier"),
        Index("ix_airv2_symbol", "symbol"),
        Index("ix_airv2_date", "as_of_date"),
    )

    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)

    weighted_ai_score: Mapped[float] = mapped_column(Float, nullable=False)
    base_score: Mapped[float] = mapped_column(Float, nullable=False)
    technical_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    fundamental_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    momentum_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    dynamic_weight_technical: Mapped[float | None] = mapped_column(Float, nullable=True)
    dynamic_weight_fundamental: Mapped[float | None] = mapped_column(Float, nullable=True)
    dynamic_weight_sentiment: Mapped[float | None] = mapped_column(Float, nullable=True)
    dynamic_weight_momentum: Mapped[float | None] = mapped_column(Float, nullable=True)

    model_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    market_regime: Mapped[str | None] = mapped_column(String(32), nullable=True)
    regime_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    historical_success_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    historical_avg_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    historical_sharpe: Mapped[float | None] = mapped_column(Float, nullable=True)

    tier: Mapped[str] = mapped_column(String(16), nullable=False)
    is_best_opportunity: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    explanation_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class RankingModelWeight(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ranking_model_weights"
    __table_args__ = (
        UniqueConstraint("model_name", "as_of_date", name="uq_rmw_name_date"),
        Index("ix_rmw_name", "model_name"),
        Index("ix_rmw_date", "as_of_date"),
    )

    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    weight_technical: Mapped[float] = mapped_column(Float, nullable=False)
    weight_fundamental: Mapped[float] = mapped_column(Float, nullable=False)
    weight_sentiment: Mapped[float] = mapped_column(Float, nullable=False)
    weight_momentum: Mapped[float] = mapped_column(Float, nullable=False)
    market_regime: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    historical_success_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
