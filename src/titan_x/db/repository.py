from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import ColumnElement, Select, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


def _apply_filters(stmt: Select[tuple[ModelT]], model: type[ModelT], filters: dict[str, Any]) -> Select[tuple[ModelT]]:
    """Fold ``filters`` into ``stmt``. Values that are not model columns are ignored."""
    for column, value in filters.items():
        column_attr = getattr(model, column, None)
        if column_attr is None:
            continue
        if isinstance(value, list):
            stmt = stmt.where(column_attr.in_(value))
        elif value is None:
            stmt = stmt.where(column_attr.is_(None))
        else:
            stmt = stmt.where(column_attr == value)
    return stmt


class BaseRepository(Generic[ModelT]):
    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self._session = session
        self._model = model

    async def create(self, **kwargs: Any) -> ModelT:
        instance = self._model(**kwargs)
        self._session.add(instance)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    async def get(self, id: int) -> ModelT | None:
        return await self._session.get(self._model, id)

    async def get_multi(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        order_by: str | None = None,
        descending: bool = False,
        **filters: Any,
    ) -> Sequence[ModelT]:
        stmt = select(self._model)
        stmt = _apply_filters(stmt, self._model, filters)

        if order_by:
            order_column: ColumnElement | None = getattr(self._model, order_by, None)
            if order_column is not None:
                stmt = stmt.order_by(order_column.desc() if descending else order_column.asc())

        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def update(self, id: int, **kwargs: Any) -> ModelT | None:
        stmt = (
            update(self._model)
            .where(self._model.id == id)  # type: ignore[arg-type]
            .values(**kwargs)
            .returning(self._model)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.scalar_one_or_none()

    async def delete(self, id: int) -> bool:
        stmt = delete(self._model).where(self._model.id == id)  # type: ignore[arg-type]
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount > 0

    async def count(self, **filters: Any) -> int:
        stmt = select(self._model)
        stmt = _apply_filters(stmt, self._model, filters)
        result = await self._session.execute(stmt)
        return len(result.scalars().all())
