"""Fail-closed authorization helpers for trading operations."""
from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException, status

from titan_x.models.user import User


def authorize_trade(user: User, *, account_owner_id: int, symbol: str, quantity: int, side: str) -> None:
    """Validate the security boundary before an order can reach an execution service."""
    role = "superuser" if user.is_superuser else user.role
    if role not in {"trader", "admin", "superuser"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Trading permission required")
    if role not in {"admin", "superuser"} and user.id != account_owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account access denied")
    normalized = symbol.strip().upper()
    if not normalized or len(normalized) > 32 or not normalized.replace("-", "").replace(".", "").isalnum():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid symbol")
    if quantity <= 0 or quantity > 10_000_000:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid quantity")
    if side.upper() not in {"BUY", "SELL"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid order side")


def validate_order_price(price: Decimal | None) -> None:
    if price is not None and (price <= 0 or price > Decimal("1000000000")):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid order price")
