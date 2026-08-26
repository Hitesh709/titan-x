"""Reusable authorization dependencies for Titan-X."""
from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status

from titan_x.api.dependencies import get_current_active_user
from titan_x.models.user import User

# Keep the role vocabulary explicit. Unknown roles are denied by default.
ROLES = frozenset({"normal", "trader", "analyst", "admin", "superuser"})


def require_roles(*allowed_roles: str) -> Callable[..., Any]:
    """Create a FastAPI dependency that enforces role-based authorization."""
    invalid = set(allowed_roles) - ROLES
    if invalid:
        raise ValueError(f"Unknown roles: {sorted(invalid)}")

    async def dependency(
        current_user: Annotated[User, Depends(get_current_active_user)],
    ) -> User:
        role = "superuser" if current_user.is_superuser else current_user.role
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return dependency


def require_owner(current_user: User, owner_id: int) -> None:
    """Enforce object-level ownership. Admin/superuser may bypass ownership."""
    role = "superuser" if current_user.is_superuser else current_user.role
    if role in {"admin", "superuser"}:
        return
    if current_user.id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this resource",
        )
