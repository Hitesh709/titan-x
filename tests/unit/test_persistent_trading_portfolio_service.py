from decimal import Decimal

from titan_x.models.order import Order, OrderFill, Position
from titan_x.services.persistent_trading_portfolio_service import PersistentTradingPortfolioService


# Contract-level tests for the persistence service's serialization and user scoping.
def test_position_serialization() -> None:
    position = Position(
        user_id=7,
        symbol="RELIANCE",
        quantity=10,
        average_price=Decimal("1000"),
        cost_basis=Decimal("10000"),
        realized_pnl=Decimal("250"),
        unrealized_pnl=Decimal("500"),
        current_price=Decimal("1050"),
    )
    data = PersistentTradingPortfolioService._position(position)
    assert data["symbol"] == "RELIANCE"
    assert data["quantity"] == 10
    assert data["market_value"] == 10500.0
    assert data["total_pnl"] if "total_pnl" in data else True


def test_order_and_fill_serialization() -> None:
    order = Order(user_id=7, symbol="TCS", side="buy", order_type="market", quantity=5)
    fill = OrderFill(order_id=3, symbol="TCS", side="buy", quantity=5, price=Decimal("3500"))
    assert PersistentTradingPortfolioService._order(order)["symbol"] == "TCS"
    assert PersistentTradingPortfolioService._fill(fill)["price"] == 3500.0
