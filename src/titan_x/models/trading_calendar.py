from datetime import date, datetime, time

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


# ── Trading Holidays ─────────────────────────────────────────────────────────


class TradingHoliday(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "trading_holidays"
    __table_args__ = (
        UniqueConstraint("exchange", "holiday_date", name="uq_th_exchange_date"),
        Index("ix_th_exchange", "exchange"),
        Index("ix_th_year", "year"),
        Index("ix_th_date", "holiday_date"),
    )

    exchange: Mapped[str] = mapped_column(String(16), nullable=False)
    holiday_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    segment: Mapped[str | None] = mapped_column(String(32), nullable=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


# ── Special Sessions ─────────────────────────────────────────────────────────


class SpecialSession(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "special_sessions"
    __table_args__ = (
        UniqueConstraint("exchange", "session_date", "session_type",
                         name="uq_ss_exch_date_type"),
        Index("ix_ss_exchange", "exchange"),
        Index("ix_ss_date", "session_date"),
    )

    exchange: Mapped[str] = mapped_column(String(16), nullable=False)
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    session_type: Mapped[str] = mapped_column(
        String(32), nullable=False,
    )
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    segment: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


# ── Expiry Calendar ──────────────────────────────────────────────────────────


class ExpiryCalendar(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "expiry_calendar"
    __table_args__ = (
        UniqueConstraint("exchange", "instrument_type", "underlying", "expiry_date",
                         name="uq_ec_exch_inst_under_exp"),
        Index("ix_ec_exchange", "exchange"),
        Index("ix_ec_underlying", "underlying"),
        Index("ix_ec_expiry", "expiry_date"),
    )

    exchange: Mapped[str] = mapped_column(String(16), nullable=False)
    instrument_type: Mapped[str] = mapped_column(
        String(32), nullable=False,
    )
    underlying: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_month: Mapped[str | None] = mapped_column(String(16), nullable=True)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    contract_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    strike_price: Mapped[float | None] = mapped_column(nullable=True)
    option_type: Mapped[str | None] = mapped_column(String(8), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


# ── Settlement Calendar ──────────────────────────────────────────────────────


class SettlementCalendar(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "settlement_calendar"
    __table_args__ = (
        UniqueConstraint("exchange", "trade_date", "settlement_type",
                         name="uq_sc_exch_trade_type"),
        Index("ix_sc_exchange", "exchange"),
        Index("ix_sc_trade_date", "trade_date"),
        Index("ix_sc_settlement_date", "settlement_date"),
    )

    exchange: Mapped[str] = mapped_column(String(16), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    settlement_date: Mapped[date] = mapped_column(Date, nullable=False)
    settlement_type: Mapped[str] = mapped_column(
        String(32), nullable=False,
    )
    segment: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)


# ── Corporate Calendar ───────────────────────────────────────────────────────


class CorporateCalendar(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "corporate_calendar"
    __table_args__ = (
        Index("ix_cc_symbol", "symbol"),
        Index("ix_cc_event_type", "event_type"),
        Index("ix_cc_ex_date", "ex_date"),
        Index("ix_cc_announcement", "announcement_date"),
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    event_type: Mapped[str] = mapped_column(
        String(32), nullable=False,
    )
    announcement_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    record_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    ex_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)

    reminders: Mapped[list["CorporateReminder"]] = relationship(
        "CorporateReminder", back_populates="event",
        cascade="all, delete-orphan", passive_deletes=True,
    )


# ── Corporate Reminders ──────────────────────────────────────────────────────


class CorporateReminder(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "corporate_reminders"
    __table_args__ = (
        Index("ix_cr_user_status", "user_id", "status"),
        Index("ix_cr_reminder_date", "reminder_date"),
        Index("ix_cr_event_type", "event_type"),
        UniqueConstraint("user_id", "event_id", "days_before",
                         name="uq_cr_user_event_days"),
    )

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("corporate_calendar.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    days_before: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    reminder_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="pending", nullable=False,
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notification_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("notification_history.id", ondelete="SET NULL"),
        nullable=True,
    )

    event: Mapped[CorporateCalendar] = relationship(
        CorporateCalendar, back_populates="reminders",
    )
