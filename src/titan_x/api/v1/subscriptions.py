from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from titan_x.api import deps
from titan_x.core.rbac import Role, require_role
from titan_x.models.recommendation import Recommendation
from titan_x.models.subscription import Subscription
from titan_x.models.user import User

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

PLANS = {
    "TITAN_99": {
        "name": "Titan 99",
        "price_inr": 99,
        "billing_period": "weekly",
        "technical_min": 75,
        "technical_max": 80,
        "risk_levels": ["Low", "Medium", "High"],
        "description": "Technical Pillar 75–80 only.",
    },
    "TITAN_499": {
        "name": "Titan 499",
        "price_inr": 499,
        "billing_period": "weekly",
        "technical_min": 81,
        "technical_max": 90,
        "risk_levels": ["Medium"],
        "description": "Technical Pillar 81–90 with Medium risk only.",
    },
    "TITAN_999": {
        "name": "Titan 999",
        "price_inr": 999,
        "billing_period": "weekly",
        "technical_min": 90,
        "technical_max": 100,
        "risk_levels": ["Low", "Medium", "High"],
        "description": "Technical Pillar 90–100 across Low, Medium and High risk.",
    },
}


class AdminSubscriptionRequest(BaseModel):
    user_id: int = Field(ge=1)
    plan_code: str
    days: int = Field(default=7, ge=1, le=3660)
    provider: str | None = None
    provider_subscription_id: str | None = None


def _plan_payload(code: str, plan: dict) -> dict:
    return {"code": code, **plan}


async def _current_subscription(session, user_id: int) -> Subscription | None:
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(Subscription)
        .where(
            Subscription.user_id == user_id,
            Subscription.status == "active",
            Subscription.expires_at >= now,
        )
        .order_by(Subscription.expires_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.get("/plans")
async def subscription_plans() -> dict:
    return {"plans": [_plan_payload(code, plan) for code, plan in PLANS.items()]}


@router.get("/me")
async def my_subscription(
    session=Depends(deps.get_session),
    user: User = Depends(deps.get_current_active_user),
) -> dict:
    subscription = await _current_subscription(session, user.id)
    if subscription is None:
        return {"plan_code": None, "status": "none", "plan": None}
    return {
        "plan_code": subscription.plan_code,
        "status": subscription.status,
        "starts_at": subscription.starts_at.isoformat(),
        "expires_at": subscription.expires_at.isoformat(),
        "plan": _plan_payload(subscription.plan_code, PLANS[subscription.plan_code]),
    }


@router.post("/admin/assign")
async def assign_subscription(
    body: AdminSubscriptionRequest,
    session=Depends(deps.get_session),
    _: User = Depends(require_role(Role.ADMIN)),
) -> dict:
    if body.plan_code not in PLANS:
        raise HTTPException(status_code=400, detail="Unknown subscription plan")
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(User).where(User.id == body.user_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="User not found")

    await session.execute(
        Subscription.__table__.update()
        .where(Subscription.user_id == body.user_id, Subscription.status == "active")
        .values(status="replaced")
    )
    subscription = Subscription(
        user_id=body.user_id,
        plan_code=body.plan_code,
        status="active",
        starts_at=now,
        expires_at=now + timedelta(days=body.days),
        provider=body.provider,
        provider_subscription_id=body.provider_subscription_id,
    )
    session.add(subscription)
    await session.commit()
    return {"message": "Subscription assigned", "subscription_id": subscription.id, "plan": _plan_payload(body.plan_code, PLANS[body.plan_code])}


@router.get("/recommendations")
async def subscription_recommendations(
    limit: int = 100,
    session=Depends(deps.get_session),
    user: User = Depends(deps.get_current_active_user),
) -> dict:
    if limit < 1 or limit > 3000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 3000")
    subscription = await _current_subscription(session, user.id)
    if subscription is None or subscription.plan_code not in PLANS:
        raise HTTPException(status_code=403, detail="An active Titan subscription is required for premium recommendations")

    plan = PLANS[subscription.plan_code]
    result = await session.execute(
        select(Recommendation)
        .where(
            Recommendation.status == "active",
            Recommendation.recommendation_type == "LIVE_SCAN",
            Recommendation.source == "yahoo",
        )
        .order_by(Recommendation.score.desc(), Recommendation.generated_at.desc())
        .limit(3000)
    )

    recommendations = []
    for rec in result.scalars().all():
        try:
            metadata = json.loads(rec.metadata_json or "{}")
        except Exception:
            metadata = {}
        gate = metadata.get("fast_technical_gate") or {}
        raw_score = gate.get("selected_score", gate.get("delivery_score", rec.score or 0))
        try:
            technical_score = float(raw_score)
        except (TypeError, ValueError):
            continue
        risk = str(rec.risk_level or "").strip().title()
        if not (plan["technical_min"] <= technical_score <= plan["technical_max"]):
            continue
        if risk not in plan["risk_levels"]:
            continue
        recommendations.append({
            "id": rec.id,
            "symbol": rec.symbol,
            "direction": rec.direction,
            "signal": rec.signal,
            "confidence": rec.confidence,
            "price_target": rec.price_target,
            "current_price": rec.current_price,
            "timeframe": rec.timeframe,
            "reasoning": rec.reasoning,
            "recommendation_type": rec.recommendation_type,
            "status": rec.status,
            "score": rec.score,
            "technical_pillar_score": technical_score,
            "technical_score": technical_score,
            "risk_level": risk,
            "predicted_return_pct": rec.predicted_return_pct,
            "source": rec.source,
            "model_version_label": rec.model_version_label,
            "generated_at": rec.generated_at.isoformat() if rec.generated_at else None,
            "expires_at": rec.expires_at.isoformat() if rec.expires_at else None,
            "metadata_json": rec.metadata_json,
        })
        if len(recommendations) >= limit:
            break

    return {
        "plan": _plan_payload(subscription.plan_code, plan),
        "recommendations": recommendations,
        "entitlement": {
            "technical_min": plan["technical_min"],
            "technical_max": plan["technical_max"],
            "risk_levels": plan["risk_levels"],
        },
    }
