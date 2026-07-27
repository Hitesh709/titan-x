import json
from collections.abc import Sequence
from datetime import date
from typing import Any

import structlog
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from titan_x.db.repository import BaseRepository
from titan_x.models.company import Company
from titan_x.models.knowledge_graph import (
    BusinessRelationship,
    CompanyPromoter,
    EntityEvent,
    Industry,
    Promoter,
    Sector,
    Subsidiary,
)

logger = structlog.get_logger(__name__)

EVENT_ENTITY_TYPES = {"company", "sector", "industry", "promoter"}
SEARCH_LIMIT = 50


class KnowledgeGraphService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._sector_repo = BaseRepository(session, Sector)
        self._industry_repo = BaseRepository(session, Industry)
        self._promoter_repo = BaseRepository(session, Promoter)
        self._cp_repo = BaseRepository(session, CompanyPromoter)
        self._sub_repo = BaseRepository(session, Subsidiary)
        self._event_repo = BaseRepository(session, EntityEvent)
        self._br_repo = BaseRepository(session, BusinessRelationship)

    # ============================================================
    # SECTOR CRUD
    # ============================================================

    async def create_sector(self, name: str, sector_code: str | None = None, description: str | None = None) -> dict[str, Any]:
        sector = await self._sector_repo.create(name=name, sector_code=sector_code, description=description)
        return self._sector_to_dict(sector)

    async def get_sector(self, sector_id: int) -> dict[str, Any] | None:
        sector = await self._session.get(Sector, sector_id)
        if sector is None:
            return None
        return self._sector_to_dict(sector)

    async def list_sectors(self, skip: int = 0, limit: int = 100) -> tuple[Sequence[Sector], int]:
        total = (await self._session.execute(select(func.count()).select_from(Sector))).scalar() or 0
        rows = (await self._session.execute(select(Sector).order_by(Sector.name).offset(skip).limit(limit))).scalars().all()
        return rows, total

    async def update_sector(self, sector_id: int, **kwargs: Any) -> dict[str, Any] | None:
        sector = await self._session.get(Sector, sector_id)
        if sector is None:
            return None
        for k, v in kwargs.items():
            if v is not None and hasattr(sector, k):
                setattr(sector, k, v)
        await self._session.flush()
        await self._session.refresh(sector)
        return self._sector_to_dict(sector)

    async def delete_sector(self, sector_id: int) -> bool:
        return await self._sector_repo.delete(sector_id)

    # ============================================================
    # INDUSTRY CRUD
    # ============================================================

    async def create_industry(self, name: str, sector_id: int | None = None, industry_code: str | None = None, description: str | None = None) -> dict[str, Any]:
        industry = await self._industry_repo.create(name=name, sector_id=sector_id, industry_code=industry_code, description=description)
        return self._industry_to_dict(industry)

    async def get_industry(self, industry_id: int) -> dict[str, Any] | None:
        industry = await self._session.get(Industry, industry_id)
        if industry is None:
            return None
        return self._industry_to_dict(industry)

    async def list_industries(self, sector_id: int | None = None, skip: int = 0, limit: int = 100) -> tuple[Sequence[Industry], int]:
        query = select(Industry)
        count_query = select(func.count()).select_from(Industry)
        if sector_id is not None:
            query = query.where(Industry.sector_id == sector_id)
            count_query = count_query.where(Industry.sector_id == sector_id)
        total = (await self._session.execute(count_query)).scalar() or 0
        rows = (await self._session.execute(query.order_by(Industry.name).offset(skip).limit(limit))).scalars().all()
        return rows, total

    async def update_industry(self, industry_id: int, **kwargs: Any) -> dict[str, Any] | None:
        industry = await self._session.get(Industry, industry_id)
        if industry is None:
            return None
        for k, v in kwargs.items():
            if v is not None and hasattr(industry, k):
                setattr(industry, k, v)
        await self._session.flush()
        await self._session.refresh(industry)
        return self._industry_to_dict(industry)

    async def delete_industry(self, industry_id: int) -> bool:
        return await self._industry_repo.delete(industry_id)

    # ============================================================
    # PROMOTER CRUD
    # ============================================================

    async def create_promoter(self, name: str, promoter_type: str = "individual", pan: str | None = None, cin: str | None = None, address: str | None = None, email: str | None = None, phone: str | None = None, metadata_json: str | None = None) -> dict[str, Any]:
        promoter = await self._promoter_repo.create(
            name=name, promoter_type=promoter_type, pan=pan, cin=cin,
            address=address, email=email, phone=phone, metadata_json=metadata_json,
        )
        return self._promoter_to_dict(promoter)

    async def get_promoter(self, promoter_id: int) -> dict[str, Any] | None:
        promoter = await self._session.get(Promoter, promoter_id)
        if promoter is None:
            return None
        return self._promoter_to_dict(promoter)

    async def list_promoters(self, skip: int = 0, limit: int = 100) -> tuple[Sequence[Promoter], int]:
        total = (await self._session.execute(select(func.count()).select_from(Promoter))).scalar() or 0
        rows = (await self._session.execute(select(Promoter).order_by(Promoter.name).offset(skip).limit(limit))).scalars().all()
        return rows, total

    async def update_promoter(self, promoter_id: int, **kwargs: Any) -> dict[str, Any] | None:
        promoter = await self._session.get(Promoter, promoter_id)
        if promoter is None:
            return None
        for k, v in kwargs.items():
            if v is not None and hasattr(promoter, k):
                setattr(promoter, k, v)
        await self._session.flush()
        await self._session.refresh(promoter)
        return self._promoter_to_dict(promoter)

    async def delete_promoter(self, promoter_id: int) -> bool:
        return await self._promoter_repo.delete(promoter_id)

    # ============================================================
    # COMPANY-PROMOTER LINKS
    # ============================================================

    async def link_company_promoter(self, company_id: int, promoter_id: int, ownership_pct: float | None = None, role: str | None = None) -> dict[str, Any]:
        link = await self._cp_repo.create(company_id=company_id, promoter_id=promoter_id, ownership_pct=ownership_pct, role=role)
        return self._cp_to_dict(link)

    async def unlink_company_promoter(self, link_id: int) -> bool:
        return await self._cp_repo.delete(link_id)

    async def get_company_promoters(self, company_id: int) -> list[dict[str, Any]]:
        rows = (await self._session.execute(
            select(CompanyPromoter).where(CompanyPromoter.company_id == company_id)
        )).scalars().all()
        return [self._cp_to_dict(r) for r in rows]

    async def get_promoter_companies(self, promoter_id: int) -> list[dict[str, Any]]:
        rows = (await self._session.execute(
            select(CompanyPromoter).where(CompanyPromoter.promoter_id == promoter_id)
        )).scalars().all()
        return [self._cp_to_dict(r) for r in rows]

    # ============================================================
    # SUBSIDIARY CRUD
    # ============================================================

    async def create_subsidiary(self, parent_company_id: int, subsidiary_company_id: int, ownership_pct: float | None = None, relationship_type: str = "subsidiary") -> dict[str, Any]:
        sub = await self._sub_repo.create(
            parent_company_id=parent_company_id, subsidiary_company_id=subsidiary_company_id,
            ownership_pct=ownership_pct, relationship_type=relationship_type,
        )
        return self._sub_to_dict(sub)

    async def get_subsidiaries(self, company_id: int) -> list[dict[str, Any]]:
        rows = (await self._session.execute(
            select(Subsidiary).where(Subsidiary.parent_company_id == company_id)
        )).scalars().all()
        return [self._sub_to_dict(r) for r in rows]

    async def get_parent_companies(self, company_id: int) -> list[dict[str, Any]]:
        rows = (await self._session.execute(
            select(Subsidiary).where(Subsidiary.subsidiary_company_id == company_id)
        )).scalars().all()
        return [self._sub_to_dict(r) for r in rows]

    async def delete_subsidiary(self, sub_id: int) -> bool:
        return await self._sub_repo.delete(sub_id)

    # ============================================================
    # ENTITY EVENT CRUD
    # ============================================================

    async def create_event(
        self, event_type: str, event_date: date, title: str,
        description: str | None = None, impact_score: float | None = None,
        source: str | None = None, company_id: int | None = None,
        sector_id: int | None = None, industry_id: int | None = None,
        promoter_id: int | None = None, metadata_json: str | None = None,
    ) -> dict[str, Any]:
        event = await self._event_repo.create(
            event_type=event_type, event_date=event_date, title=title,
            description=description, impact_score=impact_score, source=source,
            company_id=company_id, sector_id=sector_id, industry_id=industry_id,
            promoter_id=promoter_id, metadata_json=metadata_json,
        )
        return self._event_to_dict(event)

    async def get_event(self, event_id: int) -> dict[str, Any] | None:
        event = await self._session.get(EntityEvent, event_id)
        if event is None:
            return None
        return self._event_to_dict(event)

    async def list_events(
        self, event_type: str | None = None, company_id: int | None = None,
        from_date: date | None = None, to_date: date | None = None,
        skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[EntityEvent], int]:
        query = select(EntityEvent)
        count_query = select(func.count()).select_from(EntityEvent)
        if event_type:
            query = query.where(EntityEvent.event_type == event_type)
            count_query = count_query.where(EntityEvent.event_type == event_type)
        if company_id:
            query = query.where(EntityEvent.company_id == company_id)
            count_query = count_query.where(EntityEvent.company_id == company_id)
        if from_date:
            query = query.where(EntityEvent.event_date >= from_date)
            count_query = count_query.where(EntityEvent.event_date >= from_date)
        if to_date:
            query = query.where(EntityEvent.event_date <= to_date)
            count_query = count_query.where(EntityEvent.event_date <= to_date)
        total = (await self._session.execute(count_query)).scalar() or 0
        rows = (await self._session.execute(query.order_by(desc(EntityEvent.event_date)).offset(skip).limit(limit))).scalars().all()
        return rows, total

    async def update_event(self, event_id: int, **kwargs: Any) -> dict[str, Any] | None:
        event = await self._session.get(EntityEvent, event_id)
        if event is None:
            return None
        for k, v in kwargs.items():
            if v is not None and hasattr(event, k):
                setattr(event, k, v)
        await self._session.flush()
        await self._session.refresh(event)
        return self._event_to_dict(event)

    async def delete_event(self, event_id: int) -> bool:
        return await self._event_repo.delete(event_id)

    # ============================================================
    # BUSINESS RELATIONSHIP CRUD
    # ============================================================

    async def create_relationship(
        self, source_entity_type: str, source_entity_id: int,
        target_entity_type: str, target_entity_id: int,
        relationship_type: str, weight: float | None = None,
        metadata_json: str | None = None,
    ) -> dict[str, Any]:
        br = await self._br_repo.create(
            source_entity_type=source_entity_type, source_entity_id=source_entity_id,
            target_entity_type=target_entity_type, target_entity_id=target_entity_id,
            relationship_type=relationship_type, weight=weight, metadata_json=metadata_json,
        )
        return self._br_to_dict(br)

    async def get_entity_relationships(self, entity_type: str, entity_id: int) -> list[dict[str, Any]]:
        rows = (await self._session.execute(
            select(BusinessRelationship).where(
                or_(
                    select(BusinessRelationship).where(
                        BusinessRelationship.source_entity_type == entity_type,
                        BusinessRelationship.source_entity_id == entity_id,
                    ).exists(),
                    select(BusinessRelationship).where(
                        BusinessRelationship.target_entity_type == entity_type,
                        BusinessRelationship.target_entity_id == entity_id,
                    ).exists(),
                )
            )
        )).scalars().all()

        result: list[dict[str, Any]] = []
        seen: set[int] = set()
        for r in rows:
            if r.id not in seen:
                seen.add(r.id)
                result.append(self._br_to_dict(r))
        return result

    async def delete_relationship(self, rel_id: int) -> bool:
        return await self._br_repo.delete(rel_id)

    # ============================================================
    # SEARCH
    # ============================================================

    async def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        pattern = f"%{query}%"
        results: list[dict[str, Any]] = []

        companies = (await self._session.execute(
            select(Company).where(
                or_(Company.company_name.ilike(pattern), Company.symbol.ilike(pattern))
            ).limit(limit)
        )).scalars().all()
        for c in companies:
            results.append({
                "entity_type": "company", "id": c.id,
                "name": c.company_name, "symbol": c.symbol,
                "sector": c.sector, "exchange": c.exchange,
            })

        sectors = (await self._session.execute(
            select(Sector).where(Sector.name.ilike(pattern)).limit(limit)
        )).scalars().all()
        for s in sectors:
            results.append({
                "entity_type": "sector", "id": s.id,
                "name": s.name, "code": s.sector_code,
            })

        industries = (await self._session.execute(
            select(Industry).where(Industry.name.ilike(pattern)).limit(limit)
        )).scalars().all()
        for ind in industries:
            results.append({
                "entity_type": "industry", "id": ind.id,
                "name": ind.name, "code": ind.industry_code,
            })

        promoters = (await self._session.execute(
            select(Promoter).where(Promoter.name.ilike(pattern)).limit(limit)
        )).scalars().all()
        for p in promoters:
            results.append({
                "entity_type": "promoter", "id": p.id,
                "name": p.name, "type": p.promoter_type,
            })

        events = (await self._session.execute(
            select(EntityEvent).where(
                or_(EntityEvent.title.ilike(pattern), EntityEvent.description.ilike(pattern))
            ).limit(limit)
        )).scalars().all()
        for e in events:
            results.append({
                "entity_type": "event", "id": e.id,
                "title": e.title, "event_type": e.event_type,
                "event_date": e.event_date.isoformat() if e.event_date else None,
                "impact_score": e.impact_score,
            })

        return results[:limit]

    # ============================================================
    # GRAPH TRAVERSAL
    # ============================================================

    async def get_company_graph(self, company_id: int, max_depth: int = 2) -> dict[str, Any]:
        company = await self._session.get(Company, company_id)
        if company is None:
            return {"company": None, "error": "Company not found"}

        nodes: list[dict[str, Any]] = [{
            "entity_type": "company", "id": company.id,
            "name": company.company_name, "symbol": company.symbol,
        }]
        edges: list[dict[str, Any]] = []
        visited_company_ids: set[int] = {company_id}

        promoters = await self.get_company_promoters(company_id)
        for cp in promoters:
            promoter = await self._session.get(Promoter, cp["promoter_id"])
            if promoter:
                nodes.append({"entity_type": "promoter", "id": promoter.id, "name": promoter.name})
                edges.append({
                    "source_type": "company", "source_id": company_id,
                    "target_type": "promoter", "target_id": promoter.id,
                    "relationship": "promoted_by", "ownership_pct": cp.get("ownership_pct"),
                })

        subsidiaries = await self.get_subsidiaries(company_id)
        for sub in subsidiaries:
            sub_id = sub["subsidiary_company_id"]
            if sub_id not in visited_company_ids:
                visited_company_ids.add(sub_id)
                sub_company = await self._session.get(Company, sub_id)
                if sub_company:
                    nodes.append({"entity_type": "company", "id": sub_company.id, "name": sub_company.company_name, "symbol": sub_company.symbol})
                    edges.append({
                        "source_type": "company", "source_id": company_id,
                        "target_type": "company", "target_id": sub_id,
                        "relationship": "owns", "ownership_pct": sub.get("ownership_pct"),
                    })

        parents = await self.get_parent_companies(company_id)
        for p in parents:
            parent_id = p["parent_company_id"]
            if parent_id not in visited_company_ids:
                visited_company_ids.add(parent_id)
                parent_company = await self._session.get(Company, parent_id)
                if parent_company:
                    nodes.append({"entity_type": "company", "id": parent_company.id, "name": parent_company.company_name, "symbol": parent_company.symbol})
                    edges.append({
                        "source_type": "company", "source_id": parent_id,
                        "target_type": "company", "target_id": company_id,
                        "relationship": "owns", "ownership_pct": p.get("ownership_pct"),
                    })

        events = (await self._session.execute(
            select(EntityEvent).where(EntityEvent.company_id == company_id).limit(20)
        )).scalars().all()
        for ev in events:
            nodes.append({"entity_type": "event", "id": ev.id, "title": ev.title, "event_type": ev.event_type, "event_date": ev.event_date.isoformat() if ev.event_date else None})
            edges.append({
                "source_type": "company", "source_id": company_id,
                "target_type": "event", "target_id": ev.id,
                "relationship": "has_event",
            })

        relationships = await self.get_entity_relationships("company", company_id)
        for br in relationships:
            other_type = br["target_entity_type"] if br["source_entity_type"] == "company" and br["source_entity_id"] == company_id else br["source_entity_type"]
            other_id = br["target_entity_id"] if br["source_entity_type"] == "company" and br["source_entity_id"] == company_id else br["source_entity_id"]
            rel_type = br["relationship_type"]
            if other_type == "company" and other_id not in visited_company_ids and max_depth > 1:
                visited_company_ids.add(other_id)
                other_company = await self._session.get(Company, other_id)
                if other_company:
                    nodes.append({"entity_type": "company", "id": other_company.id, "name": other_company.company_name, "symbol": other_company.symbol})
                    edges.append({
                        "source_type": "company", "source_id": company_id,
                        "target_type": "company", "target_id": other_id,
                        "relationship": rel_type,
                    })

        if company.sector:
            nodes.append({"entity_type": "sector", "id": 0, "name": company.sector})
            edges.append({
                "source_type": "company", "source_id": company_id,
                "target_type": "sector", "target_id": 0,
                "relationship": "belongs_to",
            })

        return {"company": {"id": company.id, "symbol": company.symbol, "name": company.company_name}, "nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}

    async def get_entity_connections(self, entity_type: str, entity_id: int) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = [{"entity_type": entity_type, "id": entity_id}]
        edges: list[dict[str, Any]] = []

        if entity_type == "sector":
            sector = await self._session.get(Sector, entity_id)
            if sector:
                nodes[0]["name"] = sector.name
                inds = (await self._session.execute(select(Industry).where(Industry.sector_id == entity_id))).scalars().all()
                for ind in inds:
                    nodes.append({"entity_type": "industry", "id": ind.id, "name": ind.name})
                    edges.append({"source_type": "sector", "source_id": entity_id, "target_type": "industry", "target_id": ind.id, "relationship": "contains"})
                events = (await self._session.execute(select(EntityEvent).where(EntityEvent.sector_id == entity_id))).scalars().all()
                for ev in events:
                    nodes.append({"entity_type": "event", "id": ev.id, "title": ev.title})
                    edges.append({"source_type": "sector", "source_id": entity_id, "target_type": "event", "target_id": ev.id, "relationship": "has_event"})

        elif entity_type == "promoter":
            promoter = await self._session.get(Promoter, entity_id)
            if promoter:
                nodes[0]["name"] = promoter.name
                links = await self.get_promoter_companies(entity_id)
                for cp in links:
                    company = await self._session.get(Company, cp["company_id"])
                    if company:
                        nodes.append({"entity_type": "company", "id": company.id, "name": company.company_name, "symbol": company.symbol})
                        edges.append({"source_type": "promoter", "source_id": entity_id, "target_type": "company", "target_id": company.id, "relationship": "promotes", "ownership_pct": cp.get("ownership_pct")})
                events = (await self._session.execute(select(EntityEvent).where(EntityEvent.promoter_id == entity_id))).scalars().all()
                for ev in events:
                    nodes.append({"entity_type": "event", "id": ev.id, "title": ev.title})
                    edges.append({"source_type": "promoter", "source_id": entity_id, "target_type": "event", "target_id": ev.id, "relationship": "has_event"})

        return {"entity": nodes[0], "nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}

    # ============================================================
    # DICT HELPERS
    # ============================================================

    def _sector_to_dict(self, sector: Sector) -> dict[str, Any]:
        return {
            "id": sector.id, "name": sector.name,
            "sector_code": sector.sector_code, "description": sector.description,
            "created_at": sector.created_at.isoformat() if sector.created_at else None,
            "updated_at": sector.updated_at.isoformat() if sector.updated_at else None,
        }

    def _industry_to_dict(self, industry: Industry) -> dict[str, Any]:
        return {
            "id": industry.id, "name": industry.name,
            "industry_code": industry.industry_code, "description": industry.description,
            "sector_id": industry.sector_id,
            "created_at": industry.created_at.isoformat() if industry.created_at else None,
            "updated_at": industry.updated_at.isoformat() if industry.updated_at else None,
        }

    def _promoter_to_dict(self, promoter: Promoter) -> dict[str, Any]:
        return {
            "id": promoter.id, "name": promoter.name,
            "promoter_type": promoter.promoter_type, "pan": promoter.pan,
            "cin": promoter.cin, "address": promoter.address,
            "email": promoter.email, "phone": promoter.phone,
            "metadata_json": promoter.metadata_json,
            "created_at": promoter.created_at.isoformat() if promoter.created_at else None,
        }

    def _cp_to_dict(self, cp: CompanyPromoter) -> dict[str, Any]:
        return {
            "id": cp.id, "company_id": cp.company_id,
            "promoter_id": cp.promoter_id, "ownership_pct": cp.ownership_pct,
            "role": cp.role, "is_active": cp.is_active,
        }

    def _sub_to_dict(self, sub: Subsidiary) -> dict[str, Any]:
        return {
            "id": sub.id, "parent_company_id": sub.parent_company_id,
            "subsidiary_company_id": sub.subsidiary_company_id,
            "ownership_pct": sub.ownership_pct, "relationship_type": sub.relationship_type,
            "is_active": sub.is_active, "metadata_json": sub.metadata_json,
        }

    def _event_to_dict(self, event: EntityEvent) -> dict[str, Any]:
        return {
            "id": event.id, "event_type": event.event_type,
            "event_date": event.event_date.isoformat() if event.event_date else None,
            "title": event.title, "description": event.description,
            "impact_score": event.impact_score, "source": event.source,
            "company_id": event.company_id, "sector_id": event.sector_id,
            "industry_id": event.industry_id, "promoter_id": event.promoter_id,
            "metadata_json": event.metadata_json,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }

    def _br_to_dict(self, br: BusinessRelationship) -> dict[str, Any]:
        return {
            "id": br.id,
            "source_entity_type": br.source_entity_type, "source_entity_id": br.source_entity_id,
            "target_entity_type": br.target_entity_type, "target_entity_id": br.target_entity_id,
            "relationship_type": br.relationship_type, "weight": br.weight,
            "is_active": br.is_active, "metadata_json": br.metadata_json,
            "created_at": br.created_at.isoformat() if br.created_at else None,
        }
