"""Feature Engineering service facade.

Definition management, value storage, dispatch and shared helpers live here;
the per-category ``_compute_*_features`` implementations are provided by the
feature mixins in :mod:`titan_x.services.feature_engineering.computers`.
"""
import json
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from titan_x.models.feature_engineering import FeatureDefinition, FeatureValue
from titan_x.models.price import DailyPrice

from titan_x.services.feature_engineering.computers import (
    BreadthFeaturesMixin,
    FinancialFeaturesMixin,
    MacroFeaturesMixin,
    MomentumFeaturesMixin,
    NewsFeaturesMixin,
    PriceFeaturesMixin,
    VolatilityFeaturesMixin,
    VolumeFeaturesMixin,
)

logger = structlog.get_logger(__name__)

FEATURE_CATEGORIES = [
    "price", "volume", "momentum", "volatility",
    "financial", "news", "macro", "breadth",
]

DEFAULT_VERSION = "1.0.0"


class FeatureEngineeringService(
    PriceFeaturesMixin,
    VolumeFeaturesMixin,
    MomentumFeaturesMixin,
    VolatilityFeaturesMixin,
    FinancialFeaturesMixin,
    NewsFeaturesMixin,
    MacroFeaturesMixin,
    BreadthFeaturesMixin,
):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._log = logger.bind(service="feature_engineering")

    # ============================================================
    # DEFINITION MANAGEMENT
    # ============================================================

    async def register_feature(
        self, name: str, category: str, *,
        description: str | None = None,
        formula: str | None = None,
        parameters: dict[str, Any] | None = None,
        source: str | None = None,
        version: str = DEFAULT_VERSION,
    ) -> FeatureDefinition:
        existing = await self.get_feature_definition(name, version)
        if existing:
            return existing
        fd = FeatureDefinition(
            name=name, category=category, version=version,
            description=description, formula=formula,
            parameters=json.dumps(parameters) if parameters else None,
            source=source, is_active=True,
        )
        self.session.add(fd)
        await self.session.flush()
        self._log.info("feature_registered", name=name, category=category, version=version)
        return fd

    async def get_feature_definition(
        self, name: str, version: str | None = None,
    ) -> FeatureDefinition | None:
        stmt = select(FeatureDefinition).where(FeatureDefinition.name == name)
        if version:
            stmt = stmt.where(FeatureDefinition.version == version)
        else:
            stmt = stmt.order_by(FeatureDefinition.version.desc()).limit(1)
        r = await self.session.execute(stmt)
        return r.scalar_one_or_none()

    async def list_definitions(
        self, category: str | None = None, active_only: bool = True,
    ) -> list[FeatureDefinition]:
        stmt = select(FeatureDefinition).order_by(FeatureDefinition.category, FeatureDefinition.name)
        if category:
            stmt = stmt.where(FeatureDefinition.category == category)
        if active_only:
            stmt = stmt.where(FeatureDefinition.is_active.is_(True))
        r = await self.session.execute(stmt)
        return list(r.scalars().all())

    async def create_new_version(
        self, name: str, *,
        description: str | None = None,
        formula: str | None = None,
        parameters: dict[str, Any] | None = None,
        source: str | None = None,
        change_notes: str | None = None,
    ) -> FeatureDefinition:
        latest = await self.get_feature_definition(name)
        parts = [int(x) for x in (latest.version.split(".") if latest else ["0", "0", "0"])]
        new_version = f"{parts[0]}.{parts[1]}.{parts[2] + 1}"
        fd = FeatureDefinition(
            name=name, category=latest.category if latest else "unknown",
            version=new_version, description=description or (latest.description if latest else None),
            formula=formula or (latest.formula if latest else None),
            parameters=json.dumps(parameters) if parameters else (latest.parameters if latest else None),
            source=source or (latest.source if latest else None),
            is_active=True,
        )
        self.session.add(fd)
        await self.session.flush()
        if latest:
            latest.is_active = False
        self._log.info("feature_version_created", name=name, version=new_version)
        return fd

    # ============================================================
    # VALUE STORAGE
    # ============================================================

    async def _upsert_value(
        self, definition_id: int, symbol: str, as_of_date: date,
        value: float, metadata: dict[str, Any] | None = None,
    ) -> FeatureValue:
        r = await self.session.execute(
            select(FeatureValue).where(
                FeatureValue.feature_definition_id == definition_id,
                FeatureValue.symbol == symbol,
                FeatureValue.as_of_date == as_of_date,
            )
        )
        existing = r.scalar_one_or_none()
        if existing:
            existing.value = value
            existing.metadata_json = json.dumps(metadata) if metadata else None
            return existing
        fv = FeatureValue(
            feature_definition_id=definition_id, symbol=symbol,
            as_of_date=as_of_date, value=value,
            metadata_json=json.dumps(metadata) if metadata else None,
        )
        self.session.add(fv)
        return fv

    async def get_values(
        self, symbol: str | None = None, feature_name: str | None = None,
        category: str | None = None, as_of_date: date | None = None,
        limit: int = 100, offset: int = 0,
    ) -> list[FeatureValue]:
        stmt = (
            select(FeatureValue)
            .options(joinedload(FeatureValue.definition))
            .join(FeatureDefinition)
        )
        if symbol:
            stmt = stmt.where(FeatureValue.symbol == symbol)
        if feature_name:
            stmt = stmt.where(FeatureDefinition.name == feature_name)
        if category:
            stmt = stmt.where(FeatureDefinition.category == category)
        if as_of_date:
            stmt = stmt.where(FeatureValue.as_of_date == as_of_date)
        stmt = stmt.order_by(FeatureValue.as_of_date.desc(), FeatureValue.symbol).offset(offset).limit(limit)
        r = await self.session.execute(stmt)
        return list(r.unique().scalars().all())

    async def count_values(
        self, symbol: str | None = None, feature_name: str | None = None,
        category: str | None = None, as_of_date: date | None = None,
    ) -> int:
        stmt = (
            select(func.count(FeatureValue.id))
            .select_from(FeatureValue)
            .join(FeatureDefinition)
        )
        if symbol:
            stmt = stmt.where(FeatureValue.symbol == symbol)
        if feature_name:
            stmt = stmt.where(FeatureDefinition.name == feature_name)
        if category:
            stmt = stmt.where(FeatureDefinition.category == category)
        if as_of_date:
            stmt = stmt.where(FeatureValue.as_of_date == as_of_date)
        r = await self.session.execute(stmt)
        return r.scalar() or 0

    # ============================================================
    # UTILITY HELPERS
    # ============================================================

    async def _get_or_create_definition(
        self, name: str, category: str, *,
        description: str | None = None,
        formula: str | None = None,
        parameters: dict[str, Any] | None = None,
        source: str | None = None,
    ) -> FeatureDefinition:
        existing = await self.get_feature_definition(name)
        if existing:
            return existing
        return await self.register_feature(
            name, category, description=description,
            formula=formula, parameters=parameters, source=source,
        )

    async def _get_prices(
        self, symbol: str, lookback: int, as_of_date: date,
    ) -> list[DailyPrice]:
        stmt = (
            select(DailyPrice)
            .where(
                DailyPrice.symbol == symbol,
                DailyPrice.trade_date <= as_of_date,
            )
            .order_by(DailyPrice.trade_date.desc())
            .limit(lookback)
        )
        r = await self.session.execute(stmt)
        return list(reversed(r.scalars().all()))

    def _compute_sma(self, values: list[float], period: int) -> float | None:
        if len(values) < period:
            return None
        return sum(values[-period:]) / period

    def _compute_ema(self, values: list[float], period: int) -> float | None:
        if len(values) < period:
            return None
        multiplier = 2.0 / (period + 1)
        ema = sum(values[:period]) / period
        for v in values[period:]:
            ema = (v - ema) * multiplier + ema
        return ema

    def _safe_div(self, a: float, b: float) -> float | None:
        if b is None or b == 0:
            return None
        return a / b

    # ============================================================
    # COMPUTE ALL
    # ============================================================

    async def compute_all_features(self, symbol: str, as_of_date: date | None = None) -> dict[str, int]:
        as_of_date = as_of_date or date.today()
        if as_of_date.weekday() >= 5:
            as_of_date = as_of_date - timedelta(days=as_of_date.weekday() - 4)
        await self.session.flush()
        results = {
            "price": await self._compute_price_features(symbol, as_of_date),
            "volume": await self._compute_volume_features(symbol, as_of_date),
            "momentum": await self._compute_momentum_features(symbol, as_of_date),
            "volatility": await self._compute_volatility_features(symbol, as_of_date),
            "financial": await self._compute_financial_features(symbol, as_of_date),
            "news": await self._compute_news_features(symbol, as_of_date),
            "macro": await self._compute_macro_features(symbol, as_of_date),
            "breadth": await self._compute_breadth_features(symbol, as_of_date),
        }
        await self.session.flush()
        self._log.info("all_features_computed", symbol=symbol, date=as_of_date.isoformat(), counts=results)
        return results

    async def compute_feature(self, feature_name: str, symbol: str, as_of_date: date | None = None) -> float | None:
        as_of_date = as_of_date or date.today()
        if as_of_date.weekday() >= 5:
            as_of_date = as_of_date - timedelta(days=as_of_date.weekday() - 4)
        fd = await self.get_feature_definition(feature_name)
        if not fd:
            return None
        category = fd.category
        await self.session.flush()
        if category == "price":
            await self._compute_price_features(symbol, as_of_date)
        elif category == "volume":
            await self._compute_volume_features(symbol, as_of_date)
        elif category == "momentum":
            await self._compute_momentum_features(symbol, as_of_date)
        elif category == "volatility":
            await self._compute_volatility_features(symbol, as_of_date)
        elif category == "financial":
            await self._compute_financial_features(symbol, as_of_date)
        elif category == "news":
            await self._compute_news_features(symbol, as_of_date)
        elif category == "macro":
            await self._compute_macro_features(symbol, as_of_date)
        elif category == "breadth":
            await self._compute_breadth_features(symbol, as_of_date)
        await self.session.flush()
        r = await self.session.execute(
            select(FeatureValue).where(
                FeatureValue.feature_definition_id == FeatureDefinition.id,
                FeatureDefinition.name == feature_name,
                FeatureValue.symbol == symbol,
                FeatureValue.as_of_date == as_of_date,
            ).join(FeatureDefinition)
        )
        fv = r.scalar_one_or_none()
        return fv.value if fv else None

    # ============================================================
    # CLEAR OLD VALUES
    # ============================================================

    async def clear_old_values(self, older_than_days: int = 90) -> int:
        cutoff = date.today() - timedelta(days=older_than_days)
        r = await self.session.execute(
            delete(FeatureValue).where(FeatureValue.as_of_date < cutoff)
        )
        await self.session.flush()
        return r.rowcount or 0