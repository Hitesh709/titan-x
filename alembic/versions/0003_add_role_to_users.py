"""Add role column to users table

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-15 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'normal'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "role")
