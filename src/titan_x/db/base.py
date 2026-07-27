from typing import Any

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

convention: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=convention)


class Base(DeclarativeBase):
    metadata = metadata

    def __repr__(self) -> str:
        columns = {c.name: getattr(self, c.name) for c in self.__table__.columns}  # type: ignore[arg-type]
        return f"{self.__class__.__name__}({columns})"
