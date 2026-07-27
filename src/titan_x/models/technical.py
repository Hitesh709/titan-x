from datetime import date

from sqlalchemy import BigInteger, Date, Float, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class TechnicalIndicator(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "technical_indicators"
    __table_args__ = (
        UniqueConstraint("symbol", "trade_date", "indicator", "params_hash",
                         name="uq_tech_indicator_symbol_date_indicator_params"),
        Index("ix_tech_indicator_symbol_indicator", "symbol", "indicator"),
        Index("ix_tech_indicator_trade_date", "trade_date"),
    )

    symbol: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    indicator: Mapped[str] = mapped_column(String(32), nullable=False)
    params_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    period: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    params: Mapped[str | None] = mapped_column(Text, nullable=True)

    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_secondary: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_tertiary: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
