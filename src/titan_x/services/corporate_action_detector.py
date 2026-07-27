import json
import math
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.company import Company
from titan_x.models.corporate_action_detection import CorporateActionDetection
from titan_x.models.price import CorporateAction, DailyPrice
from titan_x.services.corporate_action_engine import AdjustmentEngine, CorporateActionEngine

logger = structlog.get_logger(__name__)

SPLIT_RATIOS = [(2, 1), (3, 1), (4, 1), (5, 1), (10, 1), (2, 5), (1, 2), (1, 5), (1, 10)]
BONUS_RATIOS = [(1, 1), (2, 1), (3, 1), (4, 1), (5, 1), (1, 2), (1, 3), (1, 4)]
LOOKBACK_DAYS = 365 * 3
VOLUME_MEDIAN_DAYS = 60
ANOMALY_THRESHOLD = 3.0


class CorporateActionDetector:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = BaseRepository(session, CorporateActionDetection)
        self._engine = CorporateActionEngine(session)

    # ------------------------------------------------------------------
    # Detection Storage
    # ------------------------------------------------------------------

    async def get_detection(self, detection_id: int) -> CorporateActionDetection | None:
        return await self._repo.get(detection_id)

    async def list_detections(
        self, symbol: str | None = None, status: str | None = None,
        detected_type: str | None = None, skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[CorporateActionDetection], int]:
        query = select(CorporateActionDetection)
        cq = select(func.count()).select_from(CorporateActionDetection)
        if symbol is not None:
            query = query.where(CorporateActionDetection.symbol == symbol.upper())
            cq = cq.where(CorporateActionDetection.symbol == symbol.upper())
        if status is not None:
            query = query.where(CorporateActionDetection.status == status)
            cq = cq.where(CorporateActionDetection.status == status)
        if detected_type is not None:
            query = query.where(CorporateActionDetection.detected_type == detected_type)
            cq = cq.where(CorporateActionDetection.detected_type == detected_type)
        total = (await self._session.execute(cq)).scalar() or 0
        query = query.order_by(CorporateActionDetection.detected_date.desc()).offset(skip).limit(limit)
        rows = (await self._session.execute(query)).scalars().all()
        return rows, total

    async def delete_detection(self, detection_id: int) -> bool:
        return await self._repo.delete(detection_id)

    async def _create_detection(
        self, symbol: str, detected_type: str, detected_date: date,
        confidence: float, source: str, **kwargs: Any,
    ) -> CorporateActionDetection:
        existing = await self._session.execute(
            select(CorporateActionDetection).where(
                CorporateActionDetection.symbol == symbol.upper(),
                CorporateActionDetection.detected_type == detected_type,
                CorporateActionDetection.detected_date == detected_date,
                CorporateActionDetection.status == "pending",
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError(f"Pending detection already exists for {symbol} {detected_type} on {detected_date}")
        return await self._repo.create(
            symbol=symbol.upper(), detected_type=detected_type,
            detected_date=detected_date, confidence=min(100.0, max(0.0, confidence)),
            source=source, **{k: v for k, v in kwargs.items() if v is not None},
        )

    # ------------------------------------------------------------------
    # Price Data Helpers
    # ------------------------------------------------------------------

    async def _get_prices(self, symbol: str) -> list[DailyPrice]:
        result = await self._session.execute(
            select(DailyPrice)
            .where(DailyPrice.symbol == symbol.upper())
            .order_by(DailyPrice.trade_date.asc())
        )
        return list(result.scalars().all())

    async def _get_volume_median(self, symbol: str, before: date) -> float:
        result = await self._session.execute(
            select(func.avg(DailyPrice.volume))
            .where(
                DailyPrice.symbol == symbol.upper(),
                DailyPrice.trade_date < before,
                DailyPrice.trade_date >= before - timedelta(days=VOLUME_MEDIAN_DAYS),
            )
        )
        avg = result.scalar()
        return float(avg) if avg else 1.0

    async def _get_existing_actions(self, symbol: str) -> set[tuple[date, str]]:
        result = await self._session.execute(
            select(CorporateAction.action_date, CorporateAction.action_type)
            .where(CorporateAction.symbol == symbol.upper())
        )
        return set(result.all())

    async def _get_companies(self) -> dict[str, int]:
        result = await self._session.execute(
            select(Company.symbol, Company.id)
        )
        return {r[0].upper(): r[1] for r in result.all()}

    # ------------------------------------------------------------------
    # Detector: Stock Splits
    # ------------------------------------------------------------------

    async def detect_splits(self, symbol: str) -> list[CorporateActionDetection]:
        prices = await self._get_prices(symbol)
        existing = await self._get_existing_actions(symbol)
        detections: list[CorporateActionDetection] = []

        if len(prices) < 10:
            return detections

        for i in range(1, len(prices)):
            curr = prices[i]
            prev = prices[i - 1]

            if (curr.trade_date, "split") in existing:
                continue

            price_ratio = prev.close / curr.close if curr.close > 0 else 1.0

            if price_ratio < 1.2:
                continue

            median_vol = max(1.0, await self._get_volume_median(symbol, curr.trade_date))
            vol_ratio = curr.volume / median_vol if median_vol > 0 else 1.0

            best_n, best_d, best_score = 0, 0, 0.0
            for n, d in SPLIT_RATIOS:
                expected_ratio = n / d
                ratio_error = abs(price_ratio - expected_ratio) / expected_ratio
                score = max(0, (1.0 - ratio_error) * 70) + min(30, vol_ratio * 5)
                if score > best_score:
                    best_n, best_d, best_score = n, d, score

            if best_score < 20:
                continue

            before_price = prev.close
            after_price = curr.open
            confidence = min(95.0, best_score)

            try:
                detection = await self._create_detection(
                    symbol=symbol, detected_type="split",
                    detected_date=curr.trade_date,
                    confidence=round(confidence, 1),
                    source="price_anomaly",
                    estimated_numerator=float(best_n),
                    estimated_denominator=float(best_d),
                    price_before=before_price,
                    price_after=after_price,
                    volume_spike_ratio=round(vol_ratio, 2),
                    signal_details_json=json.dumps({
                        "price_ratio": round(price_ratio, 4),
                        "volume_ratio": round(vol_ratio, 2),
                        "best_match": f"{best_n}:{best_d}",
                        "match_score": round(best_score, 1),
                    }),
                )
                detections.append(detection)
            except ValueError:
                continue

        return detections

    # ------------------------------------------------------------------
    # Detector: Bonuses
    # ------------------------------------------------------------------

    async def detect_bonuses(self, symbol: str) -> list[CorporateActionDetection]:
        prices = await self._get_prices(symbol)
        existing = await self._get_existing_actions(symbol)
        detections: list[CorporateActionDetection] = []

        if len(prices) < 10:
            return detections

        for i in range(1, len(prices)):
            curr = prices[i]
            prev = prices[i - 1]

            if (curr.trade_date, "bonus") in existing:
                continue

            price_ratio = prev.close / curr.close if curr.close > 0 else 1.0

            if price_ratio < 1.1 or price_ratio > 3.0:
                continue

            median_vol = max(1.0, await self._get_volume_median(symbol, curr.trade_date))
            vol_ratio = curr.volume / median_vol if median_vol > 0 else 1.0

            best_n, best_d, best_score = 0, 0, 0.0
            for n, d in BONUS_RATIOS:
                expected_factor = (d + n) / d
                ratio_error = abs(price_ratio - expected_factor) / expected_factor
                score = max(0, (1.0 - ratio_error) * 65) + min(25, vol_ratio * 3)
                if score > best_score:
                    best_n, best_d, best_score = n, d, score

            if best_score < 20:
                continue

            confidence = min(90.0, best_score)

            try:
                detection = await self._create_detection(
                    symbol=symbol, detected_type="bonus",
                    detected_date=curr.trade_date,
                    confidence=round(confidence, 1),
                    source="price_anomaly",
                    estimated_numerator=float(best_n),
                    estimated_denominator=float(best_d),
                    price_before=prev.close,
                    price_after=curr.open,
                    volume_spike_ratio=round(vol_ratio, 2),
                    signal_details_json=json.dumps({
                        "price_ratio": round(price_ratio, 4),
                        "volume_ratio": round(vol_ratio, 2),
                        "best_match": f"{best_n}:{best_d}",
                        "match_score": round(best_score, 1),
                    }),
                )
                detections.append(detection)
            except ValueError:
                continue

        return detections

    # ------------------------------------------------------------------
    # Detector: Dividends
    # ------------------------------------------------------------------

    async def detect_dividends(self, symbol: str) -> list[CorporateActionDetection]:
        prices = await self._get_prices(symbol)
        existing = await self._get_existing_actions(symbol)
        detections: list[CorporateActionDetection] = []

        if len(prices) < 20:
            return detections

        for i in range(1, len(prices)):
            curr = prices[i]
            prev = prices[i - 1]

            if (curr.trade_date, "dividend") in existing:
                continue

            gap = prev.close - curr.open
            gap_pct = gap / prev.close if prev.close > 0 else 0

            if gap_pct < 0.005 or gap_pct > 0.50:
                continue

            median_vol = max(1.0, await self._get_volume_median(symbol, curr.trade_date))
            vol_ratio = curr.volume / median_vol if median_vol > 0 else 1.0

            next_day = None
            for j in range(i + 1, min(i + 5, len(prices))):
                next_day = prices[j]
                break
            recovery = 0.0
            if next_day:
                recovery = (next_day.close - curr.open) / curr.open if curr.open > 0 else 0

            vol_score = min(15, abs(vol_ratio - 1.0) * 10)
            recovery_penalty = min(30, max(0, recovery * 100))
            gap_score = min(50, gap_pct * 500)
            confidence = min(85.0, gap_score + vol_score + 15 - recovery_penalty)

            if confidence < 25:
                continue

            est_dividend = round(gap, 2)

            try:
                detection = await self._create_detection(
                    symbol=symbol, detected_type="dividend",
                    detected_date=curr.trade_date,
                    confidence=round(confidence, 1),
                    source="price_anomaly",
                    estimated_dividend_amount=est_dividend,
                    price_before=prev.close,
                    price_after=curr.open,
                    volume_spike_ratio=round(vol_ratio, 2),
                    signal_details_json=json.dumps({
                        "gap": round(gap, 4),
                        "gap_pct": round(gap_pct * 100, 2),
                        "volume_ratio": round(vol_ratio, 2),
                        "recovery_pct": round(recovery * 100, 2),
                        "estimated_dividend": est_dividend,
                    }),
                )
                detections.append(detection)
            except ValueError:
                continue

        return detections

    # ------------------------------------------------------------------
    # Detector: Rights Issues
    # ------------------------------------------------------------------

    async def detect_rights(self, symbol: str) -> list[CorporateActionDetection]:
        prices = await self._get_prices(symbol)
        existing = await self._get_existing_actions(symbol)
        detections: list[CorporateActionDetection] = []

        if len(prices) < 20:
            return detections

        for i in range(1, len(prices)):
            curr = prices[i]
            prev = prices[i - 1]

            if (curr.trade_date, "rights") in existing:
                continue

            price_ratio = prev.close / curr.close if curr.close > 0 else 1.0

            if price_ratio < 1.05 or price_ratio > 2.0:
                continue

            median_vol = max(1.0, await self._get_volume_median(symbol, curr.trade_date))
            vol_ratio = curr.volume / median_vol if median_vol > 0 else 1.0
            if vol_ratio < 1.5:
                continue

            next_days = prices[i + 1 : min(i + 5, len(prices))]
            recovery = 0.0
            if next_days:
                recovery = (next_days[-1].close - curr.open) / curr.open if curr.open > 0 else 0

            sustained = recovery > -0.03
            vol_score = min(25, vol_ratio * 5)
            price_score = max(0, 40 - abs(price_ratio - 1.15) * 100)
            recovery_bonus = 10 if sustained else 0
            confidence = min(80.0, vol_score + price_score + recovery_bonus)

            if confidence < 30:
                continue

            try:
                detection = await self._create_detection(
                    symbol=symbol, detected_type="rights",
                    detected_date=curr.trade_date,
                    confidence=round(confidence, 1),
                    source="price_anomaly",
                    estimated_premium=round(prev.close, 2),
                    estimated_issue_price=round(curr.open * 0.85, 2),
                    price_before=prev.close,
                    price_after=curr.open,
                    volume_spike_ratio=round(vol_ratio, 2),
                    signal_details_json=json.dumps({
                        "price_ratio": round(price_ratio, 4),
                        "volume_ratio": round(vol_ratio, 2),
                        "recovery_pct": round(recovery * 100, 2),
                        "estimated_premium": round(prev.close, 2),
                    }),
                )
                detections.append(detection)
            except ValueError:
                continue

        return detections

    # ------------------------------------------------------------------
    # Detector: Mergers & Acquisitions
    # ------------------------------------------------------------------

    async def detect_mergers(self, symbol: str) -> list[CorporateActionDetection]:
        prices = await self._get_prices(symbol)
        existing = await self._get_existing_actions(symbol)
        detections: list[CorporateActionDetection] = []

        company_map = await self._get_companies()
        if symbol.upper() not in company_map:
            return detections

        if len(prices) < 60:
            return detections

        recent = prices[-60:]
        avg_vol = sum(p.volume for p in recent) / len(recent) if recent else 1

        for i in range(len(recent) - 5, len(recent)):
            curr = recent[i]
            if (curr.trade_date, "merger") in existing:
                continue

            before_avg = sum(p.close for p in recent[:30]) / 30 if len(recent) >= 30 else 1
            after_price = curr.close
            price_jump = after_price / before_avg if before_avg > 0 else 1.0

            if price_jump < 1.5:
                continue

            vol_spike = curr.volume / avg_vol if avg_vol > 0 else 1
            if vol_spike < 2.0:
                continue

            confidence = min(70.0, min(price_jump * 15, 50) + min(vol_spike * 5, 30))

            try:
                detection = await self._create_detection(
                    symbol=symbol, detected_type="merger",
                    detected_date=curr.trade_date,
                    confidence=round(confidence, 1),
                    source="price_anomaly",
                    price_before=round(before_avg, 2),
                    price_after=after_price,
                    volume_spike_ratio=round(vol_spike, 2),
                    signal_details_json=json.dumps({
                        "price_jump_pct": round((price_jump - 1) * 100, 2),
                        "volume_ratio": round(vol_spike, 2),
                        "avg_price_30d": round(before_avg, 2),
                    }),
                )
                detections.append(detection)
            except ValueError:
                continue

        return detections

    async def detect_acquisitions(self, symbol: str) -> list[CorporateActionDetection]:
        prices = await self._get_prices(symbol)
        existing = await self._get_existing_actions(symbol)
        detections: list[CorporateActionDetection] = []

        company_map = await self._get_companies()
        if symbol.upper() not in company_map:
            return detections

        if len(prices) < 60:
            return detections

        recent = prices[-60:]
        avg_vol = sum(p.volume for p in recent) / len(recent) if recent else 1

        for i in range(len(recent) - 5, len(recent)):
            curr = recent[i]
            if (curr.trade_date, "acquisition") in existing:
                continue

            before_avg = sum(p.close for p in recent[:30]) / 30 if len(recent) >= 30 else 1
            after_price = curr.close
            price_jump = after_price / before_avg if before_avg > 0 else 1.0

            if price_jump < 1.3:
                continue

            vol_spike = curr.volume / avg_vol if avg_vol > 0 else 1
            if vol_spike < 3.0:
                continue

            remaining = prices[prices.index(curr) + 1 :]
            sustained = False
            if remaining:
                later_avg = sum(p.close for p in remaining[:min(10, len(remaining))]) / min(10, len(remaining))
                sustained = later_avg > before_avg * 1.15

            premium_score = min(40, (price_jump - 1) * 50)
            vol_score = min(35, vol_spike * 5)
            sustained_bonus = 15 if sustained else 0
            confidence = min(85.0, premium_score + vol_score + sustained_bonus)

            if confidence < 30:
                continue

            try:
                detection = await self._create_detection(
                    symbol=symbol, detected_type="acquisition",
                    detected_date=curr.trade_date,
                    confidence=round(confidence, 1),
                    source="price_anomaly",
                    price_before=round(before_avg, 2),
                    price_after=after_price,
                    volume_spike_ratio=round(vol_spike, 2),
                    signal_details_json=json.dumps({
                        "price_jump_pct": round((price_jump - 1) * 100, 2),
                        "volume_ratio": round(vol_spike, 2),
                        "avg_price_30d": round(before_avg, 2),
                        "sustained_premium": sustained,
                    }),
                )
                detections.append(detection)
            except ValueError:
                continue

        return detections

    # ------------------------------------------------------------------
    # Run All Detectors
    # ------------------------------------------------------------------

    async def detect_all(self, symbol: str) -> dict[str, Any]:
        result: dict[str, Any] = {"symbol": symbol.upper(), "detections": {}}

        result["detections"]["splits"] = [d.id for d in await self.detect_splits(symbol)]
        result["detections"]["bonuses"] = [d.id for d in await self.detect_bonuses(symbol)]
        result["detections"]["dividends"] = [d.id for d in await self.detect_dividends(symbol)]
        result["detections"]["rights"] = [d.id for d in await self.detect_rights(symbol)]
        result["detections"]["mergers"] = [d.id for d in await self.detect_mergers(symbol)]
        result["detections"]["acquisitions"] = [d.id for d in await self.detect_acquisitions(symbol)]

        total = sum(len(v) for v in result["detections"].values())
        result["total_detections"] = total
        return result

    # ------------------------------------------------------------------
    # Auto-Confirm & Adjust Pipeline
    # ------------------------------------------------------------------

    async def confirm_detection(self, detection_id: int) -> CorporateAction:
        detection = await self._repo.get(detection_id)
        if detection is None:
            raise ValueError("Detection not found")
        if detection.status != "pending":
            raise ValueError(f"Detection status is '{detection.status}', not 'pending'")

        action_type = detection.detected_type
        symbol = detection.symbol
        action_date = detection.detected_date
        description = f"Auto-detected {action_type} (confidence: {detection.confidence:.1f}%)"

        if action_type == "split":
            n = detection.estimated_numerator or 1
            d = detection.estimated_denominator or 1
            action = await self._engine.record_split(symbol, action_date, n, d, description=description)
        elif action_type == "bonus":
            n = detection.estimated_numerator or 1
            d = detection.estimated_denominator or 1
            action = await self._engine.record_bonus(symbol, action_date, n, d, description=description)
        elif action_type == "dividend":
            amt = detection.estimated_dividend_amount or 0
            action = await self._engine.record_dividend(symbol, action_date, amt, description=description)
        elif action_type == "rights":
            n = detection.estimated_numerator or 1
            d = detection.estimated_denominator or 1
            premium = detection.estimated_premium or detection.price_before or 100
            issue_price = detection.estimated_issue_price or (premium * 0.85)
            action = await self._engine.record_rights(symbol, action_date, n, d, premium, issue_price, description=description)
        elif action_type == "merger":
            n = 1
            d = detection.estimated_denominator or 1
            target = detection.target_symbol or "UNKNOWN"
            action = await self._engine.record_merger(symbol, action_date, n, d, target, description=description)
        elif action_type == "acquisition":
            n = 1
            d = detection.estimated_denominator or 1
            old = detection.target_symbol or symbol
            action = await self._engine.record_acquisition(symbol, action_date, n, d, old, description=description)
        else:
            raise ValueError(f"Unsupported action type: {action_type}")

        detection.status = "confirmed"
        detection.confirmed_action_id = action.id
        detection.confirmed_at = func.now()
        await self._session.flush()

        logger.info("detection_confirmed", id=detection_id, type=action_type, action_id=action.id)
        return action

    async def confirm_and_adjust(self, detection_id: int) -> dict[str, Any]:
        action = await self.confirm_detection(detection_id)
        adjust_result = await self._engine.adjust_prices(action.symbol)
        return {
            "action": {"id": action.id, "symbol": action.symbol, "type": action.action_type, "date": str(action.action_date)},
            "adjustment": adjust_result,
        }

    async def auto_detect_and_adjust(self, symbol: str, min_confidence: float = 50.0) -> dict[str, Any]:
        detect_result = await self.detect_all(symbol)
        confirmed: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        for det_type, ids in detect_result["detections"].items():
            for det_id in ids:
                detection = await self._repo.get(det_id)
                if detection is None or detection.confidence < min_confidence:
                    continue
                try:
                    result = await self.confirm_and_adjust(det_id)
                    confirmed.append(result)
                except ValueError as e:
                    errors.append({"detection_id": det_id, "error": str(e)})

        return {
            "symbol": symbol.upper(),
            "detections_found": detect_result["total_detections"],
            "confirmed": len(confirmed),
            "errors": len(errors),
            "details": {"confirmed": confirmed, "errors": errors},
        }
