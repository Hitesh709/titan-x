"""Add loan application workflow storage.

Revision ID: 0005_add_loan_applications
Revises: 0004_setup_timescaledb
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_add_loan_applications"
down_revision = "0004_setup_timescaledb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "loan_applications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("mobile", sa.String(length=20), nullable=False),
        sa.Column("pan", sa.String(length=10), nullable=True),
        sa.Column("pan_name", sa.String(length=200), nullable=True),
        sa.Column("customer_name", sa.String(length=200), nullable=True),
        sa.Column("stage", sa.String(length=50), nullable=False, server_default="MOBILE_VERIFICATION"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="IN_PROGRESS"),
        sa.Column("documents_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("analyses_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("verification_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("risk_grade", sa.String(length=10), nullable=True),
        sa.Column("offer_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_loan_applications_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_loan_applications"),
    )
    op.create_index("ix_loan_applications_mobile", "loan_applications", ["mobile"])
    op.create_index("ix_loan_applications_pan", "loan_applications", ["pan"])
    op.create_index("ix_loan_applications_stage", "loan_applications", ["stage"])
    op.create_index("ix_loan_applications_status", "loan_applications", ["status"])


def downgrade() -> None:
    op.drop_index("ix_loan_applications_status", table_name="loan_applications")
    op.drop_index("ix_loan_applications_stage", table_name="loan_applications")
    op.drop_index("ix_loan_applications_pan", table_name="loan_applications")
    op.drop_index("ix_loan_applications_mobile", table_name="loan_applications")
    op.drop_table("loan_applications")
