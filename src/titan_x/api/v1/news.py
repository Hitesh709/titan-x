import asyncio
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from titan_x.api.dependencies import get_cache, get_news_engine, require_api_key
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.infrastructure.cache import RedisCache
from titan_x.services.news_engine import NewsEngine

news_router = APIRouter(
    prefix="/news",
    tags=["news"],
    dependencies=[Depends(require_api_key)],
)


class CategoryResponse(BaseModel):
    id: int
    name: str
    description: str | None


class NewsArticleResponse(BaseModel):
    id: int
    title: str
    summary: str | None
    content: str | None
    source: str
    source_id: str
    url: str
    symbol: str | None
    author: str | None
    published_at: str | None
    language: str
    is_cleaned: bool
    categories: list[CategoryResponse]


class IngestResponse(BaseModel):
    total: int
    created: int
    duplicates: int
    errors: int
    errors_detail: list[str]


class NewsStatsResponse(BaseModel):
    total_articles: int
    per_source: dict[str, int]


class IngestRequest(BaseModel):
    source: str = Field(min_length=1, max_length=64)
    articles: list[dict[str, Any]]
    run_nlp: bool = True


@news_router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_news(
    body: IngestRequest,
    engine: Annotated[NewsEngine, Depends(get_news_engine)],
) -> IngestResponse:
    result = await engine.ingest(body.source, body.articles, run_nlp=body.run_nlp)
    return IngestResponse(**result)


@news_router.get("/search", response_model=PaginatedResponse[NewsArticleResponse])
async def search_news(
    engine: Annotated[NewsEngine, Depends(get_news_engine)],
    query: str | None = Query(None, min_length=2),
    symbol: str | None = Query(None, min_length=1, max_length=16),
    source: str | None = Query(None, min_length=1),
    category: str | None = Query(None, min_length=1),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[NewsArticleResponse]:
    articles, total = await engine.search(
        query=query, symbol=symbol, source=source, category=category,
        date_from=date_from, date_to=date_to, skip=skip, limit=limit,
    )
    items = [_article_response(a) for a in articles]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@news_router.get("/{article_id}", response_model=NewsArticleResponse)
async def get_article(
    article_id: int,
    engine: Annotated[NewsEngine, Depends(get_news_engine)],
) -> NewsArticleResponse:
    article = await engine.get_by_id(article_id)
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return _article_response(article)


@news_router.get("", response_model=PaginatedResponse[NewsArticleResponse])
async def list_news(
    engine: Annotated[NewsEngine, Depends(get_news_engine)],
    cache: Annotated[RedisCache, Depends(get_cache)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[NewsArticleResponse]:
    cache_key = f"news:list:{skip}:{limit}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return PaginatedResponse[NewsArticleResponse](**cached)
    articles, total = await engine.search(skip=skip, limit=limit)
    items = [_article_response(a) for a in articles]
    response = PaginatedResponse(items=items, total=total, skip=skip, limit=limit)
    asyncio.ensure_future(cache.set(cache_key, response.model_dump(), ttl=30))
    return response


@news_router.get("/meta/sources", response_model=list[str])
async def list_sources(
    engine: Annotated[NewsEngine, Depends(get_news_engine)],
) -> list[str]:
    return await engine.list_sources()


@news_router.get("/meta/categories", response_model=list[CategoryResponse])
async def list_categories(
    engine: Annotated[NewsEngine, Depends(get_news_engine)],
) -> list[CategoryResponse]:
    categories = await engine.list_categories()
    return [CategoryResponse(**c.__dict__) for c in categories]


@news_router.get("/meta/stats", response_model=NewsStatsResponse)
async def get_stats(
    engine: Annotated[NewsEngine, Depends(get_news_engine)],
) -> NewsStatsResponse:
    stats = await engine.get_stats()
    return NewsStatsResponse(**stats)


@news_router.delete("/{article_id}", response_model=MessageResponse)
async def delete_article(
    article_id: int,
    engine: Annotated[NewsEngine, Depends(get_news_engine)],
) -> MessageResponse:
    deleted = await engine.delete_article(article_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return MessageResponse(message="Article deleted")


def _article_response(article: Any) -> NewsArticleResponse:
    return NewsArticleResponse(
        id=article.id, title=article.title, summary=article.summary,
        content=article.content, source=article.source,
        source_id=article.source_id, url=article.url,
        symbol=article.symbol, author=article.author,
        published_at=article.published_at.isoformat() if article.published_at else None,
        language=article.language, is_cleaned=article.is_cleaned,
        categories=[CategoryResponse(id=c.id, name=c.name, description=c.description) for c in article.categories],
    )
