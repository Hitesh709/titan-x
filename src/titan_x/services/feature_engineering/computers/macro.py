"""Macro features (indicator values, MacroFeature fallback)."""
from datetime import date

from sqlalchemy import select

from titan_x.models.feature_engineering import FeatureDefinition, FeatureValue
from titan_x.models.macro import MacroFeature, MacroIndicator


class MacroFeaturesMixin:
    async def _compute_macro_features(self, symbol: str, as_of_date: date) -> int:
        count = 0

        # Fetch latest macro indicators
        indicator_types = ["interest_rate", "inflation_rate", "gdp_growth"]
        for ind_type in indicator_types:
            r = await self.session.execute(
                select(MacroIndicator)
                .where(MacroIndicator.indicator_type == ind_type, MacroIndicator.as_of_date <= as_of_date)
                .order_by(MacroIndicator.as_of_date.desc())
                .limit(1)
            )
            indicator = r.scalar_one_or_none()
            if indicator and indicator.value is not None:
                fd = await self._get_or_create_definition(
                    ind_type, "macro",
                    description=f"Latest {ind_type.replace('_', ' ')}",
                    formula="from MacroIndicator", source="macro_indicator",
                )
                await self._upsert_value(fd.id, symbol, as_of_date, round(indicator.value, 4),
                                         {"as_of_date": indicator.as_of_date.isoformat(), "unit": indicator.unit})
                count += 1

        # Try MacroFeature as fallback
        if count < 3:
            for ind_type in indicator_types:
                existing = await self.session.execute(
                    select(FeatureValue)
                    .join(FeatureDefinition)
                    .where(
                        FeatureDefinition.name == ind_type,
                        FeatureValue.symbol == symbol,
                        FeatureValue.as_of_date == as_of_date,
                    )
                )
                if existing.scalar_one_or_none():
                    continue
                r = await self.session.execute(
                    select(MacroFeature)
                    .where(MacroFeature.feature_name == ind_type, MacroFeature.as_of_date <= as_of_date)
                    .order_by(MacroFeature.as_of_date.desc())
                    .limit(1)
                )
                mf = r.scalar_one_or_none()
                if mf and mf.value is not None:
                    fd = await self._get_or_create_definition(
                        ind_type, "macro",
                        description=f"Latest {ind_type.replace('_', ' ')} (from MacroFeature)",
                        formula="from MacroFeature", source="macro_feature",
                    )
                    await self._upsert_value(fd.id, symbol, as_of_date, round(mf.value, 4),
                                             {"as_of_date": mf.as_of_date.isoformat()})
                    count += 1

        return count