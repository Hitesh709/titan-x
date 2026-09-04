"""SQLite compatibility revision replacing the retired TimescaleDB migration.

Revision ID: 0004
Revises: 0003

The historical 0004 revision configured PostgreSQL/TimescaleDB. Titan X now
uses SQLite, so this revision intentionally performs no database-specific work
while preserving the Alembic revision chain for existing installations.
"""
from collections.abc import Sequence

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No-op: SQLite schema is managed from SQLAlchemy metadata."""


def downgrade() -> None:
    """No-op: the retired TimescaleDB objects are not part of SQLite."""
