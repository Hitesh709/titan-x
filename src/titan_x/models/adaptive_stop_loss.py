from datetime import date

from sqlalchemy import Boolean, Date, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class AdaptiveStopLoss(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "adaptive_stop_loss"
    __table_args__ = (
        Index("ix_asl_symbol", "symbol"),
        Index("ix_asl_date", "trade_date"),
        Index("ix_asl_active", "symbol", "is_active"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- ATR-based ---
    atr_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    atr_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=2.0)
    sl_price_atr: Mapped[float | None] = mapped_column(Float, nullable=True)
    sl_pct_atr: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Support-based ---
    nearest_support: Mapped[float | None] = mapped_column(Float, nullable=True)
    support_distance_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    support_strength: Mapped[float | None] = mapped_column(Float, nullable=True)
    sl_price_support: Mapped[float | None] = mapped_column(Float, nullable=True)
    sl_pct_support: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Volatility-based ---
    volatility_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    volatility_60d: Mapped[float | None] = mapped_column(Float, nullable=True)
    vol_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=1.5)
    sl_price_volatility: Mapped[float | None] = mapped_column(Float, nullable=True)
    sl_pct_volatility: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Regime-based ---
    trend_regime: Mapped[str | None] = mapped_column(String(16), nullable=True)
    volatility_regime: Mapped[str | None] = mapped_column(String(16), nullable=True)
    regime_adjustment: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Liquidity-based ---
    liquidity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    liquidity_rating: Mapped[str | None] = mapped_column(String(16), nullable=True)
    liq_adjustment: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Composite ---
    composite_stop_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    composite_stop_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    method: Mapped[str] = mapped_column(String(32), nullable=False, default="composite")

    # --- Trailing ---
    trailing_activation_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_trailing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- Status ---
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
