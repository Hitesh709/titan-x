from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin


class AuthChallenge(PrimaryKeyMixin, Base):
    __tablename__ = "auth_challenges"
    __table_args__ = (
        Index("ix_auth_challenges_status_expires_at", "status", "expires_at"),
        Index("ix_auth_challenges_browser_session_id", "browser_session_id"),
        Index("ix_auth_challenges_operation", "operation"),
    )

    challenge_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    challenge_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    browser_session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(20), default="LOGIN", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("user_devices.id", ondelete="SET NULL"), nullable=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    registration_username: Mapped[str | None] = mapped_column(String(80), nullable=True)
    registration_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    registration_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    registration_password_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    email_otp_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email_otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_otp_attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    email_otp_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer: Mapped["User | None"] = relationship("User", foreign_keys=[customer_id])  # type: ignore[name-defined]
    device: Mapped["UserDevice | None"] = relationship("UserDevice", foreign_keys=[device_id])  # type: ignore[name-defined]
