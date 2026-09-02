from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class CompanyListing(PrimaryKeyMixin, TimestampMixin, Base):
    """Exchange-specific listing identity for a company/security."""

    __tablename__ = "company_listings"
    __table_args__ = (
        UniqueConstraint("exchange", "symbol", name="uq_company_listing_exchange_symbol"),
        UniqueConstraint("company_id", "exchange", name="uq_company_listing_company_exchange"),
    )

    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    yahoo_symbol: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)

    company: Mapped["Company"] = relationship(back_populates="listings")
