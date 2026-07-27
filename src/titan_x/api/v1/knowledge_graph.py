from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from titan_x.api.dependencies import (
    get_current_active_user,
    get_knowledge_graph_service,
    require_api_key,
)
from titan_x.api.schemas import MessageResponse, PaginatedResponse
from titan_x.models.user import User
from titan_x.services.knowledge_graph_service import KnowledgeGraphService

kg_router = APIRouter(
    prefix="/knowledge-graph",
    tags=["knowledge-graph"],
    dependencies=[Depends(require_api_key)],
)


# ============================================================
# SECTORS
# ============================================================

@kg_router.post("/sectors", status_code=status.HTTP_201_CREATED)
async def create_sector(
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    name: str = Query(..., min_length=1, max_length=128),
    sector_code: str | None = Query(None, max_length=16),
    description: str | None = Query(None, max_length=2000),
) -> dict:
    return await svc.create_sector(name=name, sector_code=sector_code, description=description)


@kg_router.get("/sectors")
async def list_sectors(
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[dict]:
    rows, total = await svc.list_sectors(skip=skip, limit=limit)
    items = [{"id": r.id, "name": r.name, "sector_code": r.sector_code, "description": r.description} for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@kg_router.get("/sectors/{sector_id}")
async def get_sector(
    sector_id: int,
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict:
    result = await svc.get_sector(sector_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sector not found")
    return result


@kg_router.put("/sectors/{sector_id}")
async def update_sector(
    sector_id: int,
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    name: str | None = Query(None, min_length=1, max_length=128),
    sector_code: str | None = Query(None, max_length=16),
    description: str | None = Query(None, max_length=2000),
) -> dict:
    result = await svc.update_sector(sector_id, name=name, sector_code=sector_code, description=description)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sector not found")
    return result


@kg_router.delete("/sectors/{sector_id}", response_model=MessageResponse)
async def delete_sector(
    sector_id: int,
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> MessageResponse:
    deleted = await svc.delete_sector(sector_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sector not found")
    return MessageResponse(message="Sector deleted")


# ============================================================
# INDUSTRIES
# ============================================================

@kg_router.post("/industries", status_code=status.HTTP_201_CREATED)
async def create_industry(
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    name: str = Query(..., min_length=1, max_length=128),
    sector_id: int | None = Query(None),
    industry_code: str | None = Query(None, max_length=16),
    description: str | None = Query(None, max_length=2000),
) -> dict:
    return await svc.create_industry(name=name, sector_id=sector_id, industry_code=industry_code, description=description)


@kg_router.get("/industries")
async def list_industries(
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    sector_id: int | None = Query(None),
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[dict]:
    rows, total = await svc.list_industries(sector_id=sector_id, skip=skip, limit=limit)
    items = [{"id": r.id, "name": r.name, "industry_code": r.industry_code, "sector_id": r.sector_id} for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@kg_router.get("/industries/{industry_id}")
async def get_industry(
    industry_id: int,
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict:
    result = await svc.get_industry(industry_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Industry not found")
    return result


@kg_router.put("/industries/{industry_id}")
async def update_industry(
    industry_id: int,
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    name: str | None = Query(None, min_length=1, max_length=128),
    sector_id: int | None = Query(None),
    industry_code: str | None = Query(None, max_length=16),
    description: str | None = Query(None, max_length=2000),
) -> dict:
    result = await svc.update_industry(industry_id, name=name, sector_id=sector_id, industry_code=industry_code, description=description)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Industry not found")
    return result


@kg_router.delete("/industries/{industry_id}", response_model=MessageResponse)
async def delete_industry(
    industry_id: int,
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> MessageResponse:
    deleted = await svc.delete_industry(industry_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Industry not found")
    return MessageResponse(message="Industry deleted")


# ============================================================
# PROMOTERS
# ============================================================

@kg_router.post("/promoters", status_code=status.HTTP_201_CREATED)
async def create_promoter(
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    name: str = Query(..., min_length=1, max_length=256),
    promoter_type: str = Query("individual", pattern="^(individual|institutional|government)$"),
    pan: str | None = Query(None, max_length=16),
    cin: str | None = Query(None, max_length=32),
    address: str | None = Query(None, max_length=2000),
    email: str | None = Query(None, max_length=256),
    phone: str | None = Query(None, max_length=32),
) -> dict:
    return await svc.create_promoter(
        name=name, promoter_type=promoter_type, pan=pan, cin=cin,
        address=address, email=email, phone=phone,
    )


@kg_router.get("/promoters")
async def list_promoters(
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[dict]:
    rows, total = await svc.list_promoters(skip=skip, limit=limit)
    items = [{"id": r.id, "name": r.name, "promoter_type": r.promoter_type, "pan": r.pan} for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@kg_router.get("/promoters/{promoter_id}")
async def get_promoter(
    promoter_id: int,
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict:
    result = await svc.get_promoter(promoter_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Promoter not found")
    return result


@kg_router.put("/promoters/{promoter_id}")
async def update_promoter(
    promoter_id: int,
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    name: str | None = Query(None, min_length=1, max_length=256),
    promoter_type: str | None = Query(None, pattern="^(individual|institutional|government)$"),
    pan: str | None = Query(None, max_length=16),
    address: str | None = Query(None, max_length=2000),
) -> dict:
    result = await svc.update_promoter(promoter_id, name=name, promoter_type=promoter_type, pan=pan, address=address)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Promoter not found")
    return result


@kg_router.delete("/promoters/{promoter_id}", response_model=MessageResponse)
async def delete_promoter(
    promoter_id: int,
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> MessageResponse:
    deleted = await svc.delete_promoter(promoter_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Promoter not found")
    return MessageResponse(message="Promoter deleted")


# ============================================================
# COMPANY-PROMOTER LINKS
# ============================================================

@kg_router.post("/company-promoters", status_code=status.HTTP_201_CREATED)
async def link_company_promoter(
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    company_id: int = Query(...),
    promoter_id: int = Query(...),
    ownership_pct: float | None = Query(None, ge=0, le=100),
    role: str | None = Query(None, max_length=64),
) -> dict:
    return await svc.link_company_promoter(company_id=company_id, promoter_id=promoter_id, ownership_pct=ownership_pct, role=role)


@kg_router.get("/companies/{company_id}/promoters")
async def get_company_promoters(
    company_id: int,
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> list[dict]:
    return await svc.get_company_promoters(company_id)


@kg_router.get("/promoters/{promoter_id}/companies")
async def get_promoter_companies(
    promoter_id: int,
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> list[dict]:
    return await svc.get_promoter_companies(promoter_id)


@kg_router.delete("/company-promoters/{link_id}", response_model=MessageResponse)
async def unlink_company_promoter(
    link_id: int,
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> MessageResponse:
    deleted = await svc.unlink_company_promoter(link_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
    return MessageResponse(message="Link deleted")


# ============================================================
# SUBSIDIARIES
# ============================================================

@kg_router.post("/subsidiaries", status_code=status.HTTP_201_CREATED)
async def create_subsidiary(
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    parent_company_id: int = Query(...),
    subsidiary_company_id: int = Query(...),
    ownership_pct: float | None = Query(None, ge=0, le=100),
    relationship_type: str = Query("subsidiary"),
) -> dict:
    return await svc.create_subsidiary(
        parent_company_id=parent_company_id, subsidiary_company_id=subsidiary_company_id,
        ownership_pct=ownership_pct, relationship_type=relationship_type,
    )


@kg_router.get("/companies/{company_id}/subsidiaries")
async def get_subsidiaries(
    company_id: int,
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> list[dict]:
    return await svc.get_subsidiaries(company_id)


@kg_router.get("/companies/{company_id}/parents")
async def get_parent_companies(
    company_id: int,
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> list[dict]:
    return await svc.get_parent_companies(company_id)


@kg_router.delete("/subsidiaries/{sub_id}", response_model=MessageResponse)
async def delete_subsidiary(
    sub_id: int,
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> MessageResponse:
    deleted = await svc.delete_subsidiary(sub_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subsidiary not found")
    return MessageResponse(message="Subsidiary deleted")


# ============================================================
# EVENTS
# ============================================================

@kg_router.post("/events", status_code=status.HTTP_201_CREATED)
async def create_event(
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    event_type: str = Query(..., max_length=32),
    event_date: date = Query(...),
    title: str = Query(..., min_length=1, max_length=256),
    description: str | None = Query(None, max_length=5000),
    impact_score: float | None = Query(None, ge=-10, le=10),
    source: str | None = Query(None, max_length=64),
    company_id: int | None = Query(None),
    sector_id: int | None = Query(None),
    industry_id: int | None = Query(None),
    promoter_id: int | None = Query(None),
) -> dict:
    return await svc.create_event(
        event_type=event_type, event_date=event_date, title=title,
        description=description, impact_score=impact_score, source=source,
        company_id=company_id, sector_id=sector_id,
        industry_id=industry_id, promoter_id=promoter_id,
    )


@kg_router.get("/events")
async def list_events(
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    event_type: str | None = Query(None, max_length=32),
    company_id: int | None = Query(None),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[dict]:
    rows, total = await svc.list_events(event_type=event_type, company_id=company_id, from_date=from_date, to_date=to_date, skip=skip, limit=limit)
    items = [{"id": r.id, "event_type": r.event_type, "event_date": r.event_date.isoformat() if r.event_date else None, "title": r.title, "impact_score": r.impact_score, "company_id": r.company_id} for r in rows]
    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@kg_router.get("/events/{event_id}")
async def get_event(
    event_id: int,
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict:
    result = await svc.get_event(event_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return result


@kg_router.put("/events/{event_id}")
async def update_event(
    event_id: int,
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    title: str | None = Query(None, min_length=1, max_length=256),
    description: str | None = Query(None, max_length=5000),
    impact_score: float | None = Query(None, ge=-10, le=10),
) -> dict:
    result = await svc.update_event(event_id, title=title, description=description, impact_score=impact_score)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return result


@kg_router.delete("/events/{event_id}", response_model=MessageResponse)
async def delete_event(
    event_id: int,
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> MessageResponse:
    deleted = await svc.delete_event(event_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return MessageResponse(message="Event deleted")


# ============================================================
# BUSINESS RELATIONSHIPS
# ============================================================

@kg_router.post("/relationships", status_code=status.HTTP_201_CREATED)
async def create_relationship(
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    source_entity_type: str = Query(..., max_length=32),
    source_entity_id: int = Query(...),
    target_entity_type: str = Query(..., max_length=32),
    target_entity_id: int = Query(...),
    relationship_type: str = Query(..., max_length=32),
    weight: float | None = Query(None, ge=0, le=1),
) -> dict:
    return await svc.create_relationship(
        source_entity_type=source_entity_type, source_entity_id=source_entity_id,
        target_entity_type=target_entity_type, target_entity_id=target_entity_id,
        relationship_type=relationship_type, weight=weight,
    )


@kg_router.get("/entities/{entity_type}/{entity_id}/relationships")
async def get_entity_relationships(
    entity_type: str,
    entity_id: int,
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> list[dict]:
    return await svc.get_entity_relationships(entity_type, entity_id)


@kg_router.delete("/relationships/{rel_id}", response_model=MessageResponse)
async def delete_relationship(
    rel_id: int,
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> MessageResponse:
    deleted = await svc.delete_relationship(rel_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relationship not found")
    return MessageResponse(message="Relationship deleted")


# ============================================================
# SEARCH
# ============================================================

@kg_router.get("/search")
async def search(
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    q: str = Query(..., min_length=1, max_length=128),
    limit: int = Query(20, ge=1, le=100),
) -> list[dict]:
    return await svc.search(query=q, limit=limit)


# ============================================================
# GRAPH TRAVERSAL
# ============================================================

@kg_router.get("/companies/{company_id}/graph")
async def get_company_graph(
    company_id: int,
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    max_depth: int = Query(1, ge=1, le=3),
) -> dict:
    return await svc.get_company_graph(company_id, max_depth=max_depth)


@kg_router.get("/entities/{entity_type}/{entity_id}/graph")
async def get_entity_connections(
    entity_type: str,
    entity_id: int,
    svc: Annotated[KnowledgeGraphService, Depends(get_knowledge_graph_service)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict:
    return await svc.get_entity_connections(entity_type, entity_id)
