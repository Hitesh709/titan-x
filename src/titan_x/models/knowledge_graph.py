from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class Sector(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_sectors"
    __table_args__ = (
        Index("ix_kg_sector_name", "name"),
    )

    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    sector_code: Mapped[str | None] = mapped_column(String(16), unique=True, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    industries: Mapped[list["Industry"]] = relationship(back_populates="sector", cascade="all, delete-orphan")
    events: Mapped[list["EntityEvent"]] = relationship(
        back_populates="sector", cascade="all, delete-orphan",
        foreign_keys="EntityEvent.sector_id",
    )


class Industry(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_industries"
    __table_args__ = (
        Index("ix_kg_industry_name", "name"),
    )

    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    industry_code: Mapped[str | None] = mapped_column(String(16), unique=True, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sector_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("knowledge_sectors.id", ondelete="SET NULL"), nullable=True)

    sector: Mapped["Sector | None"] = relationship(back_populates="industries")
    events: Mapped[list["EntityEvent"]] = relationship(
        back_populates="industry", cascade="all, delete-orphan",
        foreign_keys="EntityEvent.industry_id",
    )


class Promoter(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_promoters"
    __table_args__ = (
        Index("ix_kg_promoter_name", "name"),
    )

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    promoter_type: Mapped[str] = mapped_column(String(32), default="individual", nullable=False)
    pan: Mapped[str | None] = mapped_column(String(16), unique=True, nullable=True)
    cin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    company_links: Mapped[list["CompanyPromoter"]] = relationship(back_populates="promoter", cascade="all, delete-orphan")
    events: Mapped[list["EntityEvent"]] = relationship(
        back_populates="promoter", cascade="all, delete-orphan",
        foreign_keys="EntityEvent.promoter_id",
    )


class CompanyPromoter(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_company_promoters"
    __table_args__ = (
        Index("ix_kg_cp_company", "company_id"),
        Index("ix_kg_cp_promoter", "promoter_id"),
        Index("ix_kg_cp_unique", "company_id", "promoter_id", unique=True),
    )

    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    promoter_id: Mapped[int] = mapped_column(Integer, ForeignKey("knowledge_promoters.id", ondelete="CASCADE"), nullable=False)
    ownership_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    promoter: Mapped["Promoter"] = relationship(back_populates="company_links")


class Subsidiary(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_subsidiaries"
    __table_args__ = (
        Index("ix_kg_sub_parent", "parent_company_id"),
        Index("ix_kg_sub_subsidiary", "subsidiary_company_id"),
        Index("ix_kg_sub_unique", "parent_company_id", "subsidiary_company_id", unique=True),
    )

    parent_company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    subsidiary_company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    ownership_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    relationship_type: Mapped[str] = mapped_column(String(32), default="subsidiary", nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class EntityEvent(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_entity_events"
    __table_args__ = (
        Index("ix_kg_ev_type", "event_type"),
        Index("ix_kg_ev_date", "event_date"),
        Index("ix_kg_ev_company", "company_id"),
    )

    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    impact_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    company_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)
    sector_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("knowledge_sectors.id", ondelete="SET NULL"), nullable=True)
    industry_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("knowledge_industries.id", ondelete="SET NULL"), nullable=True)
    promoter_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("knowledge_promoters.id", ondelete="SET NULL"), nullable=True)

    sector: Mapped["Sector | None"] = relationship(back_populates="events", foreign_keys=[sector_id])
    industry: Mapped["Industry | None"] = relationship(back_populates="events", foreign_keys=[industry_id])
    promoter: Mapped["Promoter | None"] = relationship(back_populates="events", foreign_keys=[promoter_id])


class BusinessRelationship(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_business_relationships"
    __table_args__ = (
        Index("ix_kg_br_source", "source_entity_type", "source_entity_id"),
        Index("ix_kg_br_target", "target_entity_type", "target_entity_id"),
    )

    source_entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    target_entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(32), nullable=False)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
