import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from titan_x.db.base import Base
from titan_x.infrastructure.broker_adapters import (
    MockBrokerAdapter,
    get_broker_adapter,
)
from titan_x.models.broker import BrokerConnection
from titan_x.models.user import User
from titan_x.services.broker_service import BrokerIntegrationService


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
    u = User(email="broker@test.com", hashed_password="hash")
    session.add(u)
    await session.flush()
    return u


@pytest_asyncio.fixture
def svc(session: AsyncSession) -> BrokerIntegrationService:
    return BrokerIntegrationService(session)


# ============================================================
# CONNECTION CRUD
# ============================================================

class TestConnectionCRUD:
    @pytest.mark.asyncio
    async def test_create_connection(self, svc: BrokerIntegrationService, user: User):
        conn = await svc.create_connection(user.id, "zerodha", label="My Zerodha")
        assert conn.broker_name == "zerodha"
        assert conn.label == "My Zerodha"
        assert conn.user_id == user.id
        assert conn.is_active is True
        assert conn.deleted_at is None

    @pytest.mark.asyncio
    async def test_create_connection_with_keys(self, svc: BrokerIntegrationService, user: User):
        conn = await svc.create_connection(
            user.id, "angel", api_key="key123", api_secret="secret456",
        )
        assert conn.api_key == "key123"
        assert conn.api_secret == "secret456"

    @pytest.mark.asyncio
    async def test_create_mock_connection(self, svc: BrokerIntegrationService, user: User):
        conn = await svc.create_connection(user.id, "mock", label="Mock Broker")
        assert conn.broker_name == "mock"

    @pytest.mark.asyncio
    async def test_get_connection_not_found(self, svc: BrokerIntegrationService):
        assert await svc.get_connection(9999) is None

    @pytest.mark.asyncio
    async def test_get_connection(self, svc: BrokerIntegrationService, user: User):
        conn = await svc.create_connection(user.id, "mock")
        fetched = await svc.get_connection(conn.id)
        assert fetched is not None
        assert fetched.id == conn.id

    @pytest.mark.asyncio
    async def test_list_connections(self, svc: BrokerIntegrationService, user: User):
        await svc.create_connection(user.id, "zerodha", label="A")
        await svc.create_connection(user.id, "angel", label="B")
        conns = await svc.list_connections(user.id)
        assert len(conns) == 2

    @pytest.mark.asyncio
    async def test_list_connections_excludes_deleted(self, svc: BrokerIntegrationService, user: User):
        c1 = await svc.create_connection(user.id, "zerodha", label="Keep")
        c2 = await svc.create_connection(user.id, "angel", label="Delete")
        await svc.delete_connection(c2.id)
        conns = await svc.list_connections(user.id)
        assert len(conns) == 1
        assert conns[0].id == c1.id

    @pytest.mark.asyncio
    async def test_update_connection(self, svc: BrokerIntegrationService, user: User):
        conn = await svc.create_connection(user.id, "mock", label="Old")
        updated = await svc.update_connection(conn.id, label="New Label", is_active=False)
        assert updated is not None
        assert updated.label == "New Label"
        assert updated.is_active is False

    @pytest.mark.asyncio
    async def test_update_connection_not_found(self, svc: BrokerIntegrationService):
        assert await svc.update_connection(9999, label="Nope") is None

    @pytest.mark.asyncio
    async def test_delete_connection(self, svc: BrokerIntegrationService, user: User):
        conn = await svc.create_connection(user.id, "mock")
        ok = await svc.delete_connection(conn.id)
        assert ok is True
        fetched = await svc.get_connection(conn.id)
        assert fetched is not None
        assert fetched.deleted_at is not None

    @pytest.mark.asyncio
    async def test_delete_connection_not_found(self, svc: BrokerIntegrationService):
        assert await svc.delete_connection(9999) is False

    @pytest.mark.asyncio
    async def test_list_available_brokers(self, svc: BrokerIntegrationService):
        brokers = svc.get_available_brokers()
        assert "zerodha" in brokers
        assert "angel" in brokers
        assert "upstox" in brokers
        assert "mock" in brokers


# ============================================================
# AUTHENTICATION
# ============================================================

class TestAuthentication:
    @pytest.mark.asyncio
    async def test_authenticate_not_found(self, svc: BrokerIntegrationService):
        result = await svc.authenticate(9999)
        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_mock(self, svc: BrokerIntegrationService, user: User):
        conn = await svc.create_connection(user.id, "mock")
        result = await svc.authenticate(conn.id)
        assert result is not None
        assert result.is_active is True
        assert result.access_token is not None

    @pytest.mark.asyncio
    async def test_authenticate_real_broker_raises(self, svc: BrokerIntegrationService, user: User):
        conn = await svc.create_connection(user.id, "zerodha")
        with pytest.raises(NotImplementedError):
            await svc.authenticate(conn.id)


# ============================================================
# MOCK BROKER ADAPTER
# ============================================================

class TestMockAdapter:
    @pytest.mark.asyncio
    async def test_place_order(self, svc: BrokerIntegrationService, user: User):
        conn = await svc.create_connection(user.id, "mock")
        await svc.authenticate(conn.id)
        result = await svc.place_order(conn.id, {
            "symbol": "RELIANCE",
            "side": "buy",
            "quantity": 10,
            "order_type": "market",
        })
        assert "broker_order_id" in result
        assert result["symbol"] == "RELIANCE"
        assert result["status"] == "open"

    @pytest.mark.asyncio
    async def test_cancel_order(self, svc: BrokerIntegrationService, user: User):
        conn = await svc.create_connection(user.id, "mock")
        await svc.authenticate(conn.id)
        result = await svc.cancel_order(conn.id, "ORDER123")
        assert result["broker_order_id"] == "ORDER123"
        assert result["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_get_positions(self, svc: BrokerIntegrationService, user: User):
        conn = await svc.create_connection(user.id, "mock")
        await svc.authenticate(conn.id)
        positions = await svc.get_positions(conn.id)
        assert positions == []

    @pytest.mark.asyncio
    async def test_get_holdings(self, svc: BrokerIntegrationService, user: User):
        conn = await svc.create_connection(user.id, "mock")
        await svc.authenticate(conn.id)
        holdings = await svc.get_holdings(conn.id)
        assert holdings == []

    @pytest.mark.asyncio
    async def test_get_profile(self, svc: BrokerIntegrationService, user: User):
        conn = await svc.create_connection(user.id, "mock")
        await svc.authenticate(conn.id)
        profile = await svc.get_profile(conn.id)
        assert profile["broker"] == "mock"
        assert profile["connected"] is True

    @pytest.mark.asyncio
    async def test_sync_orders(self, svc: BrokerIntegrationService, user: User):
        conn = await svc.create_connection(user.id, "mock")
        await svc.authenticate(conn.id)
        orders = await svc.sync_orders(conn.id)
        assert orders == []

    @pytest.mark.asyncio
    async def test_place_order_not_active(self, svc: BrokerIntegrationService, user: User):
        conn = await svc.create_connection(user.id, "mock")
        await svc.update_connection(conn.id, is_active=False)
        with pytest.raises(ValueError, match="not active"):
            await svc.place_order(conn.id, {"symbol": "TEST", "side": "buy", "quantity": 1})

    @pytest.mark.asyncio
    async def test_place_order_not_found(self, svc: BrokerIntegrationService):
        with pytest.raises(ValueError, match="not found"):
            await svc.place_order(9999, {})

    @pytest.mark.asyncio
    async def test_unsupported_broker(self):
        with pytest.raises(ValueError, match="Unsupported broker"):
            get_broker_adapter("nonexistent")

    @pytest.mark.asyncio
    async def test_get_adapter_zerodha(self):
        adapter = get_broker_adapter("zerodha")
        from titan_x.infrastructure.broker_adapters import ZerodhaAdapter
        assert isinstance(adapter, ZerodhaAdapter)

    @pytest.mark.asyncio
    async def test_get_adapter_angel(self):
        adapter = get_broker_adapter("angel")
        from titan_x.infrastructure.broker_adapters import AngelAdapter
        assert isinstance(adapter, AngelAdapter)

    @pytest.mark.asyncio
    async def test_get_adapter_upstox(self):
        adapter = get_broker_adapter("upstox")
        from titan_x.infrastructure.broker_adapters import UpstoxAdapter
        assert isinstance(adapter, UpstoxAdapter)

    @pytest.mark.asyncio
    async def test_get_adapter_mock(self):
        adapter = get_broker_adapter("mock")
        assert isinstance(adapter, MockBrokerAdapter)

    @pytest.mark.asyncio
    async def test_mock_authenticate_sets_token(self, user: User, session: AsyncSession):
        conn = BrokerConnection(user_id=user.id, broker_name="mock")
        session.add(conn)
        await session.flush()
        adapter = MockBrokerAdapter()
        success = await adapter.authenticate(conn)
        assert success is True
        assert conn.access_token is not None
        assert conn.access_token.startswith("mock_token_")
