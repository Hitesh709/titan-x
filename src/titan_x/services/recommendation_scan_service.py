from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from titan_x.models.company import Company
from titan_x.models.market_breadth import MarketBreadth
from titan_x.models.recommendation import Recommendation
from titan_x.models.sector import SectorPerformance
from titan_x.infrastructure.market_data_providers import YahooFinanceProvider
from titan_x.services.ai_recommendation_engine import AIRecommendationEngine, bars_from_records
from titan_x.services.nse_universe_service import NSEUniverseService
from titan_x.services.recommendation_service import RecommendationService
from titan_x.services.technical_strength_engine import score_technical_strength

logger = structlog.get_logger(__name__)

FAST_GATE_SCORE = 70.0
SOURCE = "yahoo"
RECOMMENDATION_TYPE = "LIVE_SCAN"
SCAN_SEGMENTS = 10
SYMBOL_CONCURRENCY_PER_SEGMENT = 5
BATCH_PER_SEGMENT = 20

_scan_lock = asyncio.Lock()
_scan_state = {
    "running": False,
    "last": None,
    "last_error": None,
    "last_universe": None,
    "segment_progress": {},
}


def get_scan_status():
    return dict(_scan_state)


class RecommendationScanService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.engine = AIRecommendationEngine()

    async def get_active_symbols(self, limit=None):
        rows = (
            await self.session.execute(
                select(Company.symbol, Company.exchange)
                .where(Company.status == "active")
                .order_by(Company.symbol, Company.exchange)
            )
        ).all()
        # Keep the exchange in the identity.  NSE and BSE can have the same
        # ticker but are different Yahoo instruments (.NS vs .BO).
        seen = set()
        out = []
        for symbol, exchange in rows:
            s = str(symbol).upper().strip() if symbol else ""
            ex = str(exchange or "NSE").upper().strip()
            if not s or ex not in {"NSE", "BSE"}:
                continue
            key = (s, ex)
            if key in seen:
                continue
            seen.add(key)
            out.append((s, ex))
        return out[:limit] if limit else out

    async def _sector_ctx(self):
        rows = (
            await self.session.execute(
                select(
                    SectorPerformance.sector,
                    SectorPerformance.momentum_score,
                    SectorPerformance.relative_strength,
                ).order_by(
                    SectorPerformance.sector,
                    SectorPerformance.as_of_date.desc(),
                )
            )
        ).all()
        out = {}
        for sec, momentum, relative in rows:
            if sec not in out:
                out[sec] = {
                    "momentum_score": momentum if momentum is not None else 50.0,
                    "relative_strength": relative if relative is not None else 50.0,
                }
        return out

    async def _breadth_ctx(self):
        breadth = (
            await self.session.execute(
                select(MarketBreadth)
                .order_by(MarketBreadth.trade_date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not breadth:
            return None
        return {
            "index_strength_score": breadth.index_strength_score or 50.0,
            "adv_decl_ratio": (
                breadth.advancing / breadth.declining
                if breadth.declining
                else 1.0
            ),
        }

    async def _stale(self, instruments, max_age):
        if max_age is None or max_age <= 0:
            return set(instruments)
        symbols = [s for s, _ in instruments]
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            minutes=max_age
        )
        rows = (
            await self.session.execute(
                select(Recommendation.symbol).where(
                    Recommendation.symbol.in_(symbols),
                    Recommendation.status == "active",
                    Recommendation.generated_at >= cutoff,
                )
            )
        ).all()
        fresh = {r[0] for r in rows}
        return {item for item in instruments if item[0] not in fresh}

    async def scan_all(self, max_age_minutes=60, concurrency=8, chunk_size=50, limit=None):
        if _scan_lock.locked():
            return {"started": False, "reason": "A scan is already running"}

        async with _scan_lock:
            _scan_state.update(
                running=True,
                last_error=None,
                segment_progress={str(i): "pending" for i in range(SCAN_SEGMENTS)},
            )
            try:
                return await self._scan(max_age_minutes, limit)
            except Exception as exc:
                _scan_state["last_error"] = str(exc)
                logger.exception("scan_failed", error=str(exc))
                raise
            finally:
                _scan_state["running"] = False

    async def _scan(self, max_age_minutes, limit):
        instruments = await self.get_active_symbols(limit)
        stale = sorted(await self._stale(instruments, max_age_minutes))
        sector = await self._sector_ctx()
        breadth = await self._breadth_ctx()

        # IMPORTANT: do not build a market={symbol: 400 bars} dictionary for
        # the entire universe.  Fetch, score, persist, and release small
        # batches.  Ten segment workers provide parallelism without allowing
        # the whole 2,300+ stock universe to accumulate in RAM.
        segments = [stale[i::SCAN_SEGMENTS] for i in range(SCAN_SEGMENTS)]
        counters = {
            "scanned": 0,
            "live_data_symbols": 0,
            "fast_passed": 0,
            "stored": 0,
            "insufficient_data": 0,
            "no_trade": 0,
            "failed": 0,
            "batch_failed": 0,
        }
        errors: list[str] = []
        counter_lock = asyncio.Lock()

        async def run_segment(segment_id: int, segment):
            provider = YahooFinanceProvider()
            try:
                _scan_state["segment_progress"][str(segment_id)] = "running"
                for start in range(0, len(segment), BATCH_PER_SEGMENT):
                    batch = segment[start : start + BATCH_PER_SEGMENT]
                    await self._process_batch(
                        segment_id,
                        batch,
                        provider,
                        sector,
                        breadth,
                        counters,
                        errors,
                        counter_lock,
                    )
                    # Explicitly yield so completed batch objects can be
                    # collected before another batch is scheduled.
                    await asyncio.sleep(0)
                _scan_state["segment_progress"][str(segment_id)] = "done"
            except Exception as exc:
                _scan_state["segment_progress"][str(segment_id)] = "failed"
                async with counter_lock:
                    counters["batch_failed"] += 1
                    errors.append(f"segment {segment_id}: {exc}")
                logger.exception("scan_segment_failed", segment=segment_id, error=str(exc))
            finally:
                await provider.close()

        await asyncio.gather(
            *(run_segment(segment_id, segment) for segment_id, segment in enumerate(segments))
        )

        await self.session.commit()
        result = {
            "started": True,
            "universe": len(instruments),
            "scanned": counters["scanned"],
            "live_data_symbols": counters["live_data_symbols"],
            "fast_gate": FAST_GATE_SCORE,
            "fast_passed": counters["fast_passed"],
            "deep_scanned": counters["fast_passed"],
            "stored": counters["stored"],
            "insufficient_data": counters["insufficient_data"],
            "no_trade": counters["no_trade"],
            "failed": counters["failed"],
            "batch_failed": counters["batch_failed"],
            "skipped_fresh": len(instruments) - len(stale),
            "first_error": errors[0] if errors else None,
            "scan_segments": SCAN_SEGMENTS,
            "batch_per_segment": BATCH_PER_SEGMENT,
            "symbol_concurrency_per_segment": SYMBOL_CONCURRENCY_PER_SEGMENT,
            "data_quality": {
                "synthetic_data_used": False,
                "live_only_fast_gate": True,
                "provider": "Yahoo Finance",
            },
        }
        _scan_state["last"] = {
            **result,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        return result

    async def _process_batch(
        self,
        segment_id,
        batch,
        provider,
        sector,
        breadth,
        counters,
        errors,
        counter_lock,
    ):
        sem = asyncio.Semaphore(SYMBOL_CONCURRENCY_PER_SEGMENT)

        async def fetch_one(instrument):
            symbol, exchange = instrument
            async with sem:
                try:
                    # YahooFinanceProvider maps NSE/BSE identities to .NS/.BO.
                    points = await provider.get_historical_prices(
                        symbol,
                        interval="1d",
                        start=date.today() - timedelta(days=400),
                        synthetic_ok=False,
                    )
                    return instrument, points, None
                except Exception as exc:
                    return instrument, None, f"{symbol} ({exchange}): Yahoo data unavailable ({exc})"

        fetched = await asyncio.gather(*(fetch_one(item) for item in batch))
        svc = RecommendationService(self.session)

        for instrument, points, error in fetched:
            symbol, exchange = instrument
            async with counter_lock:
                counters["scanned"] += 1

            if error:
                async with counter_lock:
                    counters["failed"] += 1
                    if len(errors) < 20:
                        errors.append(error)
                continue

            if not points or len(points) < 30:
                async with counter_lock:
                    counters["insufficient_data"] += 1
                continue

            async with counter_lock:
                counters["live_data_symbols"] += 1

            try:
                # bars is scoped to one instrument and released at the end of
                # this iteration; no full-market DataFrame cache is retained.
                bars = bars_from_records(points)
                intraday, delivery = await asyncio.gather(
                    asyncio.to_thread(score_technical_strength, bars, mode="intraday"),
                    asyncio.to_thread(score_technical_strength, bars, mode="delivery"),
                )
                selected_score = max(intraday.score, delivery.score)

                if selected_score < FAST_GATE_SCORE:
                    async with counter_lock:
                        counters["no_trade"] += 1
                    continue

                async with counter_lock:
                    counters["fast_passed"] += 1

                company = (
                    await self.session.execute(
                        select(Company.sector)
                        .where(
                            Company.symbol == symbol,
                            Company.exchange == exchange,
                            Company.status == "active",
                        )
                        .limit(1)
                    )
                ).scalar_one_or_none()
                sector_name = company or ""

                rec = self.engine.build(
                    symbol,
                    bars,
                    sector_ctx=sector.get(sector_name),
                    breadth_ctx=breadth,
                )
                rec["exchange"] = exchange
                rec["data_points"] = len(points)
                rec["fast_technical_gate"] = {
                    "threshold": FAST_GATE_SCORE,
                    "intraday_score": intraday.score,
                    "delivery_score": delivery.score,
                    "selected_score": selected_score,
                }

                if rec.get("insufficient_data") or rec.get("no_trade"):
                    async with counter_lock:
                        counters["no_trade"] += 1
                    continue

                await self._store(rec, svc, exchange=exchange)
                async with counter_lock:
                    counters["stored"] += 1
            except Exception as exc:
                async with counter_lock:
                    counters["failed"] += 1
                    if len(errors) < 20:
                        errors.append(f"{symbol} ({exchange}): {exc}")
                logger.warning("scan_symbol_failed", symbol=symbol, exchange=exchange, error=str(exc))

    async def _store(self, rec, svc, exchange="NSE"):
        # Do not delete another exchange's recommendation merely because the
        # ticker text is identical.
        await self.session.execute(
            delete(Recommendation).where(
                Recommendation.symbol == rec["symbol"],
                Recommendation.recommendation_type == RECOMMENDATION_TYPE,
                Recommendation.source == SOURCE,
            )
        )

        signal = rec["signal"]
        direction = (
            "BUY" if signal in ("strong_buy", "buy")
            else "SELL" if signal in ("strong_sell", "sell")
            else "HOLD"
        )
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        metadata = {
            "signal": signal,
            "exchange": exchange,
            "as_of_date": rec.get("as_of_date"),
            "data_points": rec.get("data_points", 0),
            "evidence": rec.get("evidence"),
            "caution": rec.get("caution"),
            "returns": rec.get("returns"),
            "indicators": rec.get("indicators"),
            "fast_technical_gate": rec.get("fast_technical_gate"),
        }
        await svc.create_recommendation(
            symbol=rec["symbol"],
            direction=direction,
            signal=signal,
            confidence=rec["confidence"],
            price_target=rec["price_target"],
            current_price=rec["current_price"],
            timeframe=f"{rec['holding_period_days']} days",
            reasoning=f"{signal.upper()} recommendation for {rec['symbol']} ({exchange})",
            recommendation_type=RECOMMENDATION_TYPE,
            score=rec["score"],
            risk_level=rec["risk_level"],
            predicted_return_pct=rec["expected_return_pct"],
            source=SOURCE,
            metadata_json=json.dumps(metadata),
            status="active",
            expires_at=now + timedelta(days=1),
            inputs_json=json.dumps(rec["factors"]),
            model_version_label="yahoo-live-v1",
        )


async def run_universe_load(session_factory: async_sessionmaker) -> dict[str, Any]:
    async with session_factory() as session:
        result = await NSEUniverseService(session).load_universe()
        await session.commit()
        result = {"loaded": True, **result}
        _scan_state["last_universe"] = result
        logger.info("full_nse_universe_loaded", **result)
        return result


async def run_background_scan(
    session_factory: async_sessionmaker,
    max_age_minutes=60,
    limit=None,
) -> dict[str, Any]:
    async with session_factory() as session:
        return await RecommendationScanService(session).scan_all(
            max_age_minutes=max_age_minutes,
            limit=limit,
        )
