"""Safe production bootstrap for the built-in TITAN X demo account."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from titan_x.core.security import hash_password
from titan_x.models.paper_trading import PaperAccount
from titan_x.models.subscription import Subscription
from titan_x.models.user import User
from titan_x.core.seed_demo import DEMO_EMAIL, DEMO_PASSWORD


async def ensure_demo_user(session_factory: async_sessionmaker) -> bool:
    """Create the demo user/account and keep its premium demo entitlement active.

    The demo account is intentionally a Titan 999 account so it can demonstrate
    the complete recommendation range, including Low/Medium/High risk results.
    Existing paper-trading data is never reset.
    """
    async with session_factory() as session:
        async with session.begin():
            user = (
                await session.execute(select(User).where(User.email == DEMO_EMAIL))
            ).scalar_one_or_none()
            created = False
            if user is None:
                user = User(
                    email=DEMO_EMAIL,
                    hashed_password=hash_password(DEMO_PASSWORD),
                    username="demo",
                    is_active=True,
                    is_verified=True,
                )
                session.add(user)
                await session.flush()
                created = True

            account = (
                await session.execute(
                    select(PaperAccount).where(PaperAccount.user_id == user.id)
                )
            ).scalar_one_or_none()
            if account is None:
                session.add(
                    PaperAccount(
                        user_id=user.id,
                        initial_capital=10_000_000.00,
                        cash_balance=10_000_000.00,
                        currency="INR",
                        is_active=True,
                    )
                )

            now = datetime.now(timezone.utc)
            subscriptions = (
                await session.execute(
                    select(Subscription)
                    .where(Subscription.user_id == user.id)
                    .order_by(Subscription.expires_at.desc())
                )
            ).scalars().all()
            current_999 = next(
                (
                    item
                    for item in subscriptions
                    if item.plan_code == "TITAN_999"
                    and item.status == "active"
                    and (
                        item.expires_at is None
                        or (
                            item.expires_at.replace(tzinfo=timezone.utc)
                            if item.expires_at.tzinfo is None
                            else item.expires_at
                        )
                        >= now
                    )
                ),
                None,
            )
            if current_999 is None:
                for item in subscriptions:
                    if item.status == "active":
                        item.status = "replaced"
                session.add(
                    Subscription(
                        user_id=user.id,
                        plan_code="TITAN_999",
                        status="active",
                        starts_at=now,
                        expires_at=now + timedelta(days=7),
                        provider="demo",
                        provider_subscription_id="demo-titan-999",
                    )
                )
            return created
