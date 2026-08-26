"""Add hashed MFA recovery-code storage to users.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-26
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("mfa_recovery_codes_hashes", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "mfa_recovery_codes_hashes")
