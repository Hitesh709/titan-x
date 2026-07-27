from datetime import date

from sqlalchemy import Date, Float, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class MacroIndicator(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "macro_indicators"
    __table_args__ = (
        UniqueConstraint("indicator_type", "as_of_date", name="uq_macro_type_date"),
        Index("ix_macro_type", "indicator_type"),
        Index("ix_macro_date", "as_of_date"),
    )

    indicator_type: Mapped[str] = mapped_column(String(32), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class MacroAnalysis(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "macro_analyses"
    __table_args__ = (
        UniqueConstraint("as_of_date", name="uq_macro_analysis_date"),
    )

    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    interest_rate_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    inflation_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    gdp_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    bond_yield_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    oil_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    gold_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    composite_macro_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    macro_regime: Mapped[str | None] = mapped_column(String(24), nullable=True)
    growth_inflation_regime: Mapped[str | None] = mapped_column(String(24), nullable=True)
    risk_regime: Mapped[str | None] = mapped_column(String(24), nullable=True)

    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class MacroFeature(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "macro_features"
    __table_args__ = (
        UniqueConstraint("feature_name", "as_of_date", name="uq_macro_feature_name_date"),
        Index("ix_macro_feature_name", "feature_name"),
        Index("ix_macro_feature_date", "as_of_date"),
    )

    feature_name: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)
