from datetime import date

from sqlalchemy import Date, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class ProfessionalReport(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "professional_reports"
    __table_args__ = (
        Index("ix_prr_symbol", "symbol"),
        Index("ix_prr_date", "trade_date"),
        Index("ix_prr_symbol_date", "symbol", "trade_date"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="bullish")
    current_price: Mapped[float] = mapped_column(Float, nullable=False)

    summary_json: Mapped[str] = mapped_column(Text, nullable=True)
    technical_json: Mapped[str] = mapped_column(Text, nullable=True)
    fundamental_json: Mapped[str] = mapped_column(Text, nullable=True)
    news_json: Mapped[str] = mapped_column(Text, nullable=True)
    risk_json: Mapped[str] = mapped_column(Text, nullable=True)
    prediction_json: Mapped[str] = mapped_column(Text, nullable=True)

    html_content: Mapped[str] = mapped_column(Text, nullable=False)

    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
