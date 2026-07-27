from datetime import date

from sqlalchemy import Date, Float, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class CompanyResearch(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "company_research"
    __table_args__ = (
        Index("ix_cr_symbol", "symbol"),
        Index("ix_cr_date", "as_of_date"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)

    business_json: Mapped[str] = mapped_column(Text, nullable=True)
    financials_json: Mapped[str] = mapped_column(Text, nullable=True)
    risks_json: Mapped[str] = mapped_column(Text, nullable=True)
    growth_json: Mapped[str] = mapped_column(Text, nullable=True)
    competition_json: Mapped[str] = mapped_column(Text, nullable=True)
    ai_summary: Mapped[str] = mapped_column(Text, nullable=True)

    html_content: Mapped[str] = mapped_column(Text, nullable=False)
