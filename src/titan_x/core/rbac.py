from collections.abc import Callable
from enum import Enum
from typing import Annotated

from fastapi import Depends, HTTPException, status

from titan_x.api.dependencies import get_current_active_user
from titan_x.models.user import User


class Role(str, Enum):
    NORMAL = "normal"
    PREMIUM = "premium"
    ANALYST = "analyst"
    ADMIN = "admin"


_ROLE_LEVELS: dict[Role, int] = {
    Role.NORMAL: 0,
    Role.PREMIUM: 1,
    Role.ANALYST: 2,
    Role.ADMIN: 3,
}


def role_ge(role: Role, minimum: Role) -> bool:
    return _ROLE_LEVELS[role] >= _ROLE_LEVELS[minimum]


def require_role(minimum_role: Role, *, exact: bool = False) -> Callable[[User], User]:
    """Factory that returns a FastAPI dependency guarding endpoint access.

    When *exact* is ``True`` only users whose role matches *minimum_role*
    exactly are allowed.  Otherwise any role at or above the requested level
    is accepted.
    """
    if exact:

        async def _check(user: Annotated[User, Depends(get_current_active_user)]) -> User:
            if user.role != minimum_role.value:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Role '{minimum_role.value}' required",
                )
            return user

    else:

        async def _check(user: Annotated[User, Depends(get_current_active_user)]) -> User:
            if not role_ge(Role(user.role), minimum_role):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient privileges (requires '{minimum_role.value}' or higher)",
                )
            return user

    return _check
