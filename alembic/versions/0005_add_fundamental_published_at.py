"""Bootstrap the current SQLAlchemy schema for PostgreSQL/Neon.

Revision ID: 0005
Revises: 0004
"""
from collections.abc import Sequence

from alembic import op

from titan_x.db.base import Base
from titan_x.models import *  # noqa: F401,F403

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The earlier migration chain was written for a schema that was normally
    # created by SQLAlchemy metadata. Bootstrap the complete current schema
    # here so a fresh Neon database does not depend on retired table assumptions.
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    pass
