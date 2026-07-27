from abc import ABC, abstractmethod
from datetime import datetime, timezone

from titan_x.models.broker import BrokerConnection


class BrokerAdapter(ABC):
    @abstractmethod
    async def place_order(self, connection: BrokerConnection, order_data: dict) -> dict:
        ...

    @abstractmethod
    async def cancel_order(self, connection: BrokerConnection, broker_order_id: str) -> dict:
        ...

    @abstractmethod
    async def get_positions(self, connection: BrokerConnection) -> list[dict]:
        ...

    @abstractmethod
    async def get_orders(self, connection: BrokerConnection) -> list[dict]:
        ...

    @abstractmethod
    async def get_holdings(self, connection: BrokerConnection) -> list[dict]:
        ...

    @abstractmethod
    async def get_profile(self, connection: BrokerConnection) -> dict:
        ...

    @abstractmethod
    async def authenticate(self, connection: BrokerConnection, request_token: str | None = None) -> bool:
        ...


class MockBrokerAdapter(BrokerAdapter):
    async def place_order(self, connection: BrokerConnection, order_data: dict) -> dict:
        return {
            "broker_order_id": "MOCK" + str(hash(str(order_data)) % 10**8),
            "status": "open",
            "symbol": order_data.get("symbol", ""),
            "quantity": order_data.get("quantity", 0),
            "price": order_data.get("price"),
            "placed_at": datetime.now(timezone.utc).isoformat(),
        }

    async def cancel_order(self, connection: BrokerConnection, broker_order_id: str) -> dict:
        return {"broker_order_id": broker_order_id, "status": "cancelled"}

    async def get_positions(self, connection: BrokerConnection) -> list[dict]:
        return []

    async def get_orders(self, connection: BrokerConnection) -> list[dict]:
        return []

    async def get_holdings(self, connection: BrokerConnection) -> list[dict]:
        return []

    async def get_profile(self, connection: BrokerConnection) -> dict:
        return {"broker": connection.broker_name, "connected": True, "account_id": f"mock_{connection.user_id}"}

    async def authenticate(self, connection: BrokerConnection, request_token: str | None = None) -> bool:
        connection.access_token = "mock_token_" + str(connection.user_id)
        connection.token_expires_at = datetime.now(timezone.utc)
        return True


class ZerodhaAdapter(BrokerAdapter):
    async def place_order(self, connection: BrokerConnection, order_data: dict) -> dict:
        raise NotImplementedError("Zerodha not implemented in this environment")

    async def cancel_order(self, connection: BrokerConnection, broker_order_id: str) -> dict:
        raise NotImplementedError("Zerodha not implemented in this environment")

    async def get_positions(self, connection: BrokerConnection) -> list[dict]:
        raise NotImplementedError("Zerodha not implemented in this environment")

    async def get_orders(self, connection: BrokerConnection) -> list[dict]:
        raise NotImplementedError("Zerodha not implemented in this environment")

    async def get_holdings(self, connection: BrokerConnection) -> list[dict]:
        raise NotImplementedError("Zerodha not implemented in this environment")

    async def get_profile(self, connection: BrokerConnection) -> dict:
        raise NotImplementedError("Zerodha not implemented in this environment")

    async def authenticate(self, connection: BrokerConnection, request_token: str | None = None) -> bool:
        raise NotImplementedError("Zerodha not implemented in this environment")


class AngelAdapter(BrokerAdapter):
    async def place_order(self, connection: BrokerConnection, order_data: dict) -> dict:
        raise NotImplementedError("Angel not implemented in this environment")

    async def cancel_order(self, connection: BrokerConnection, broker_order_id: str) -> dict:
        raise NotImplementedError("Angel not implemented in this environment")

    async def get_positions(self, connection: BrokerConnection) -> list[dict]:
        raise NotImplementedError("Angel not implemented in this environment")

    async def get_orders(self, connection: BrokerConnection) -> list[dict]:
        raise NotImplementedError("Angel not implemented in this environment")

    async def get_holdings(self, connection: BrokerConnection) -> list[dict]:
        raise NotImplementedError("Angel not implemented in this environment")

    async def get_profile(self, connection: BrokerConnection) -> dict:
        raise NotImplementedError("Angel not implemented in this environment")

    async def authenticate(self, connection: BrokerConnection, request_token: str | None = None) -> bool:
        raise NotImplementedError("Angel not implemented in this environment")


class UpstoxAdapter(BrokerAdapter):
    async def place_order(self, connection: BrokerConnection, order_data: dict) -> dict:
        raise NotImplementedError("Upstox not implemented in this environment")

    async def cancel_order(self, connection: BrokerConnection, broker_order_id: str) -> dict:
        raise NotImplementedError("Upstox not implemented in this environment")

    async def get_positions(self, connection: BrokerConnection) -> list[dict]:
        raise NotImplementedError("Upstox not implemented in this environment")

    async def get_orders(self, connection: BrokerConnection) -> list[dict]:
        raise NotImplementedError("Upstox not implemented in this environment")

    async def get_holdings(self, connection: BrokerConnection) -> list[dict]:
        raise NotImplementedError("Upstox not implemented in this environment")

    async def get_profile(self, connection: BrokerConnection) -> dict:
        raise NotImplementedError("Upstox not implemented in this environment")

    async def authenticate(self, connection: BrokerConnection, request_token: str | None = None) -> bool:
        raise NotImplementedError("Upstox not implemented in this environment")


def get_broker_adapter(broker_name: str) -> BrokerAdapter:
    adapters = {
        "zerodha": ZerodhaAdapter,
        "angel": AngelAdapter,
        "upstox": UpstoxAdapter,
        "mock": MockBrokerAdapter,
    }
    cls = adapters.get(broker_name.lower())
    if cls is None:
        raise ValueError(f"Unsupported broker: {broker_name}")
    return cls()
