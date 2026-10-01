"""Add crypto paper bot state."""
from alembic import op
import sqlalchemy as sa
revision="0007_crypto_bot"
down_revision="0006_crypto_paper"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("crypto_paper_bot_states",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column("user_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
        sa.Column("symbol",sa.String(20),nullable=False,server_default="BTCUSDT"),
        sa.Column("enabled",sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column("risk_per_trade",sa.Numeric(8,4),nullable=False,server_default="1"),
        sa.Column("max_position_pct",sa.Numeric(8,4),nullable=False,server_default="25"),
        sa.Column("last_decision",sa.String(10)),
        sa.Column("last_reason",sa.String(500)),
        sa.Column("last_run_at",sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id")
    )
    op.create_index("ix_crypto_paper_bot_states_user_id","crypto_paper_bot_states",["user_id"],unique=True)

def downgrade():
    op.drop_table("crypto_paper_bot_states")
