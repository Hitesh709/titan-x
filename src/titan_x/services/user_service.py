from collections.abc import Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.core.config import Settings
from titan_x.core.security import hash_password
from titan_x.db.repository import BaseRepository
from titan_x.models.user import User


class UserService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings
        self._repo = BaseRepository(session, User)

    async def get_by_id(self, user_id: int) -> User | None:
        return await self._repo.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def list_users(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        order_by: str = "id",
        descending: bool = False,
        search: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
        is_verified: bool | None = None,
        is_superuser: bool | None = None,
    ) -> tuple[Sequence[User], int]:
        stmt = select(User)

        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(User.email.ilike(pattern))

        if role is not None:
            stmt = stmt.where(User.role == role)
        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)
        if is_verified is not None:
            stmt = stmt.where(User.is_verified == is_verified)
        if is_superuser is not None:
            stmt = stmt.where(User.is_superuser == is_superuser)

        count_stmt = stmt
        total_result = await self._session.execute(count_stmt)
        total = len(total_result.scalars().all())

        order_column = getattr(User, order_by, User.id)
        if descending:
            stmt = stmt.order_by(order_column.desc())
        else:
            stmt = stmt.order_by(order_column.asc())

        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        users = result.scalars().all()

        return users, total

    async def create_user(
        self,
        email: str,
        password: str,
        role: str = "normal",
        is_active: bool = True,
        is_superuser: bool = False,
        is_verified: bool = False,
    ) -> User:
        existing = await self.get_by_email(email)
        if existing:
            raise ValueError("Email already registered")
        return await self._repo.create(
            email=email,
            hashed_password=hash_password(password),
            role=role,
            is_active=is_active,
            is_superuser=is_superuser,
            is_verified=is_verified,
        )

    async def update_user(
        self,
        user_id: int,
        *,
        email: str | None = None,
        password: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
        is_superuser: bool | None = None,
        is_verified: bool | None = None,
    ) -> User | None:
        user = await self._repo.get(user_id)
        if user is None:
            return None

        update_kwargs: dict = {}
        if email is not None and email != user.email:
            existing = await self.get_by_email(email)
            if existing and existing.id != user_id:
                raise ValueError("Email already in use")
            update_kwargs["email"] = email
        if password is not None:
            update_kwargs["hashed_password"] = hash_password(password)
        if role is not None:
            update_kwargs["role"] = role
        if is_active is not None:
            update_kwargs["is_active"] = is_active
        if is_superuser is not None:
            update_kwargs["is_superuser"] = is_superuser
        if is_verified is not None:
            update_kwargs["is_verified"] = is_verified

        if not update_kwargs:
            return user

        return await self._repo.update(user_id, **update_kwargs)

    async def delete_user(self, user_id: int) -> bool:
        return await self._repo.delete(user_id)
