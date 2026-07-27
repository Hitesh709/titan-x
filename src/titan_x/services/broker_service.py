from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.infrastructure.broker_adapters import BrokerAdapter, get_broker_adapter
from titan_x.models.broker import BrokerConnection


class BrokerIntegrationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_connection(
        self,
        user_id: int,
        broker_name: str,
        label: str = "",
        api_key: str | None = None,
        api_secret: str | None = None,
        metadata_json: str | None = None,
    ) -> BrokerConnection:
        conn = BrokerConnection(
            user_id=user_id,
            broker_name=broker_name.lower(),
            label=label or broker_name,
            api_key=api_key,
            api_secret=api_secret,
            metadata_json=metadata_json,
        )
        self.session.add(conn)
        await self.session.flush()
        await self.session.refresh(conn)
        return conn

    async def get_connection(self, connection_id: int) -> BrokerConnection | None:
        return await self.session.get(BrokerConnection, connection_id)

    async def list_connections(self, user_id: int) -> list[BrokerConnection]:
        result = await self.session.execute(
            select(BrokerConnection).where(
                BrokerConnection.user_id == user_id,
                BrokerConnection.deleted_at.is_(None),
            ).order_by(BrokerConnection.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_connection(
        self,
        connection_id: int,
        label: str | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        metadata_json: str | None = None,
        is_active: bool | None = None,
    ) -> BrokerConnection | None:
        conn = await self.get_connection(connection_id)
        if conn is None:
            return None
        if label is not None:
            conn.label = label
        if api_key is not None:
            conn.api_key = api_key
        if api_secret is not None:
            conn.api_secret = api_secret
        if metadata_json is not None:
            conn.metadata_json = metadata_json
        if is_active is not None:
            conn.is_active = is_active
        await self.session.flush()
        return conn

    async def delete_connection(self, connection_id: int) -> bool:
        conn = await self.get_connection(connection_id)
        if conn is None:
            return False
        conn.deleted_at = datetime.now(timezone.utc)
        await self.session.flush()
        return True

    async def authenticate(self, connection_id: int, request_token: str | None = None) -> BrokerConnection | None:
        conn = await self.get_connection(connection_id)
        if conn is None:
            return None
        adapter = get_broker_adapter(conn.broker_name)
        success = await adapter.authenticate(conn, request_token)
        if success:
            conn.is_active = True
            await self.session.flush()
        return conn

    async def place_order(self, connection_id: int, order_data: dict) -> dict:
        conn = await self.get_connection(connection_id)
        if conn is None:
            raise ValueError("Broker connection not found")
        if not conn.is_active:
            raise ValueError("Broker connection is not active")
        adapter = get_broker_adapter(conn.broker_name)
        return await adapter.place_order(conn, order_data)

    async def cancel_order(self, connection_id: int, broker_order_id: str) -> dict:
        conn = await self.get_connection(connection_id)
        if conn is None:
            raise ValueError("Broker connection not found")
        if not conn.is_active:
            raise ValueError("Broker connection is not active")
        adapter = get_broker_adapter(conn.broker_name)
        return await adapter.cancel_order(conn, broker_order_id)

    async def get_positions(self, connection_id: int) -> list[dict]:
        conn = await self.get_connection(connection_id)
        if conn is None:
            raise ValueError("Broker connection not found")
        if not conn.is_active:
            raise ValueError("Broker connection is not active")
        adapter = get_broker_adapter(conn.broker_name)
        return await adapter.get_positions(conn)

    async def get_holdings(self, connection_id: int) -> list[dict]:
        conn = await self.get_connection(connection_id)
        if conn is None:
            raise ValueError("Broker connection not found")
        if not conn.is_active:
            raise ValueError("Broker connection is not active")
        adapter = get_broker_adapter(conn.broker_name)
        return await adapter.get_holdings(conn)

    async def get_profile(self, connection_id: int) -> dict:
        conn = await self.get_connection(connection_id)
        if conn is None:
            raise ValueError("Broker connection not found")
        if not conn.is_active:
            raise ValueError("Broker connection is not active")
        adapter = get_broker_adapter(conn.broker_name)
        return await adapter.get_profile(conn)

    async def sync_orders(self, connection_id: int) -> list[dict]:
        conn = await self.get_connection(connection_id)
        if conn is None:
            raise ValueError("Broker connection not found")
        if not conn.is_active:
            raise ValueError("Broker connection is not active")
        adapter = get_broker_adapter(conn.broker_name)
        return await adapter.get_orders(conn)

    def get_available_brokers(self) -> list[str]:
        return ["zerodha", "angel", "upstox", "mock"]
