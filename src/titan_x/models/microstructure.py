from datetime import date

from sqlalchemy import BigInteger, Date, Float, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class MarketMicrostructure(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "market_microstructure"
    __table_args__ = (
        UniqueConstraint("symbol", "as_of_date", name="uq_microstructure_sym_date"),
        Index("ix_microstructure_symbol", "symbol"),
        Index("ix_microstructure_date", "as_of_date"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)

    # --- Volume ---
    volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    avg_volume_5d: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    avg_volume_20d: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    volume_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_percentile_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_trend: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # --- Delivery ---
    delivery_quantity: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    total_traded_quantity: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    delivery_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    delivery_trend: Mapped[str | None] = mapped_column(String(16), nullable=True)
    delivery_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Spread ---
    avg_spread_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    spread_volatility: Mapped[float | None] = mapped_column(Float, nullable=True)
    spread_regime: Mapped[str | None] = mapped_column(String(16), nullable=True)
    spread_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Market Depth ---
    dollar_volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_dollar_volume_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    depth_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Turnover ---
    turnover: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_turnover_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    turnover_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    free_float_turnover: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Composite Liquidity ---
    liquidity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    amihud_illiquidity: Mapped[float | None] = mapped_column(Float, nullable=True)
    liquidity_rating: Mapped[str | None] = mapped_column(String(16), nullable=True)

    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
