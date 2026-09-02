"""Add exchange-specific security listings for NSE/BSE identity."""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "company_listings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("exchange", sa.String(length=8), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("yahoo_symbol", sa.String(length=40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("exchange", "symbol", name="uq_company_listing_exchange_symbol"),
        sa.UniqueConstraint("company_id", "exchange", name="uq_company_listing_company_exchange"),
    )
    op.create_index("ix_company_listings_company_id", "company_listings", ["company_id"])
    op.create_index("ix_company_listings_exchange", "company_listings", ["exchange"])
    op.create_index("ix_company_listings_symbol", "company_listings", ["symbol"])
    op.create_index("ix_company_listings_yahoo_symbol", "company_listings", ["yahoo_symbol"])
    op.create_index("ix_company_listings_is_active", "company_listings", ["is_active"])

    # Backfill the existing security rows. Company remains the ISIN/security
    # identity; this creates its first exchange listing without changing data.
    op.execute(sa.text("""
        INSERT INTO company_listings (created_at, updated_at, company_id, exchange, symbol, yahoo_symbol, is_active)
        SELECT created_at, updated_at, id, exchange, symbol,
               CASE WHEN exchange = 'NSE' THEN symbol || '.NS'
                    WHEN exchange = 'BSE' THEN symbol || '.BO'
                    ELSE symbol END,
               CASE WHEN status = 'active' THEN TRUE ELSE FALSE END
        FROM companies
        WHERE exchange IN ('NSE', 'BSE')
    """))


def downgrade() -> None:
    op.drop_index("ix_company_listings_is_active", table_name="company_listings")
    op.drop_index("ix_company_listings_yahoo_symbol", table_name="company_listings")
    op.drop_index("ix_company_listings_symbol", table_name="company_listings")
    op.drop_index("ix_company_listings_exchange", table_name="company_listings")
    op.drop_index("ix_company_listings_company_id", table_name="company_listings")
    op.drop_table("company_listings")
