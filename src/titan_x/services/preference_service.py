from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.preference import UserPreference


class PreferenceService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_preference(self, user_id: int, pref_key: str) -> str | None:
        result = await self.session.execute(
            select(UserPreference).where(
                UserPreference.user_id == user_id,
                UserPreference.pref_key == pref_key,
            )
        )
        pref = result.scalar_one_or_none()
        return pref.pref_value if pref else None

    async def set_preference(self, user_id: int, pref_key: str, pref_value: str) -> UserPreference:
        result = await self.session.execute(
            select(UserPreference).where(
                UserPreference.user_id == user_id,
                UserPreference.pref_key == pref_key,
            )
        )
        pref = result.scalar_one_or_none()
        if pref:
            pref.pref_value = pref_value
        else:
            pref = UserPreference(user_id=user_id, pref_key=pref_key, pref_value=pref_value)
            self.session.add(pref)
        await self.session.flush()
        await self.session.refresh(pref)
        return pref

    async def get_all_preferences(self, user_id: int) -> dict[str, str]:
        result = await self.session.execute(
            select(UserPreference).where(UserPreference.user_id == user_id)
        )
        prefs = result.scalars().all()
        return {p.pref_key: p.pref_value for p in prefs}

    async def delete_preference(self, user_id: int, pref_key: str) -> bool:
        result = await self.session.execute(
            delete(UserPreference).where(
                UserPreference.user_id == user_id,
                UserPreference.pref_key == pref_key,
            )
        )
        await self.session.flush()
        return result.rowcount > 0

    async def delete_all_preferences(self, user_id: int) -> int:
        result = await self.session.execute(
            delete(UserPreference).where(UserPreference.user_id == user_id)
        )
        await self.session.flush()
        return result.rowcount
