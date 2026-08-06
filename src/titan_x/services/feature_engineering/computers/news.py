"""News features (article counts, sentiment, ratios)."""
from datetime import date, timedelta

from sqlalchemy import select

from titan_x.models.news import NewsArticle
from titan_x.models.news_nlp import NewsNLPAnalysis


class NewsFeaturesMixin:
    async def _compute_news_features(self, symbol: str, as_of_date: date) -> int:
        count = 0
        lookback_start = as_of_date - timedelta(days=7)

        # Get articles for symbol in last 7 days
        articles_r = await self.session.execute(
            select(NewsArticle).where(
                NewsArticle.symbol == symbol,
                NewsArticle.published_at >= lookback_start,
                NewsArticle.published_at <= as_of_date,
            )
        )
        articles = list(articles_r.scalars().all())
        article_ids = [a.id for a in articles]

        # news_count_7d
        fd = await self._get_or_create_definition(
            "news_count_7d", "news",
            description="Number of news articles in last 7 days",
            formula="count(articles)", source="news_article",
        )
        await self._upsert_value(fd.id, symbol, as_of_date, len(articles),
                                 {"lookback_days": 7, "article_ids": article_ids[:10] if article_ids else []})
        count += 1

        if not article_ids:
            # No news, but we still record sentiment_score_7d as None-skip
            return count

        # Get NLP analysis for those articles
        nlp_r = await self.session.execute(
            select(NewsNLPAnalysis).where(
                NewsNLPAnalysis.article_id.in_(article_ids),
                NewsNLPAnalysis.is_processed.is_(True),
            )
        )
        analyses = list(nlp_r.scalars().all())

        if not analyses:
            return count

        # sentiment_score_7d: avg sentiment positive score
        sentiments = [a.sentiment_positive for a in analyses if a.sentiment_positive is not None]
        if sentiments:
            avg_sentiment = sum(sentiments) / len(sentiments)
            fd = await self._get_or_create_definition(
                "sentiment_score_7d", "news",
                description="Average news sentiment score over 7 days",
                formula="avg(sentiment_positive)", source="news_nlp",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(avg_sentiment, 4),
                                     {"article_count": len(analyses), "lookback_days": 7})
            count += 1

        # positive_news_ratio_7d
        if analyses:
            positive_count = sum(1 for a in analyses if a.sentiment_label == "positive")
            ratio = positive_count / len(analyses)
            fd = await self._get_or_create_definition(
                "positive_news_ratio_7d", "news",
                description="Ratio of positive news articles over 7 days",
                formula="positive_articles / total_articles", source="news_nlp",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(ratio, 4))
            count += 1

        # avg_sentiment_confidence
        confidences = [a.sentiment_confidence for a in analyses if a.sentiment_confidence is not None]
        if confidences:
            avg_conf = sum(confidences) / len(confidences)
            fd = await self._get_or_create_definition(
                "avg_sentiment_confidence", "news",
                description="Average sentiment confidence score",
                formula="avg(sentiment_confidence)", source="news_nlp",
            )
            await self._upsert_value(fd.id, symbol, as_of_date, round(avg_conf, 4))
            count += 1

        return count