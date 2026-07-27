from datetime import date

from sqlalchemy import Boolean, Date, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class OpportunityRejection(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "opportunity_rejections"
    __table_args__ = (
        Index("ix_orj_symbol", "symbol"),
        Index("ix_orj_date", "trade_date"),
        Index("ix_orj_rejected", "symbol", "is_rejected"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="bullish")

    # Dimension scores (0-100, higher = better)
    liquidity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    news_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    financial_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    trend_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Dimension reasons
    liquidity_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    risk_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    news_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    financial_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    trend_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    market_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)

    composite_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_rejected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
