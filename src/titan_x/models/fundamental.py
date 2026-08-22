from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class FundamentalMetric(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "fundamental_metrics"
    __table_args__ = (
        UniqueConstraint("symbol", "fiscal_year", "fiscal_period", "period_type", "metric_name",
                         name="uq_fund_metric_symbol_year_period_name"),
        Index("ix_fund_metric_symbol_name", "symbol", "metric_name"),
        Index("ix_fund_metric_symbol_published", "symbol", "published_at"),
        Index("ix_fund_metric_published", "published_at"),
        Index("ix_fund_metric_fiscal_year", "fiscal_year"),
    )

    symbol: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    fiscal_year: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fiscal_period: Mapped[int] = mapped_column(BigInteger, nullable=False)
    period_type: Mapped[str] = mapped_column(String(16), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Point-in-time availability date. Historical screens must never use a
    # filing that was published after the requested as-of date.
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
