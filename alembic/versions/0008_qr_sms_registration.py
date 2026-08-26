"""Adapt QR authentication for browser-based SMS verification and registration."""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(length=80), nullable=True))
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.add_column("auth_challenges", sa.Column("operation", sa.String(length=20), nullable=False, server_default="LOGIN"))
    op.add_column("auth_challenges", sa.Column("verification_phone", sa.String(length=32), nullable=True))
    op.add_column("auth_challenges", sa.Column("registration_username", sa.String(length=80), nullable=True))
    op.add_column("auth_challenges", sa.Column("registration_email", sa.String(length=320), nullable=True))
    op.add_column("auth_challenges", sa.Column("registration_phone", sa.String(length=32), nullable=True))
    op.add_column("auth_challenges", sa.Column("registration_password_hash", sa.String(length=256), nullable=True))
    op.create_index("ix_auth_challenges_operation", "auth_challenges", ["operation"])


def downgrade() -> None:
    op.drop_index("ix_auth_challenges_operation", table_name="auth_challenges")
    op.drop_column("auth_challenges", "registration_password_hash")
    op.drop_column("auth_challenges", "registration_phone")
    op.drop_column("auth_challenges", "registration_email")
    op.drop_column("auth_challenges", "registration_username")
    op.drop_column("auth_challenges", "verification_phone")
    op.drop_column("auth_challenges", "operation")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_column("users", "username")
