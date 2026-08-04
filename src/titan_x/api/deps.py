"""Re-exports from dependencies with shorter names for router use."""
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.api.dependencies import get_current_active_user, request_session
from titan_x.models.user import User

get_session = request_session


async def get_app_session_factory(request: Request):
    """Yield the app-level async_sessionmaker (for long-running background work)."""
    return request.app.state.session_factory


async def get_current_active_superuser(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser access required")
    return current_user


__all__ = ["get_session", "get_current_active_user", "get_current_active_superuser"]
