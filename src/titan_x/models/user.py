from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, SoftDeleteMixin, TimestampMixin


class User(PrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fcm_token: Mapped[str | None] = mapped_column(Text, nullable=True)

    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user", cascade="all, delete-orphan")  # type: ignore[name-defined]
    preferences: Mapped[list["UserPreference"]] = relationship(back_populates="user", cascade="all, delete-orphan")  # type: ignore[name-defined]
    broker_connections: Mapped[list["BrokerConnection"]] = relationship(back_populates="user", cascade="all, delete-orphan")  # type: ignore[name-defined]
    orders: Mapped[list["Order"]] = relationship(back_populates="user", cascade="all, delete-orphan")  # type: ignore[name-defined]
    positions: Mapped[list["Position"]] = relationship(back_populates="user", cascade="all, delete-orphan")  # type: ignore[name-defined]
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(  # type: ignore[name-defined]
        "RefreshToken", back_populates="user", cascade="all, delete-orphan",
    )
