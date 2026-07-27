from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from titan_x.api.dependencies import get_news_engine, get_news_nlp_engine, require_api_key
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.services.news_engine import NewsEngine
from titan_x.services.news_nlp import NewsNLPEngine

news_nlp_router = APIRouter(
    prefix="/news-nlp",
    tags=["news-nlp"],
    dependencies=[Depends(require_api_key)],
)


class SentimentResponse(BaseModel):
    label: str
    positive: float
    negative: float
    neutral: float
    confidence: float


class EntityResponse(BaseModel):
    id: int
    entity_text: str
    entity_type: str
    confidence: float | None
    metadata_json: str | None


class NLPAnalysisResponse(BaseModel):
    id: int
    article_id: int
    is_processed: bool
    processed_at: str | None
    sentiment: SentimentResponse
    detected_events: list[dict[str, str]] | None
    event_confidence: float | None
    mapped_sector: str | None
    sector_confidence: float | None
    mapped_company_symbol: str | None
    company_confidence: float | None
    overall_confidence: float | None
    entities: list[EntityResponse]


class NLPStatsResponse(BaseModel):
    total_processed: int
    per_sentiment: dict[str, int]
    per_sector: dict[str, int]


@news_nlp_router.post("/process/{article_id}", response_model=NLPAnalysisResponse)
async def process_article(
    article_id: int,
    engine: Annotated[NewsNLPEngine, Depends(get_news_nlp_engine)],
) -> NLPAnalysisResponse:
    try:
        analysis = await engine.process_article(article_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    entities = await engine.get_entities(article_id)
    return _analysis_response(analysis, entities)


@news_nlp_router.post("/process-batch", response_model=dict[str, int])
async def process_batch(
    engine: Annotated[NewsNLPEngine, Depends(get_news_nlp_engine)],
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, int]:
    processed = await engine.process_unprocessed(limit)
    return {"processed": processed}


@news_nlp_router.get("/{article_id}", response_model=NLPAnalysisResponse)
async def get_analysis(
    article_id: int,
    engine: Annotated[NewsNLPEngine, Depends(get_news_nlp_engine)],
) -> NLPAnalysisResponse:
    analysis = await engine.get_analysis(article_id)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NLP analysis not found for this article")
    entities = await engine.get_entities(article_id)
    return _analysis_response(analysis, entities)


@news_nlp_router.get("/sentiment/{label}", response_model=PaginatedResponse[dict[str, Any]])
async def search_by_sentiment(
    label: str,
    engine_nlp: Annotated[NewsNLPEngine, Depends(get_news_nlp_engine)],
    engine: Annotated[NewsEngine, Depends(get_news_engine)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> PaginatedResponse[dict[str, Any]]:
    if label not in ("positive", "negative", "neutral"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Label must be positive, negative, or neutral")
    articles, total = await engine_nlp.search_by_sentiment(label, skip=skip, limit=limit)
    items = [_article_summary(a) for a in articles]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@news_nlp_router.get("/sector/{sector}", response_model=PaginatedResponse[dict[str, Any]])
async def search_by_sector(
    sector: str,
    engine_nlp: Annotated[NewsNLPEngine, Depends(get_news_nlp_engine)],
    engine: Annotated[NewsEngine, Depends(get_news_engine)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> PaginatedResponse[dict[str, Any]]:
    articles, total = await engine_nlp.search_by_sector(sector, skip=skip, limit=limit)
    items = [_article_summary(a) for a in articles]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@news_nlp_router.get("/event/{event_type}", response_model=PaginatedResponse[dict[str, Any]])
async def search_by_event(
    event_type: str,
    engine_nlp: Annotated[NewsNLPEngine, Depends(get_news_nlp_engine)],
    engine: Annotated[NewsEngine, Depends(get_news_engine)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> PaginatedResponse[dict[str, Any]]:
    articles, total = await engine_nlp.search_by_event(event_type, skip=skip, limit=limit)
    items = [_article_summary(a) for a in articles]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@news_nlp_router.get("/meta/stats", response_model=NLPStatsResponse)
async def get_nlp_stats(
    engine: Annotated[NewsNLPEngine, Depends(get_news_nlp_engine)],
) -> NLPStatsResponse:
    stats = await engine.get_nlp_stats()
    return NLPStatsResponse(**stats)


def _analysis_response(analysis: Any, entities: list[Any]) -> NLPAnalysisResponse:
    import json
    events = json.loads(analysis.detected_events) if analysis.detected_events else None
    return NLPAnalysisResponse(
        id=analysis.id, article_id=analysis.article_id,
        is_processed=analysis.is_processed,
        processed_at=analysis.processed_at.isoformat() if analysis.processed_at else None,
        sentiment=SentimentResponse(
            label=analysis.sentiment_label or "neutral",
            positive=analysis.sentiment_positive or 0.0,
            negative=analysis.sentiment_negative or 0.0,
            neutral=analysis.sentiment_neutral or 0.0,
            confidence=analysis.sentiment_confidence or 0.0,
        ),
        detected_events=events,
        event_confidence=analysis.event_confidence,
        mapped_sector=analysis.mapped_sector,
        sector_confidence=analysis.sector_confidence,
        mapped_company_symbol=analysis.mapped_company_symbol,
        company_confidence=analysis.company_confidence,
        overall_confidence=analysis.overall_confidence,
        entities=[EntityResponse(id=e.id, entity_text=e.entity_text, entity_type=e.entity_type, confidence=e.confidence, metadata_json=e.metadata_json) for e in entities],
    )


def _article_summary(article: Any) -> dict[str, Any]:
    return {"id": article.id, "title": article.title, "symbol": article.symbol, "source": article.source, "published_at": article.published_at.isoformat() if article.published_at else None}
