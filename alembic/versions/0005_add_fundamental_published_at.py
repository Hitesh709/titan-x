"""Add point-in-time publication timestamp to fundamental metrics.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-22
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fundamental_metrics",
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_fund_metric_symbol_published",
        "fundamental_metrics",
        ["symbol", "published_at"],
        unique=False,
    )
    op.create_index(
        "ix_fund_metric_published",
        "fundamental_metrics",
        ["published_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_fund_metric_published", table_name="fundamental_metrics")
    op.drop_index("ix_fund_metric_symbol_published", table_name="fundamental_metrics")
    op.drop_column("fundamental_metrics", "published_at")
