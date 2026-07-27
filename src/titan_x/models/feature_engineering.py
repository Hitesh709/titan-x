from datetime import date

from sqlalchemy import Boolean, Date, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class FeatureDefinition(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feature_definitions"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_feat_def_name_version"),
        Index("ix_feature_def_category", "category"),
    )

    name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    formula: Mapped[str | None] = mapped_column(Text, nullable=True)
    parameters: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    values: Mapped[list["FeatureValue"]] = relationship(
        back_populates="definition", cascade="all, delete-orphan",
    )


class FeatureValue(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feature_values"
    __table_args__ = (
        UniqueConstraint(
            "feature_definition_id", "symbol", "as_of_date",
            name="uq_feature_val_def_sym_date",
        ),
        Index("ix_feature_values_sym_date", "symbol", "as_of_date"),
        Index("ix_feature_values_def_id", "feature_definition_id"),
    )

    feature_definition_id: Mapped[int] = mapped_column(
        ForeignKey("feature_definitions.id", ondelete="CASCADE"), nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    definition: Mapped["FeatureDefinition"] = relationship(back_populates="values")
