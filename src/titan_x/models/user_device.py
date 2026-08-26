from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin


class UserDevice(PrimaryKeyMixin, Base):
    __tablename__ = "user_devices"

    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_name: Mapped[str] = mapped_column(String(120), nullable=False)
    device_public_key: Mapped[str] = mapped_column(Text, nullable=False)
    device_status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer: Mapped["User"] = relationship("User", back_populates="devices")  # type: ignore[name-defined]

    @property
    def is_active(self) -> bool:
        return self.device_status == "active" and self.revoked_at is None
