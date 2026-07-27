from datetime import date

from sqlalchemy import BigInteger, Date, Float, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class SectorPerformance(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sector_performance"
    __table_args__ = (
        UniqueConstraint("sector", "as_of_date", "period_label", name="uq_sector_perf_date_period"),
        Index("ix_sector_perf_sector", "sector"),
        Index("ix_sector_perf_as_of_date", "as_of_date"),
    )

    sector: Mapped[str] = mapped_column(String(128), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_label: Mapped[str] = mapped_column(String(16), nullable=False)
    return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    momentum_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    relative_strength: Mapped[float | None] = mapped_column(Float, nullable=True)
    rank: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    constituent_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    total_return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
