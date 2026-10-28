"""Merge the stock/auth and crypto-paper migration branches.

Both branches contain real schema changes. This merge revision gives fresh installs
and existing installations a single unambiguous Alembic head.
"""

from collections.abc import Sequence

revision: str = "0011_merge_stock_crypto_heads"
down_revision: str | tuple[str, str] | None = ("0010", "0007_crypto_bot")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # All schema changes are performed by the two parent branches.
    pass


def downgrade() -> None:
    # Do not automatically drop tables owned by either parent branch.
    pass
