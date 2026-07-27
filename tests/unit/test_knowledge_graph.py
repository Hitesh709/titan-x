from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.models.company import Company
from titan_x.models.knowledge_graph import (
    BusinessRelationship,
    EntityEvent,
    Industry,
    Promoter,
    Sector,
    Subsidiary,
)
from titan_x.models.user import User
from titan_x.services.knowledge_graph_service import KnowledgeGraphService


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fks(dbapi_con, _rec):
        cursor = dbapi_con.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()


@pytest_asyncio.fixture
async def user(session: AsyncSession) -> User:
    u = User(email="kg@test.com", hashed_password="h")
    session.add(u)
    await session.flush()
    return u


@pytest_asyncio.fixture
async def company(session: AsyncSession) -> Company:
    c = Company(symbol="PARENT", company_name="Parent Corp", isin="IN00001", exchange="NSE", sector="Technology", industry="Software")
    session.add(c)
    await session.flush()
    return c


@pytest_asyncio.fixture
async def subsidiary_company(session: AsyncSession) -> Company:
    c = Company(symbol="SUB", company_name="Subsidiary Inc", isin="IN00002", exchange="NSE", sector="Technology")
    session.add(c)
    await session.flush()
    return c


@pytest_asyncio.fixture
def svc(session: AsyncSession) -> KnowledgeGraphService:
    return KnowledgeGraphService(session)


# ============================================================
# SECTOR CRUD
# ============================================================

class TestSectorCRUD:
    @pytest.mark.asyncio
    async def test_create(self, svc: KnowledgeGraphService):
        result = await svc.create_sector(name="Technology", sector_code="TECH", description="Tech sector")
        assert result["name"] == "Technology"
        assert result["sector_code"] == "TECH"
        assert result["id"] is not None

    @pytest.mark.asyncio
    async def test_get(self, svc: KnowledgeGraphService):
        created = await svc.create_sector(name="Healthcare")
        result = await svc.get_sector(created["id"])
        assert result is not None
        assert result["name"] == "Healthcare"

    @pytest.mark.asyncio
    async def test_get_not_found(self, svc: KnowledgeGraphService):
        assert await svc.get_sector(9999) is None

    @pytest.mark.asyncio
    async def test_list(self, svc: KnowledgeGraphService):
        await svc.create_sector(name="A")
        await svc.create_sector(name="B")
        rows, total = await svc.list_sectors()
        assert total == 2

    @pytest.mark.asyncio
    async def test_update(self, svc: KnowledgeGraphService):
        created = await svc.create_sector(name="Old")
        result = await svc.update_sector(created["id"], name="New", description="Updated")
        assert result["name"] == "New"
        assert result["description"] == "Updated"

    @pytest.mark.asyncio
    async def test_update_not_found(self, svc: KnowledgeGraphService):
        assert await svc.update_sector(9999, name="X") is None

    @pytest.mark.asyncio
    async def test_delete(self, svc: KnowledgeGraphService):
        created = await svc.create_sector(name="Del")
        assert await svc.delete_sector(created["id"]) is True
        assert await svc.get_sector(created["id"]) is None

    @pytest.mark.asyncio
    async def test_delete_not_found(self, svc: KnowledgeGraphService):
        assert await svc.delete_sector(9999) is False


# ============================================================
# INDUSTRY CRUD
# ============================================================

class TestIndustryCRUD:
    @pytest.mark.asyncio
    async def test_create(self, svc: KnowledgeGraphService):
        result = await svc.create_industry(name="Software", industry_code="SW")
        assert result["name"] == "Software"
        assert result["id"] is not None

    @pytest.mark.asyncio
    async def test_create_with_sector(self, svc: KnowledgeGraphService):
        sec = await svc.create_sector(name="Tech")
        ind = await svc.create_industry(name="AI", sector_id=sec["id"])
        assert ind["sector_id"] == sec["id"]

    @pytest.mark.asyncio
    async def test_list_by_sector(self, svc: KnowledgeGraphService):
        s1 = await svc.create_sector(name="Tech")
        s2 = await svc.create_sector(name="Health")
        await svc.create_industry(name="Software", sector_id=s1["id"])
        await svc.create_industry(name="Biotech", sector_id=s2["id"])
        rows, total = await svc.list_industries(sector_id=s1["id"])
        assert total == 1
        assert rows[0].name == "Software"


# ============================================================
# PROMOTER CRUD
# ============================================================

class TestPromoterCRUD:
    @pytest.mark.asyncio
    async def test_create(self, svc: KnowledgeGraphService):
        result = await svc.create_promoter(name="John Doe", promoter_type="individual", pan="ABCDE1234F")
        assert result["name"] == "John Doe"
        assert result["pan"] == "ABCDE1234F"

    @pytest.mark.asyncio
    async def test_institutional(self, svc: KnowledgeGraphService):
        result = await svc.create_promoter(name="Goldman Sachs", promoter_type="institutional")
        assert result["promoter_type"] == "institutional"

    @pytest.mark.asyncio
    async def test_update(self, svc: KnowledgeGraphService):
        p = await svc.create_promoter(name="Old Name")
        result = await svc.update_promoter(p["id"], name="New Name")
        assert result["name"] == "New Name"


# ============================================================
# COMPANY-PROMOTER LINKS
# ============================================================

class TestCompanyPromoter:
    @pytest.mark.asyncio
    async def test_link(self, svc: KnowledgeGraphService, company: Company):
        p = await svc.create_promoter(name="Promoter A")
        link = await svc.link_company_promoter(company_id=company.id, promoter_id=p["id"], ownership_pct=25.5, role="Promoter")
        assert link["company_id"] == company.id
        assert link["ownership_pct"] == 25.5

    @pytest.mark.asyncio
    async def test_get_company_promoters(self, svc: KnowledgeGraphService, company: Company):
        p1 = await svc.create_promoter(name="P1")
        p2 = await svc.create_promoter(name="P2")
        await svc.link_company_promoter(company.id, p1["id"])
        await svc.link_company_promoter(company.id, p2["id"])
        links = await svc.get_company_promoters(company.id)
        assert len(links) == 2

    @pytest.mark.asyncio
    async def test_get_promoter_companies(self, svc: KnowledgeGraphService, company: Company):
        p = await svc.create_promoter(name="P")
        await svc.link_company_promoter(company.id, p["id"])
        links = await svc.get_promoter_companies(p["id"])
        assert len(links) == 1

    @pytest.mark.asyncio
    async def test_unlink(self, svc: KnowledgeGraphService, company: Company):
        p = await svc.create_promoter(name="P")
        link = await svc.link_company_promoter(company.id, p["id"])
        assert await svc.unlink_company_promoter(link["id"]) is True

    @pytest.mark.asyncio
    async def test_unlink_not_found(self, svc: KnowledgeGraphService):
        assert await svc.unlink_company_promoter(9999) is False


# ============================================================
# SUBSIDIARY
# ============================================================

class TestSubsidiary:
    @pytest.mark.asyncio
    async def test_create(self, svc: KnowledgeGraphService, company: Company, subsidiary_company: Company):
        sub = await svc.create_subsidiary(company.id, subsidiary_company.id, ownership_pct=100.0)
        assert sub["parent_company_id"] == company.id
        assert sub["ownership_pct"] == 100.0

    @pytest.mark.asyncio
    async def test_get_subsidiaries(self, svc: KnowledgeGraphService, company: Company, subsidiary_company: Company):
        await svc.create_subsidiary(company.id, subsidiary_company.id)
        subs = await svc.get_subsidiaries(company.id)
        assert len(subs) == 1

    @pytest.mark.asyncio
    async def test_get_parents(self, svc: KnowledgeGraphService, company: Company, subsidiary_company: Company):
        await svc.create_subsidiary(company.id, subsidiary_company.id)
        parents = await svc.get_parent_companies(subsidiary_company.id)
        assert len(parents) == 1

    @pytest.mark.asyncio
    async def test_delete(self, svc: KnowledgeGraphService, company: Company, subsidiary_company: Company):
        sub = await svc.create_subsidiary(company.id, subsidiary_company.id)
        assert await svc.delete_subsidiary(sub["id"]) is True
        assert len(await svc.get_subsidiaries(company.id)) == 0


# ============================================================
# ENTITY EVENT
# ============================================================

class TestEntityEvent:
    @pytest.mark.asyncio
    async def test_create(self, svc: KnowledgeGraphService, company: Company):
        ev = await svc.create_event(event_type="acquisition", event_date=date.today(), title="Acquisition of Startup", company_id=company.id, impact_score=5.0)
        assert ev["event_type"] == "acquisition"
        assert ev["impact_score"] == 5.0
        assert ev["company_id"] == company.id

    @pytest.mark.asyncio
    async def test_list(self, svc: KnowledgeGraphService):
        await svc.create_event(event_type="ipo", event_date=date.today(), title="IPO Event")
        rows, total = await svc.list_events()
        assert total == 1

    @pytest.mark.asyncio
    async def test_list_filtered(self, svc: KnowledgeGraphService, company: Company):
        await svc.create_event(event_type="merger", event_date=date.today(), title="Merger", company_id=company.id)
        rows, total = await svc.list_events(event_type="merger")
        assert total == 1
        rows, total = await svc.list_events(event_type="ipo")
        assert total == 0

    @pytest.mark.asyncio
    async def test_list_date_range(self, svc: KnowledgeGraphService):
        await svc.create_event(event_type="earnings", event_date=date(2025, 6, 15), title="Q1 Earnings")
        rows, total = await svc.list_events(from_date=date(2025, 6, 1), to_date=date(2025, 6, 30))
        assert total == 1
        rows, total = await svc.list_events(from_date=date(2025, 7, 1))
        assert total == 0

    @pytest.mark.asyncio
    async def test_get_event(self, svc: KnowledgeGraphService):
        ev = await svc.create_event(event_type="dividend", event_date=date.today(), title="Dividend Declared")
        result = await svc.get_event(ev["id"])
        assert result["title"] == "Dividend Declared"

    @pytest.mark.asyncio
    async def test_get_not_found(self, svc: KnowledgeGraphService):
        assert await svc.get_event(9999) is None

    @pytest.mark.asyncio
    async def test_update(self, svc: KnowledgeGraphService):
        ev = await svc.create_event(event_type="stock_split", event_date=date.today(), title="Split")
        updated = await svc.update_event(ev["id"], title="Stock Split Updated", impact_score=3.0)
        assert updated["title"] == "Stock Split Updated"
        assert updated["impact_score"] == 3.0

    @pytest.mark.asyncio
    async def test_delete(self, svc: KnowledgeGraphService):
        ev = await svc.create_event(event_type="ipo", event_date=date.today(), title="IPO")
        assert await svc.delete_event(ev["id"]) is True
        assert await svc.get_event(ev["id"]) is None


# ============================================================
# BUSINESS RELATIONSHIP
# ============================================================

class TestBusinessRelationship:
    @pytest.mark.asyncio
    async def test_create(self, svc: KnowledgeGraphService, company: Company, subsidiary_company: Company):
        br = await svc.create_relationship(
            source_entity_type="company", source_entity_id=company.id,
            target_entity_type="company", target_entity_id=subsidiary_company.id,
            relationship_type="competitor", weight=0.8,
        )
        assert br["relationship_type"] == "competitor"
        assert br["weight"] == 0.8

    @pytest.mark.asyncio
    async def test_get_entity_relationships(self, svc: KnowledgeGraphService, company: Company, subsidiary_company: Company):
        await svc.create_relationship("company", company.id, "company", subsidiary_company.id, "partner")
        rels = await svc.get_entity_relationships("company", company.id)
        assert len(rels) == 1

    @pytest.mark.asyncio
    async def test_delete(self, svc: KnowledgeGraphService, company: Company, subsidiary_company: Company):
        br = await svc.create_relationship("company", company.id, "company", subsidiary_company.id, "supplier")
        assert await svc.delete_relationship(br["id"]) is True

    @pytest.mark.asyncio
    async def test_delete_not_found(self, svc: KnowledgeGraphService):
        assert await svc.delete_relationship(9999) is False


# ============================================================
# SEARCH
# ============================================================

class TestSearch:
    @pytest.mark.asyncio
    async def test_search_companies(self, svc: KnowledgeGraphService, session: AsyncSession):
        session.add(Company(symbol="AAPL", company_name="Apple Inc", isin="US00001", exchange="NASDAQ"))
        session.add(Company(symbol="GOOG", company_name="Alphabet Inc", isin="US00002", exchange="NASDAQ"))
        await session.flush()
        results = await svc.search(query="Apple")
        assert len(results) >= 1
        assert any(r["entity_type"] == "company" and "Apple" in r["name"] for r in results)

    @pytest.mark.asyncio
    async def test_search_sectors(self, svc: KnowledgeGraphService):
        await svc.create_sector(name="Technology")
        await svc.create_sector(name="Healthcare")
        results = await svc.search(query="Tech")
        assert any(r["entity_type"] == "sector" for r in results)

    @pytest.mark.asyncio
    async def test_search_promoters(self, svc: KnowledgeGraphService):
        await svc.create_promoter(name="Mukesh Ambani")
        results = await svc.search(query="Mukesh")
        assert any(r["entity_type"] == "promoter" for r in results)

    @pytest.mark.asyncio
    async def test_search_events(self, svc: KnowledgeGraphService):
        await svc.create_event(event_type="merger", event_date=date.today(), title="Big Merger Announcement")
        results = await svc.search(query="Merger")
        assert any(r["entity_type"] == "event" for r in results)

    @pytest.mark.asyncio
    async def test_search_empty(self, svc: KnowledgeGraphService):
        results = await svc.search(query="NonexistentXYZ")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_search_limit(self, svc: KnowledgeGraphService):
        for i in range(5):
            await svc.create_sector(name=f"Sector{i}")
        results = await svc.search(query="Sector", limit=2)
        assert len(results) <= 2


# ============================================================
# GRAPH TRAVERSAL
# ============================================================

class TestGraphTraversal:
    @pytest.mark.asyncio
    async def test_company_graph(self, svc: KnowledgeGraphService, session: AsyncSession, company: Company):
        sub = Company(symbol="SUB2", company_name="Subsidiary 2", isin="IN00003", exchange="NSE")
        session.add(sub)
        await session.flush()

        await svc.create_subsidiary(company.id, sub.id)
        p = await svc.create_promoter(name="Founder")
        await svc.link_company_promoter(company.id, p["id"])

        graph = await svc.get_company_graph(company.id)
        assert graph["node_count"] >= 3
        assert graph["edge_count"] >= 2
        assert graph["company"]["id"] == company.id

    @pytest.mark.asyncio
    async def test_company_graph_not_found(self, svc: KnowledgeGraphService):
        graph = await svc.get_company_graph(9999)
        assert graph["error"] == "Company not found"

    @pytest.mark.asyncio
    async def test_entity_connections_sector(self, svc: KnowledgeGraphService):
        sec = await svc.create_sector(name="Energy")
        await svc.create_industry(name="Oil & Gas", sector_id=sec["id"])
        conn = await svc.get_entity_connections("sector", sec["id"])
        assert conn["node_count"] >= 2

    @pytest.mark.asyncio
    async def test_entity_connections_promoter(self, svc: KnowledgeGraphService, company: Company):
        p = await svc.create_promoter(name="Promoter X")
        await svc.link_company_promoter(company.id, p["id"])
        conn = await svc.get_entity_connections("promoter", p["id"])
        assert conn["node_count"] >= 2


# ============================================================
# CASCADE EDGE CASES
# ============================================================

class TestCascade:
    @pytest.mark.asyncio
    async def test_delete_sector_cascades_industry(self, svc: KnowledgeGraphService):
        sec = await svc.create_sector(name="Tech")
        await svc.create_industry(name="Software", sector_id=sec["id"])
        await svc.delete_sector(sec["id"])
        rows, total = await svc.list_industries(sector_id=sec["id"])
        assert total == 0

    @pytest.mark.asyncio
    async def test_delete_promoter_cascades_links(self, svc: KnowledgeGraphService, company: Company):
        p = await svc.create_promoter(name="P")
        await svc.link_company_promoter(company.id, p["id"])
        await svc.delete_promoter(p["id"])
        links = await svc.get_company_promoters(company.id)
        assert len(links) == 0

    @pytest.mark.asyncio
    async def test_list_promoters_pagination(self, svc: KnowledgeGraphService):
        for i in range(5):
            await svc.create_promoter(name=f"Promoter{i}")
        rows, total = await svc.list_promoters(skip=0, limit=2)
        assert total == 5
        assert len(rows) == 2
