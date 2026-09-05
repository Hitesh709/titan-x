"""Safe production bootstrap for the built-in TITAN X demo account."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from titan_x.core.security import hash_password
from titan_x.models.paper_trading import PaperAccount
from titan_x.models.user import User
from titan_x.core.seed_demo import DEMO_EMAIL, DEMO_PASSWORD


async def ensure_demo_user(session_factory: async_sessionmaker) -> bool:
    """Create the demo user/account only when missing; never reset user data."""
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
            return created
