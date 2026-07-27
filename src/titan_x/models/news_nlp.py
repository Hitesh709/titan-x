from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class NewsNLPAnalysis(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "news_nlp_analysis"

    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("news_articles.id", ondelete="CASCADE"),
        unique=True, nullable=False, index=True,
    )
    is_processed: Mapped[bool] = mapped_column(default=False, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sentiment_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sentiment_positive: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_negative: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_neutral: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    detected_events: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    mapped_sector: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sector_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    mapped_company_symbol: Mapped[str | None] = mapped_column(String(16), nullable=True)
    company_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    overall_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    article: Mapped["NewsArticle"] = relationship(back_populates="nlp_analysis")


class NewsEntity(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "news_entities"
    __table_args__ = (
        Index("ix_news_entities_article_id", "article_id"),
    )

    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("news_articles.id", ondelete="CASCADE"), nullable=False,
    )
    entity_text: Mapped[str] = mapped_column(String(256), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    article: Mapped["NewsArticle"] = relationship(back_populates="entities")
