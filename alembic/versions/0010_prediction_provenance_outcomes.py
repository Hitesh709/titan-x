"""Add point-in-time prediction audit and outcome tracking.

Revision ID: 0010
Revises: 0009
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prediction_audits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("prediction_id", sa.Integer(), sa.ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recommendation_id", sa.Integer(), sa.ForeignKey("recommendations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_snapshot_ref", sa.Text(), nullable=True),
        sa.Column("data_source_ref", sa.Text(), nullable=True),
        sa.Column("feature_version_ref", sa.Text(), nullable=True),
        sa.Column("model_version_ref", sa.Text(), nullable=True),
        sa.Column("market_regime", sa.String(length=32), nullable=True),
        sa.Column("input_hash", sa.String(length=128), nullable=False),
        sa.Column("explanation_hash", sa.String(length=128), nullable=True),
        sa.Column("audit_schema_version", sa.String(length=16), nullable=False, server_default="1.0.0"),
        sa.UniqueConstraint("prediction_id", name="uq_prediction_audit_prediction"),
    )
    op.create_index("ix_prediction_audit_symbol_asof", "prediction_audits", ["symbol", "as_of_date"])
    op.create_index("ix_prediction_audit_generated", "prediction_audits", ["generated_at"])
    op.create_index("ix_prediction_audit_input_hash", "prediction_audits", ["input_hash"])

    op.create_table(
        "prediction_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("audit_id", sa.Integer(), sa.ForeignKey("prediction_audits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("observation_date", sa.Date(), nullable=True),
        sa.Column("entry_price", sa.Float(), nullable=True),
        sa.Column("close_price", sa.Float(), nullable=True),
        sa.Column("close_return_pct", sa.Float(), nullable=True),
        sa.Column("max_favorable_excursion_pct", sa.Float(), nullable=True),
        sa.Column("max_adverse_excursion_pct", sa.Float(), nullable=True),
        sa.Column("target_hit", sa.Boolean(), nullable=True),
        sa.Column("stop_hit", sa.Boolean(), nullable=True),
        sa.Column("direction_correct", sa.Boolean(), nullable=True),
        sa.Column("resolution_status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome_metadata_json", sa.Text(), nullable=True),
        sa.UniqueConstraint("audit_id", "horizon_days", name="uq_prediction_outcome_horizon"),
    )
    op.create_index("ix_prediction_outcome_horizon", "prediction_outcomes", ["horizon_days"])
    op.create_index("ix_prediction_outcome_resolved", "prediction_outcomes", ["resolved_at"])


def downgrade() -> None:
    op.drop_index("ix_prediction_outcome_resolved", table_name="prediction_outcomes")
    op.drop_index("ix_prediction_outcome_horizon", table_name="prediction_outcomes")
    op.drop_table("prediction_outcomes")
    op.drop_index("ix_prediction_audit_input_hash", table_name="prediction_audits")
    op.drop_index("ix_prediction_audit_generated", table_name="prediction_audits")
    op.drop_index("ix_prediction_audit_symbol_asof", table_name="prediction_audits")
    op.drop_table("prediction_audits")
