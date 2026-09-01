"""Persistence helpers for reproducible, point-in-time prediction audits."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.prediction_audit import PredictionAudit, PredictionOutcome


class PredictionAuditService:
    """Create and resolve immutable prediction audit records.

    The service deliberately stores references and hashes rather than copying
    complete market datasets into the transactional database. The referenced
    data-lake snapshot/version remains the source of truth.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def canonical_hash(payload: Any) -> str:
        """Return a deterministic SHA-256 hash for JSON-serializable payloads."""
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    async def record_prediction(
        self,
        *,
        prediction_id: int,
        symbol: str,
        as_of_date: date,
        generated_at: datetime,
        input_payload: Any,
        data_snapshot_ref: Any = None,
        data_source_ref: Any = None,
        feature_version_ref: Any = None,
        model_version_ref: Any = None,
        market_regime: str | None = None,
        explanation_payload: Any = None,
        recommendation_id: int | None = None,
    ) -> PredictionAudit:
        """Persist one audit envelope; repeated writes for a prediction are rejected."""
        existing = await self.session.scalar(
            select(PredictionAudit).where(PredictionAudit.prediction_id == prediction_id)
        )
        if existing is not None:
            return existing

        generated_at = generated_at.astimezone(timezone.utc) if generated_at.tzinfo else generated_at.replace(tzinfo=timezone.utc)
        audit = PredictionAudit(
            prediction_id=prediction_id,
            recommendation_id=recommendation_id,
            symbol=symbol,
            as_of_date=as_of_date,
            generated_at=generated_at,
            data_snapshot_ref=json.dumps(data_snapshot_ref, sort_keys=True, default=str) if data_snapshot_ref is not None else None,
            data_source_ref=json.dumps(data_source_ref, sort_keys=True, default=str) if data_source_ref is not None else None,
            feature_version_ref=json.dumps(feature_version_ref, sort_keys=True, default=str) if feature_version_ref is not None else None,
            model_version_ref=json.dumps(model_version_ref, sort_keys=True, default=str) if model_version_ref is not None else None,
            market_regime=market_regime,
            input_hash=self.canonical_hash(input_payload),
            explanation_hash=self.canonical_hash(explanation_payload) if explanation_payload is not None else None,
        )
        self.session.add(audit)
        await self.session.flush()
        return audit

    async def record_outcome(
        self,
        *,
        audit_id: int,
        horizon_days: int,
        observation_date: date,
        entry_price: float,
        close_price: float,
        max_favorable_excursion_pct: float | None = None,
        max_adverse_excursion_pct: float | None = None,
        target_hit: bool | None = None,
        stop_hit: bool | None = None,
        direction_correct: bool | None = None,
        metadata: Any = None,
    ) -> PredictionOutcome:
        """Upsert the realized outcome for a supported horizon."""
        if horizon_days not in (1, 3, 5, 10, 15, 20, 30):
            raise ValueError("horizon_days must be one of 1, 3, 5, 10, 15, 20, 30")
        if entry_price <= 0 or close_price <= 0:
            raise ValueError("entry_price and close_price must be positive")

        outcome = await self.session.scalar(
            select(PredictionOutcome).where(
                PredictionOutcome.audit_id == audit_id,
                PredictionOutcome.horizon_days == horizon_days,
            )
        )
        close_return_pct = ((close_price / entry_price) - 1.0) * 100.0
        if outcome is None:
            outcome = PredictionOutcome(
                audit_id=audit_id,
                horizon_days=horizon_days,
            )
            self.session.add(outcome)

        outcome.observation_date = observation_date
        outcome.entry_price = entry_price
        outcome.close_price = close_price
        outcome.close_return_pct = close_return_pct
        outcome.max_favorable_excursion_pct = max_favorable_excursion_pct
        outcome.max_adverse_excursion_pct = max_adverse_excursion_pct
        outcome.target_hit = target_hit
        outcome.stop_hit = stop_hit
        outcome.direction_correct = direction_correct
        outcome.resolution_status = "resolved"
        outcome.resolved_at = datetime.now(timezone.utc)
        outcome.outcome_metadata_json = json.dumps(metadata, sort_keys=True, default=str) if metadata is not None else None
        await self.session.flush()
        return outcome
