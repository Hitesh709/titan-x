from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from titan_x.db.base import Base
from titan_x.db.mixins import PrimaryKeyMixin, TimestampMixin


class NewsCategory(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "news_categories"

    name: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)

    articles: Mapped[list["NewsArticle"]] = relationship(
        secondary="news_article_categories", back_populates="categories",
    )


class NewsArticle(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "news_articles"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_news_article_source_id"),
        Index("ix_news_articles_published_at", "published_at"),
        Index("ix_news_articles_symbol", "symbol"),
        Index("ix_news_articles_source", "source"),
        Index("ix_news_articles_url_hash", "url_hash"),
    )

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(256), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(16), nullable=True)
    author: Mapped[str | None] = mapped_column(String(128), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    language: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    is_cleaned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)

    categories: Mapped[list["NewsCategory"]] = relationship(
        secondary="news_article_categories", back_populates="articles",
    )

    nlp_analysis: Mapped["NewsNLPAnalysis | None"] = relationship(
        back_populates="article", uselist=False, cascade="all, delete-orphan",
    )
    entities: Mapped[list["NewsEntity"]] = relationship(
        back_populates="article", cascade="all, delete-orphan",
    )


class NewsArticleCategory(PrimaryKeyMixin, Base):
    __tablename__ = "news_article_categories"
    __table_args__ = (
        UniqueConstraint("article_id", "category_id", name="uq_news_article_category"),
    )

    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("news_articles.id", ondelete="CASCADE"), nullable=False,
    )
    category_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("news_categories.id", ondelete="CASCADE"), nullable=False,
    )
