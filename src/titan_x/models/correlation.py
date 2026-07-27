from datetime import date

from sqlalchemy import Date, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class CorrelationPair(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "correlation_pairs"
    __table_args__ = (
        UniqueConstraint("correlation_type", "symbol_1", "symbol_2", "lookback_days", name="uq_corr_type_sym1_sym2_lb"),
    )

    correlation_type: Mapped[str] = mapped_column(String(20), nullable=False)
    symbol_1: Mapped[str] = mapped_column(String(16), nullable=False)
    symbol_2: Mapped[str] = mapped_column(String(16), nullable=False)
    correlation_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    lookback_days: Mapped[int] = mapped_column(Integer, nullable=False, default=252)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    samples: Mapped[int | None] = mapped_column(Integer, nullable=True)


class CorrelationMatrix(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "correlation_matrices"
    __table_args__ = (
        UniqueConstraint("matrix_type", "label", "as_of_date", "lookback_days", name="uq_corr_matrix_type_label_date_lb"),
    )

    matrix_type: Mapped[str] = mapped_column(String(20), nullable=False)
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    lookback_days: Mapped[int] = mapped_column(Integer, nullable=False, default=252)
    symbols_json: Mapped[str] = mapped_column(Text, nullable=False)
    matrix_json: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
