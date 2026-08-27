"""Add email OTP verification to QR registration."""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("auth_challenges", "status", type_=sa.String(length=32), existing_type=sa.String(length=16), existing_nullable=False)
    op.add_column("auth_challenges", sa.Column("email_otp_hash", sa.String(length=64), nullable=True))
    op.add_column("auth_challenges", sa.Column("email_otp_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("auth_challenges", sa.Column("email_otp_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("auth_challenges", sa.Column("email_otp_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("auth_challenges", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("auth_challenges", "email_verified_at")
    op.drop_column("auth_challenges", "email_otp_sent_at")
    op.drop_column("auth_challenges", "email_otp_attempts")
    op.drop_column("auth_challenges", "email_otp_expires_at")
    op.drop_column("auth_challenges", "email_otp_hash")
    op.alter_column("auth_challenges", "status", type_=sa.String(length=16), existing_type=sa.String(length=32), existing_nullable=False)
