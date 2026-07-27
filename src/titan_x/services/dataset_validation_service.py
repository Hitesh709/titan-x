import json
import math
import statistics
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.corporate_action_detection import CorporateActionDetection
from titan_x.models.data_validation import DataQualityScore, ValidationAnomaly, ValidationRun
from titan_x.models.price import CorporateAction, DailyPrice

logger = structlog.get_logger(__name__)


class DatasetValidationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self._log = logger.bind(service="dataset_validation")

    async def validate_dataset(
        self, symbol: str, date_from: date | None = None, date_to: date | None = None,
    ) -> ValidationRun:
        if date_to is None:
            date_to = date.today()
        if date_from is None:
            date_from = date_to - timedelta(days=365)

        run = ValidationRun(
            symbol=symbol,
            date_from=date_from,
            date_to=date_to,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(run)
        await self.session.flush()
        await self.session.refresh(run)

        try:
            stmt = select(DailyPrice).where(
                DailyPrice.symbol == symbol,
                DailyPrice.trade_date >= date_from,
                DailyPrice.trade_date <= date_to,
            ).order_by(DailyPrice.trade_date)
            r = await self.session.execute(stmt)
            records = list(r.scalars().all())

            run.total_records = len(records)

            anomalies: list[ValidationAnomaly] = []

            anomalies.extend(await self._check_missing_values(run.id, symbol, records))
            anomalies.extend(await self._check_duplicate_rows(run.id, symbol, date_from, date_to, records))
            anomalies.extend(await self._check_price_anomalies(run.id, symbol, records))
            anomalies.extend(await self._check_volume_anomalies(run.id, symbol, records))
            anomalies.extend(await self._check_corporate_action_mismatch(run.id, symbol, records))
            anomalies.extend(await self._check_timestamp_mismatch(run.id, symbol, records, date_from, date_to))

            for anom in anomalies:
                self.session.add(anom)
            await self.session.flush()

            run.anomalies_found = len(anomalies)
            run.missing_values = sum(1 for a in anomalies if a.anomaly_type == "missing_value")
            run.duplicate_rows = sum(1 for a in anomalies if a.anomaly_type == "duplicate_row")
            run.price_anomalies = sum(1 for a in anomalies if a.anomaly_type == "price_anomaly")
            run.volume_anomalies = sum(1 for a in anomalies if a.anomaly_type == "volume_anomaly")
            run.corp_action_mismatches = sum(1 for a in anomalies if a.anomaly_type == "corp_action_mismatch")
            run.timestamp_mismatches = sum(1 for a in anomalies if a.anomaly_type == "timestamp_mismatch")

            score = self._compute_quality_score(
                records, anomalies, date_from, date_to,
            )
            run.quality_score = score["overall_score"]
            run.quality_rating = score["rating"]

            existing_dqs = await self.session.execute(
                select(DataQualityScore).where(
                    DataQualityScore.symbol == symbol,
                    DataQualityScore.score_date == date_to,
                )
            )
            dqs = existing_dqs.scalar_one_or_none()
            if dqs:
                dqs.overall_score = score["overall_score"]
                dqs.completeness_score = score["completeness"]
                dqs.uniqueness_score = score["uniqueness"]
                dqs.accuracy_score = score["accuracy"]
                dqs.consistency_score = score["consistency"]
                dqs.timeliness_score = score["timeliness"]
                dqs.total_checks = score["total_checks"]
                dqs.checks_passed = score["checks_passed"]
                dqs.checks_failed = score["checks_failed"]
                dqs.rating = score["rating"]
                dqs.run_id = run.id
            else:
                dqs = DataQualityScore(
                    symbol=symbol, score_date=date_to,
                    overall_score=score["overall_score"],
                    completeness_score=score["completeness"],
                    uniqueness_score=score["uniqueness"],
                    accuracy_score=score["accuracy"],
                    consistency_score=score["consistency"],
                    timeliness_score=score["timeliness"],
                    total_checks=score["total_checks"],
                    checks_passed=score["checks_passed"],
                    checks_failed=score["checks_failed"],
                    rating=score["rating"],
                    run_id=run.id,
                )
                self.session.add(dqs)

            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)

        except Exception as exc:
            run.status = "failed"
            run.error_message = str(exc)
            self._log.error("validation_failed", symbol=symbol, error=str(exc))

        await self.session.flush()
        await self.session.refresh(run)
        return run

    # ============================================================
    # 1. MISSING VALUES
    # ============================================================

    async def _check_missing_values(
        self, run_id: int, symbol: str, records: list[DailyPrice],
    ) -> list[ValidationAnomaly]:
        anomalies: list[ValidationAnomaly] = []
        required_fields = ["open", "high", "low", "close", "volume"]

        for rec in records:
            for field in required_fields:
                val = getattr(rec, field, None)
                is_invalid = (
                    val is None
                    or (isinstance(val, float) and (math.isnan(val) or math.isinf(val)))
                    or (isinstance(val, (int, float)) and val <= 0)
                )
                if is_invalid:
                    anomalies.append(ValidationAnomaly(
                        run_id=run_id,
                        anomaly_type="missing_value",
                        severity="high",
                        symbol=symbol,
                        trade_date=rec.trade_date,
                        field_name=field,
                        expected_value="non-null number",
                        actual_value=str(val),
                        description=f"Missing or invalid value in '{field}' on {rec.trade_date}: got {val}",
                        details_json=json.dumps({"record_id": rec.id, "record_symbol": rec.symbol, "record_date": rec.trade_date.isoformat()}),
                    ))
        return anomalies

    # ============================================================
    # 2. DUPLICATE ROWS
    # ============================================================

    async def _check_duplicate_rows(
        self, run_id: int, symbol: str,
        date_from: date, date_to: date, records: list[DailyPrice],
    ) -> list[ValidationAnomaly]:
        anomalies: list[ValidationAnomaly] = []

        seen_dates: dict[date, list[DailyPrice]] = {}
        for rec in records:
            seen_dates.setdefault(rec.trade_date, []).append(rec)

        for trade_date, dups in seen_dates.items():
            if len(dups) > 1:
                ohlcvs = [(d.open, d.high, d.low, d.close, d.volume) for d in dups]
                if len(set(ohlcvs)) < len(ohlcvs):
                    anomalies.append(ValidationAnomaly(
                        run_id=run_id,
                        anomaly_type="duplicate_row",
                        severity="high",
                        symbol=symbol,
                        trade_date=trade_date,
                        description=f"Duplicate records found for {symbol} on {trade_date}: {len(dups)} rows",
                        details_json=json.dumps({
                            "row_count": len(dups),
                            "unique_count": len(set(ohlcvs)),
                            "record_ids": [d.id for d in dups if d.id],
                        }),
                    ))
        return anomalies

    # ============================================================
    # 3. PRICE ANOMALIES
    # ============================================================

    async def _check_price_anomalies(
        self, run_id: int, symbol: str, records: list[DailyPrice],
    ) -> list[ValidationAnomaly]:
        anomalies: list[ValidationAnomaly] = []
        if len(records) < 10:
            return anomalies

        closes = [r.close for r in records]
        returns = []
        for i in range(1, len(closes)):
            if closes[i - 1] > 0:
                ret = (closes[i] - closes[i - 1]) / closes[i - 1]
                returns.append(ret)

        if len(returns) < 5:
            return anomalies

        mean_ret = statistics.mean(returns)
        std_ret = statistics.stdev(returns) if len(returns) > 1 else 0.01
        std_ret = max(std_ret, 0.0001)

        for i, rec in enumerate(records):
            # Skip first record since we need previous close
            if i == 0:
                continue
            prev_close = records[i - 1].close
            if prev_close <= 0:
                continue
            daily_ret = (rec.close - prev_close) / prev_close

            z_score = (daily_ret - mean_ret) / std_ret if std_ret > 0 else 0

            if abs(z_score) > 4:
                severity = "high" if abs(z_score) > 6 else "medium"
                anomalies.append(ValidationAnomaly(
                    run_id=run_id,
                    anomaly_type="price_anomaly",
                    severity=severity,
                    symbol=symbol,
                    trade_date=rec.trade_date,
                    field_name="close",
                    expected_value=f"within {4:.0f}σ",
                    actual_value=f"{z_score:.1f}σ ({daily_ret:+.2%})",
                    description=f"Price anomaly on {rec.trade_date}: return {daily_ret:+.2%} (z={z_score:.1f}), prev_close={prev_close:.2f}, close={rec.close:.2f}",
                    details_json=json.dumps({
                        "return_pct": round(daily_ret * 100, 2),
                        "z_score": round(z_score, 2),
                        "prev_close": prev_close,
                        "close": rec.close,
                        "mean_return": round(mean_ret * 100, 2),
                        "std_return": round(std_ret * 100, 2),
                    }),
                ))

        # Gap detection (open vs previous close)
        for i, rec in enumerate(records):
            if i == 0:
                continue
            prev_close = records[i - 1].close
            if prev_close <= 0:
                continue
            gap_pct = (rec.open - prev_close) / prev_close
            if abs(gap_pct) > 0.10:
                anomalies.append(ValidationAnomaly(
                    run_id=run_id,
                    anomaly_type="price_anomaly",
                    severity="medium" if abs(gap_pct) > 0.15 else "low",
                    symbol=symbol,
                    trade_date=rec.trade_date,
                    field_name="open",
                    expected_value=f"gap < 10%",
                    actual_value=f"{gap_pct:+.2%}",
                    description=f"Large price gap on {rec.trade_date}: open={rec.open:.2f} vs prev_close={prev_close:.2f} ({gap_pct:+.2%})",
                    details_json=json.dumps({
                        "gap_pct": round(gap_pct * 100, 2),
                        "open": rec.open,
                        "prev_close": prev_close,
                    }),
                ))

        # Price level anomalies (daily range too large or too small)
        for rec in records:
            if rec.high > 0 and rec.low > 0:
                range_pct = (rec.high - rec.low) / ((rec.high + rec.low) / 2)
                if range_pct > 0.20:
                    anomalies.append(ValidationAnomaly(
                        run_id=run_id,
                        anomaly_type="price_anomaly",
                        severity="low",
                        symbol=symbol,
                        trade_date=rec.trade_date,
                        field_name="high/low",
                        expected_value="range < 20%",
                        actual_value=f"{range_pct:.2%}",
                        description=f"Wide price range on {rec.trade_date}: high={rec.high:.2f}, low={rec.low:.2f} ({range_pct:.2%})",
                        details_json=json.dumps({"range_pct": round(range_pct * 100, 2), "high": rec.high, "low": rec.low}),
                    ))

        return anomalies

    # ============================================================
    # 4. VOLUME ANOMALIES
    # ============================================================

    async def _check_volume_anomalies(
        self, run_id: int, symbol: str, records: list[DailyPrice],
    ) -> list[ValidationAnomaly]:
        anomalies: list[ValidationAnomaly] = []
        if len(records) < 10:
            return anomalies

        volumes = [r.volume for r in records if r.volume > 0]
        if len(volumes) < 5:
            return anomalies

        median_vol = statistics.median(volumes)
        if median_vol == 0:
            return anomalies

        for rec in records:
            if rec.volume <= 0:
                continue
            ratio = rec.volume / median_vol

            if ratio > 5:
                anomalies.append(ValidationAnomaly(
                    run_id=run_id,
                    anomaly_type="volume_anomaly",
                    severity="high" if ratio > 10 else "medium",
                    symbol=symbol,
                    trade_date=rec.trade_date,
                    field_name="volume",
                    expected_value=f"volume < {5:.0f}x median",
                    actual_value=f"{ratio:.1f}x median",
                    description=f"Volume spike on {rec.trade_date}: {rec.volume:,} ({ratio:.1f}x median {median_vol:,})",
                    details_json=json.dumps({"ratio": round(ratio, 2), "volume": rec.volume, "median_volume": median_vol}),
                ))
            elif ratio < 0.1 and len(records) > 20:
                anomalies.append(ValidationAnomaly(
                    run_id=run_id,
                    anomaly_type="volume_anomaly",
                    severity="medium",
                    symbol=symbol,
                    trade_date=rec.trade_date,
                    field_name="volume",
                    expected_value=f"volume > 0.1x median",
                    actual_value=f"{ratio:.1f}x median",
                    description=f"Volume drop on {rec.trade_date}: {rec.volume:,} ({ratio:.1f}x median {median_vol:,})",
                    details_json=json.dumps({"ratio": round(ratio, 2), "volume": rec.volume, "median_volume": median_vol}),
                ))

        return anomalies

    # ============================================================
    # 5. CORPORATE ACTION MISMATCH
    # ============================================================

    async def _check_corporate_action_mismatch(
        self, run_id: int, symbol: str, records: list[DailyPrice],
    ) -> list[ValidationAnomaly]:
        anomalies: list[ValidationAnomaly] = []
        if len(records) < 5:
            return anomalies

        ca_stmt = select(CorporateAction).where(
            CorporateAction.symbol == symbol,
        ).order_by(CorporateAction.action_date)
        r = await self.session.execute(ca_stmt)
        corp_actions = list(r.scalars().all())

        det_stmt = select(CorporateActionDetection).where(
            CorporateActionDetection.symbol == symbol,
            CorporateActionDetection.status == "detected",
        ).order_by(CorporateActionDetection.detected_date)
        r = await self.session.execute(det_stmt)
        detections = list(r.scalars().all())

        if not corp_actions and not detections:
            return anomalies

        date_ca: dict[date, list[CorporateAction]] = {}
        for ca in corp_actions:
            date_ca.setdefault(ca.action_date, []).append(ca)

        date_det: dict[date, list[CorporateActionDetection]] = {}
        for d in detections:
            date_det.setdefault(d.detected_date, []).append(d)

        for i, rec in enumerate(records):
            if i == 0:
                continue
            prev_close = records[i - 1].close
            if prev_close <= 0:
                continue
            ret = (rec.close - prev_close) / prev_close
            abs_ret = abs(ret)

            has_ca = rec.trade_date in date_ca or rec.trade_date in date_det
            significant_move = abs_ret > 0.05

            if significant_move and not has_ca:
                # Check if adjacent date has CA
                adjacent_ca = (
                    (rec.trade_date - timedelta(days=1)) in date_ca or
                    (rec.trade_date + timedelta(days=1)) in date_ca or
                    (rec.trade_date - timedelta(days=1)) in date_det or
                    (rec.trade_date + timedelta(days=1)) in date_det
                )
                if not adjacent_ca and abs_ret > 0.08:
                    anomalies.append(ValidationAnomaly(
                        run_id=run_id,
                        anomaly_type="corp_action_mismatch",
                        severity="medium",
                        symbol=symbol,
                        trade_date=rec.trade_date,
                        field_name="close",
                        expected_value="price move aligned with corp actions",
                        actual_value=f"{ret:+.2%} without recorded corp action",
                        description=f"Price move {ret:+.2%} on {rec.trade_date} has no matching corporate action",
                        details_json=json.dumps({
                            "return_pct": round(ret * 100, 2),
                            "prev_close": prev_close,
                            "close": rec.close,
                            "has_corp_action": False,
                            "adjacent_date_has_action": adjacent_ca,
                        }),
                    ))

            if has_ca and abs_ret < 0.01:
                ca_list = date_ca.get(rec.trade_date, []) + [
                    d for d in detections if d.detected_date == rec.trade_date
                ]
                ca_types = [getattr(c, "action_type", getattr(c, "detected_type", "unknown")) for c in ca_list]
                anomalies.append(ValidationAnomaly(
                    run_id=run_id,
                    anomaly_type="corp_action_mismatch",
                    severity="low",
                    symbol=symbol,
                    trade_date=rec.trade_date,
                    field_name="close",
                    expected_value="price adjusted for corp action",
                    actual_value=f"move={ret:+.2%} with {','.join(ca_types)}",
                    description=f"Corporate action {','.join(ca_types)} on {rec.trade_date} but price only moved {ret:+.2%}",
                    details_json=json.dumps({
                        "return_pct": round(ret * 100, 2),
                        "corp_actions": ca_types,
                        "action_types": ca_types,
                    }),
                ))

        return anomalies

    # ============================================================
    # 6. TIMESTAMP MISMATCH
    # ============================================================

    async def _check_timestamp_mismatch(
        self, run_id: int, symbol: str, records: list[DailyPrice],
        date_from: date, date_to: date,
    ) -> list[ValidationAnomaly]:
        anomalies: list[ValidationAnomaly] = []

        expected_business_days = 0
        current = date_from
        while current <= date_to:
            if current.weekday() < 5:
                expected_business_days += 1
            current += timedelta(days=1)

        actual_days = len(records)
        missing_days = expected_business_days - actual_days
        if missing_days > 0 and expected_business_days > 0:
            missing_pct = missing_days / expected_business_days
            if missing_pct > 0.05:
                anomalies.append(ValidationAnomaly(
                    run_id=run_id,
                    anomaly_type="timestamp_mismatch",
                    severity="medium" if missing_pct > 0.20 else "low",
                    symbol=symbol,
                    field_name="trade_date",
                    expected_value=f"{expected_business_days} business days",
                    actual_value=f"{actual_days} records ({missing_days} missing)",
                    description=f"Missing {missing_days}/{expected_business_days} business days ({missing_pct:.1%}) between {date_from} and {date_to}",
                    details_json=json.dumps({
                        "expected_days": expected_business_days,
                        "actual_days": actual_days,
                        "missing_days": missing_days,
                        "missing_pct": round(missing_pct * 100, 1),
                    }),
                ))

        actual_dates_list = [r.trade_date for r in records]

        for i in range(1, len(actual_dates_list)):
            gap = (actual_dates_list[i] - actual_dates_list[i - 1]).days
            if gap > 5:
                anomalies.append(ValidationAnomaly(
                    run_id=run_id,
                    anomaly_type="timestamp_mismatch",
                    severity="medium" if gap > 20 else "low",
                    symbol=symbol,
                    trade_date=actual_dates_list[i],
                    field_name="trade_date",
                    expected_value="no gap > 5 business days",
                    actual_value=f"{gap} day gap",
                    description=f"Data gap of {gap} days between {actual_dates_list[i - 1]} and {actual_dates_list[i]}",
                    details_json=json.dumps({
                        "gap_days": gap,
                        "from_date": actual_dates_list[i - 1].isoformat(),
                        "to_date": actual_dates_list[i].isoformat(),
                    }),
                ))

        for rec in records:
            if rec.trade_date > date.today():
                anomalies.append(ValidationAnomaly(
                    run_id=run_id,
                    anomaly_type="timestamp_mismatch",
                    severity="high",
                    symbol=symbol,
                    trade_date=rec.trade_date,
                    field_name="trade_date",
                    expected_value=f"<= {date.today()}",
                    actual_value=rec.trade_date.isoformat(),
                    description=f"Future date detected: {rec.trade_date} > {date.today()}",
                    details_json=json.dumps({"trade_date": rec.trade_date.isoformat(), "today": date.today().isoformat()}),
                ))

        # Check for out-of-order dates
        for i in range(1, len(actual_dates_list)):
            if actual_dates_list[i] <= actual_dates_list[i - 1]:
                anomalies.append(ValidationAnomaly(
                    run_id=run_id,
                    anomaly_type="timestamp_mismatch",
                    severity="high",
                    symbol=symbol,
                    trade_date=actual_dates_list[i],
                    field_name="trade_date",
                    expected_value=f"> {actual_dates_list[i - 1]}",
                    actual_value=actual_dates_list[i].isoformat(),
                    description=f"Out-of-order dates: {actual_dates_list[i]} <= {actual_dates_list[i - 1]}",
                    details_json=json.dumps({
                        "current_date": actual_dates_list[i].isoformat(),
                        "previous_date": actual_dates_list[i - 1].isoformat(),
                    }),
                ))

        return anomalies

    # ============================================================
    # 7. DATA QUALITY SCORING
    # ============================================================

    def _compute_quality_score(
        self, records: list[DailyPrice], anomalies: list[ValidationAnomaly],
        date_from: date, date_to: date,
    ) -> dict[str, Any]:
        total_records = len(records)
        if total_records == 0:
            return {
                "overall_score": 0.0,
                "completeness": 0.0,
                "uniqueness": 0.0,
                "accuracy": 0.0,
                "consistency": 0.0,
                "timeliness": 0.0,
                "total_checks": 5,
                "checks_passed": 0,
                "checks_failed": 5,
                "rating": "poor",
            }

        expected_business_days = 0
        current = date_from
        while current <= date_to:
            if current.weekday() < 5:
                expected_business_days += 1
            current += timedelta(days=1)

        # Completeness: records vs expected business days
        completeness = min(1.0, total_records / max(expected_business_days, 1))
        missing_val_count = sum(1 for a in anomalies if a.anomaly_type == "missing_value")
        completeness_penalty = missing_val_count / max(total_records, 1) * 0.3
        completeness = max(0, completeness - completeness_penalty)

        # Uniqueness: dedup ratio
        unique_dates = len(set(r.trade_date for r in records))
        uniqueness = unique_dates / max(total_records, 1)

        # Accuracy: inverse of price/volume anomaly ratio
        price_vol_anomalies = sum(
            1 for a in anomalies if a.anomaly_type in ("price_anomaly", "volume_anomaly")
        )
        accuracy = max(0, 1.0 - price_vol_anomalies / max(total_records, 1) * 2)
        accuracy = min(1.0, accuracy)

        # Consistency: inverse of corp action mismatch + duplicate ratio
        consistency_issues = sum(
            1 for a in anomalies if a.anomaly_type in ("corp_action_mismatch", "duplicate_row")
        )
        consistency = max(0, 1.0 - consistency_issues / max(total_records, 1) * 2)
        consistency = min(1.0, consistency)

        # Timeliness: gaps + future dates
        timeliness_issues = sum(
            1 for a in anomalies if a.anomaly_type == "timestamp_mismatch"
        )
        timeliness = max(0, 1.0 - timeliness_issues / max(total_records, 1) * 1.5)
        timeliness = min(1.0, timeliness)

        # Overall: weighted average
        weights = {
            "completeness": 0.25,
            "uniqueness": 0.15,
            "accuracy": 0.25,
            "consistency": 0.20,
            "timeliness": 0.15,
        }
        overall = (
            completeness * weights["completeness"]
            + uniqueness * weights["uniqueness"]
            + accuracy * weights["accuracy"]
            + consistency * weights["consistency"]
            + timeliness * weights["timeliness"]
        )
        overall_score = round(overall * 100, 1)

        total_checks = 5
        passed = sum([
            1 if completeness > 0.8 else 0,
            1 if uniqueness > 0.95 else 0,
            1 if accuracy > 0.8 else 0,
            1 if consistency > 0.8 else 0,
            1 if timeliness > 0.8 else 0,
        ])
        failed = total_checks - passed

        if overall_score >= 90:
            rating = "excellent"
        elif overall_score >= 75:
            rating = "good"
        elif overall_score >= 50:
            rating = "fair"
        else:
            rating = "poor"

        return {
            "overall_score": overall_score,
            "completeness": round(completeness * 100, 1),
            "uniqueness": round(uniqueness * 100, 1),
            "accuracy": round(accuracy * 100, 1),
            "consistency": round(consistency * 100, 1),
            "timeliness": round(timeliness * 100, 1),
            "total_checks": total_checks,
            "checks_passed": passed,
            "checks_failed": failed,
            "rating": rating,
        }

    # ============================================================
    # QUERY METHODS
    # ============================================================

    async def get_validation_run(self, run_id: int) -> ValidationRun | None:
        r = await self.session.execute(
            select(ValidationRun).where(ValidationRun.id == run_id)
        )
        return r.scalar_one_or_none()

    async def list_validation_runs(
        self, symbol: str | None = None, status: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[ValidationRun]:
        stmt = select(ValidationRun).order_by(ValidationRun.started_at.desc())
        if symbol:
            stmt = stmt.where(ValidationRun.symbol == symbol.upper())
        if status:
            stmt = stmt.where(ValidationRun.status == status)
        stmt = stmt.offset(offset).limit(limit)
        r = await self.session.execute(stmt)
        return list(r.scalars().all())

    async def get_anomalies(
        self, run_id: int | None = None, anomaly_type: str | None = None,
        severity: str | None = None, symbol: str | None = None,
        limit: int = 100, offset: int = 0,
    ) -> list[ValidationAnomaly]:
        stmt = select(ValidationAnomaly).order_by(ValidationAnomaly.created_at.desc())
        if run_id is not None:
            stmt = stmt.where(ValidationAnomaly.run_id == run_id)
        if anomaly_type:
            stmt = stmt.where(ValidationAnomaly.anomaly_type == anomaly_type)
        if severity:
            stmt = stmt.where(ValidationAnomaly.severity == severity)
        if symbol:
            stmt = stmt.where(ValidationAnomaly.symbol == symbol.upper())
        stmt = stmt.offset(offset).limit(limit)
        r = await self.session.execute(stmt)
        return list(r.scalars().all())

    async def get_anomaly_stats(self) -> dict[str, Any]:
        r = await self.session.execute(
            select(
                ValidationAnomaly.anomaly_type,
                ValidationAnomaly.severity,
                func.count(ValidationAnomaly.id),
            ).group_by(ValidationAnomaly.anomaly_type, ValidationAnomaly.severity)
        )
        rows = r.all()
        stats: dict[str, dict[str, int]] = {}
        for atype, severity, count in rows:
            if atype not in stats:
                stats[atype] = {}
            stats[atype][severity] = count
        return stats

    async def get_quality_scores(
        self, symbol: str | None = None, limit: int = 50, offset: int = 0,
    ) -> list[DataQualityScore]:
        stmt = select(DataQualityScore).order_by(DataQualityScore.score_date.desc())
        if symbol:
            stmt = stmt.where(DataQualityScore.symbol == symbol.upper())
        stmt = stmt.offset(offset).limit(limit)
        r = await self.session.execute(stmt)
        return list(r.scalars().all())

    async def get_quality_stats(self) -> dict[str, Any]:
        r = await self.session.execute(
            select(
                func.avg(DataQualityScore.overall_score),
                func.min(DataQualityScore.overall_score),
                func.max(DataQualityScore.overall_score),
                func.count(DataQualityScore.id),
            )
        )
        avg, mn, mx, cnt = r.one()
        r2 = await self.session.execute(
            select(DataQualityScore.rating, func.count(DataQualityScore.id))
            .group_by(DataQualityScore.rating)
        )
        by_rating = {rating: count for rating, count in r2.all()}
        return {
            "average_score": round(avg, 1) if avg else None,
            "min_score": round(mn, 1) if mn else None,
            "max_score": round(mx, 1) if mx else None,
            "total_scores": cnt,
            "by_rating": by_rating,
        }

    async def clear_anomalies(self, older_than_days: int = 30) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        r = await self.session.execute(
            select(ValidationRun.id).where(ValidationRun.created_at <= cutoff)
        )
        old_run_ids = [row[0] for row in r.all()]
        if not old_run_ids:
            return 0
        deleted = 0
        r1 = await self.session.execute(
            delete(ValidationAnomaly).where(ValidationAnomaly.run_id.in_(old_run_ids))
        )
        deleted += r1.rowcount
        r2 = await self.session.execute(
            delete(DataQualityScore).where(DataQualityScore.run_id.in_(old_run_ids))
        )
        deleted += r2.rowcount or 0
        r3 = await self.session.execute(
            delete(ValidationRun).where(ValidationRun.id.in_(old_run_ids))
        )
        await self.session.flush()
        return deleted + (r3.rowcount or 0)
