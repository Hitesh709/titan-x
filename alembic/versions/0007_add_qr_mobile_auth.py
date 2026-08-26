"""Add registered devices and one-time QR authentication challenges."""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_devices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("device_name", sa.String(length=120), nullable=False),
        sa.Column("device_public_key", sa.Text(), nullable=False),
        sa.Column("device_status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_devices_customer_id", "user_devices", ["customer_id"])
    op.create_index("ix_user_devices_device_status", "user_devices", ["device_status"])
    op.create_table(
        "auth_challenges",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("challenge_id", sa.String(length=64), nullable=False),
        sa.Column("challenge_hash", sa.String(length=64), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("browser_session_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("device_id", sa.Integer(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["device_id"], ["user_devices.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("challenge_id"),
        sa.UniqueConstraint("challenge_hash"),
    )
    op.create_index("ix_auth_challenges_status", "auth_challenges", ["status"])
    op.create_index("ix_auth_challenges_expires_at", "auth_challenges", ["expires_at"])
    op.create_index("ix_auth_challenges_customer_id", "auth_challenges", ["customer_id"])
    op.create_index("ix_auth_challenges_device_id", "auth_challenges", ["device_id"])
    op.create_index("ix_auth_challenges_browser_session_id", "auth_challenges", ["browser_session_id"])
    op.create_index("ix_auth_challenges_status_expires_at", "auth_challenges", ["status", "expires_at"])


def downgrade() -> None:
    op.drop_table("auth_challenges")
    op.drop_table("user_devices")
