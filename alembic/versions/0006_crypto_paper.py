"""Add persistent crypto paper trading tables."""
from alembic import op
import sqlalchemy as sa

revision="0006_crypto_paper"
down_revision="0005"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("crypto_paper_accounts",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column("user_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
        sa.Column("initial_capital",sa.Numeric(20,8),nullable=False,server_default="100000"),
        sa.Column("cash_balance",sa.Numeric(20,8),nullable=False,server_default="100000"),
        sa.Column("currency",sa.String(8),nullable=False,server_default="USDT"),
        sa.Column("is_active",sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.UniqueConstraint("user_id")
    )
    op.create_index("ix_crypto_paper_accounts_user_id","crypto_paper_accounts",["user_id"],unique=True)
    op.create_table("crypto_paper_positions",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column("account_id",sa.Integer(),sa.ForeignKey("crypto_paper_accounts.id",ondelete="CASCADE"),nullable=False),
        sa.Column("user_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
        sa.Column("symbol",sa.String(20),nullable=False),
        sa.Column("quantity",sa.Numeric(28,12),nullable=False,server_default="0"),
        sa.Column("average_price",sa.Numeric(28,12),nullable=False,server_default="0"),
        sa.Column("current_price",sa.Numeric(28,12)),
        sa.Column("realized_pnl",sa.Numeric(20,8),nullable=False,server_default="0"),
        sa.Column("stop_price",sa.Numeric(28,12)),
        sa.Column("take_price",sa.Numeric(28,12)),
        sa.UniqueConstraint("account_id","symbol",name="uq_crypto_paper_position")
    )
    op.create_index("ix_crypto_paper_positions_account_id","crypto_paper_positions",["account_id"])
    op.create_index("ix_crypto_paper_positions_user_id","crypto_paper_positions",["user_id"])
    op.create_index("ix_crypto_paper_positions_symbol","crypto_paper_positions",["symbol"])
    op.create_table("crypto_paper_trades",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column("account_id",sa.Integer(),sa.ForeignKey("crypto_paper_accounts.id",ondelete="CASCADE"),nullable=False),
        sa.Column("user_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
        sa.Column("symbol",sa.String(20),nullable=False),
        sa.Column("side",sa.String(10),nullable=False),
        sa.Column("quantity",sa.Numeric(28,12),nullable=False),
        sa.Column("price",sa.Numeric(28,12),nullable=False),
        sa.Column("realized_pnl",sa.Numeric(20,8)),
        sa.Column("reason",sa.Text()),
        sa.Column("trade_time",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False)
    )
    op.create_index("ix_crypto_paper_trades_account_id","crypto_paper_trades",["account_id"])
    op.create_index("ix_crypto_paper_trades_user_id","crypto_paper_trades",["user_id"])
    op.create_index("ix_crypto_paper_trades_symbol","crypto_paper_trades",["symbol"])

def downgrade():
    op.drop_table("crypto_paper_trades")
    op.drop_table("crypto_paper_positions")
    op.drop_table("crypto_paper_accounts")
