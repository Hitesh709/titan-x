"""Fast, selective full-market recommendation scanner.

Pipeline:
  market universe -> live price history -> FAST technical gate -> deep AI scan

The fast gate is intentionally strict: only stocks with an intraday OR delivery
technical-strength score >= 95 proceed to the expensive six-pillar AI engine.
The deep strategy itself is unchanged; this module only prevents unnecessary
work on weak candidates and parallelizes market-data acquisition.
"""
from __future__ import annotations

import asyncio
import json
import random
from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from titan_x.infrastructure.market_data_providers import MarketDataPoint, StooqProvider, YahooFinanceProvider
from titan_x.models.company import Company
from titan_x.models.market_breadth import MarketBreadth
from titan_x.models.recommendation import Recommendation
from titan_x.models.sector import SectorPerformance
from titan_x.services.ai_recommendation_engine import AIRecommendationEngine, bars_from_records
from titan_x.services.recommendation_service import RecommendationService
from titan_x.services.technical_strength_engine import score_technical_strength

logger = structlog.get_logger(__name__)

# Higher concurrency is safe here because the expensive deep engine is only run
# after the 95+ gate. The semaphore still protects upstream providers.
DEFAULT_CONCURRENCY = 15
DEFAULT_CHUNK_SIZE = 100
SOURCE = "yahoo-live"
RECOMMENDATION_TYPE = "LIVE_SCAN"
DEMO_SOURCE = "demo-synthetic"
FAST_GATE_SCORE = 95.0

FALLBACK_NSE_SYMBOLS = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "HDFC", "WIPRO",
    "BHARTIARTL", "SBIN", "ITC", "LT", "KOTAKBANK", "AXISBANK", "MARUTI",
    "SUNPHARMA", "TATAMOTORS", "TATASTEEL", "ONGC", "NTPC", "POWERGRID",
    "TITAN", "BAJFINANCE", "ASIANPAINT", "NESTLEIND", "HCLTECH", "TECHM",
    "ULTRACEMCO", "ADANIPORTS", "M&M", "JSWSTEEL",
]

_scan_lock: asyncio.Lock | None = None
_scan_state: dict[str, Any] = {
    "running": False,
    "last": None,
    "last_error": None,
    "last_universe": None,
}


def _get_scan_lock() -> asyncio.Lock:
    global _scan_lock
    if _scan_lock is None:
        _scan_lock = asyncio.Lock()
    return _scan_lock


def get_scan_status() -> dict[str, Any]:
    return dict(_scan_state)


def _point_to_dict(p: MarketDataPoint | dict) -> dict[str, Any]:
    if isinstance(p, dict):
        return {k: p.get(k) for k in ("trade_date", "open", "high", "low", "close", "volume")}
    return {
        "trade_date": p.trade_date,
        "open": p.open,
        "high": p.high,
        "low": p.low,
        "close": p.close,
        "volume": p.volume,
    }


def _synthetic_bars(symbol: str, days: int = 500) -> list[dict[str, Any]]:
    """Deterministic demo fallback only; never presented as live data."""
    rng = random.Random(hash(symbol) & 0xFFFFFFFF)
    base = 100.0 + (hash(symbol) % 500)
    drift = (rng.random() - 0.5) * 0.002
    bars: list[dict[str, Any]] = []
    today = date.today()
    for i in range(days):
        d = today - timedelta(days=days - 1 - i)
        if d.weekday() >= 5:
            continue
        base *= 1 + drift + (rng.random() - 0.5) * 0.02
        high = base * (1 + abs(rng.random() * 0.015))
        low = base * (1 - abs(rng.random() * 0.015))
        open_ = base * (1 + (rng.random() - 0.5) * 0.01)
        bars.append({
            "trade_date": d,
            "open": round(open_, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(base, 2),
            "volume": int(1_000_000 + rng.random() * 5_000_000),
        })
    return bars


class RecommendationScanService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.engine = AIRecommendationEngine()

    async def get_active_symbols(self, limit: int | None = None) -> list[str]:
        # Scan every active exchange represented in the company master. The
        # universe loader can therefore grow from NSE-only to NSE+BSE without
        # changing the recommendation pipeline.
        stmt = select(Company.symbol).where(Company.status == "active").order_by(Company.symbol)
        result = await self.session.execute(stmt)
        symbols = list(dict.fromkeys(r[0] for r in result.all() if r[0]))
        return symbols[:limit] if limit else symbols

    async def _build_sector_context(self) -> dict[str, dict[str, float]]:
        result = await self.session.execute(
            select(SectorPerformance.sector, SectorPerformance.momentum_score, SectorPerformance.relative_strength)
            .order_by(SectorPerformance.sector, SectorPerformance.as_of_date.desc())
        )
        ctx: dict[str, dict[str, float]] = {}
        for sector, momentum, strength in result.all():
            if sector not in ctx:
                ctx[sector] = {
                    "momentum_score": momentum if momentum is not None else 50.0,
                    "relative_strength": strength if strength is not None else 50.0,
                }
        return ctx

    async def _build_breadth_context(self) -> dict[str, Any] | None:
        result = await self.session.execute(select(MarketBreadth).order_by(MarketBreadth.trade_date.desc()).limit(1))
        b = result.scalar_one_or_none()
        if b is None:
            return None
        adv_ratio = b.advancing / b.declining if b.declining and b.declining > 0 else 1.0
        return {"index_strength_score": b.index_strength_score or 50.0, "adv_decl_ratio": adv_ratio}

    async def _stale_symbols(self, max_age_minutes: int | None, symbols: list[str]) -> set[str]:
        if max_age_minutes is None or max_age_minutes <= 0:
            return set(symbols)
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=max_age_minutes)
        result = await self.session.execute(
            select(Recommendation.symbol).where(
                Recommendation.symbol.in_(symbols),
                Recommendation.status == "active",
                Recommendation.generated_at >= cutoff,
            )
        )
        fresh = {r[0] for r in result.all()}
        return {s for s in symbols if s not in fresh}

    async def scan_all(
        self,
        max_age_minutes: int | None = 60,
        concurrency: int = DEFAULT_CONCURRENCY,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        limit: int | None = None,
    ) -> dict[str, Any]:
        lock = _get_scan_lock()
        if lock.locked():
            return {"started": False, "reason": "A scan is already running"}
        async with lock:
            _scan_state["running"] = True
            _scan_state["last_error"] = None
            try:
                return await self._scan_locked(max_age_minutes, concurrency, chunk_size, limit)
            except Exception as exc:  # noqa: BLE001
                _scan_state["last_error"] = str(exc)
                logger.exception("scan_failed", error=str(exc))
                raise
            finally:
                _scan_state["running"] = False

    async def _scan_locked(
        self,
        max_age_minutes: int | None,
        concurrency: int,
        chunk_size: int,
        limit: int | None,
    ) -> dict[str, Any]:
        # Keep the existing universe bootstrap behaviour. Do not block on
        # enrichment when the database already has an active universe.
        from sqlalchemy import func
        from titan_x.core.seed_demo import COMPANIES

        active_result = await self.session.execute(select(func.count(Company.id)).where(Company.status == "active"))
        active_count = active_result.scalar() or 0
        if active_count == 0:
            now = datetime.now(timezone.utc)
            import hashlib
            for entry in COMPANIES:
                symbol, name, sector, _industry, exchange, *_ = entry
                if exchange in ("NSE", "BSE") and symbol:
                    self.session.add(Company(
                        symbol=symbol,
                        company_name=name,
                        isin="IN" + hashlib.md5(symbol.encode()).hexdigest()[:10].upper(),
                        sector=sector,
                        exchange=exchange,
                        status="active",
                        created_at=now,
                        updated_at=now,
                    ))
            await self.session.commit()
            try:
                from titan_x.services.nse_universe_service import NSEUniverseService
                result = await NSEUniverseService(self.session).load_universe()
                await self.session.commit()
                _scan_state["last_universe"] = result
            except Exception as exc:  # noqa: BLE001
                logger.warning("universe_enrichment_failed", error=str(exc))

        all_symbols = await self.get_active_symbols(limit=limit)
        used_fallback = False
        if not all_symbols:
            all_symbols = list(FALLBACK_NSE_SYMBOLS)
            used_fallback = True

        sector_ctx = await self._build_sector_context()
        breadth_ctx = await self._build_breadth_context()
        symbols = sorted(await self._stale_symbols(max_age_minutes, all_symbols))

        sector_by_symbol: dict[str, str | None] = {}
        if symbols:
            res = await self.session.execute(select(Company.symbol, Company.sector).where(Company.symbol.in_(symbols)))
            sector_by_symbol = {sym: sec for sym, sec in res.all()}

        processed = fast_passed = deep_scanned = stored = insufficient = no_trade = failed = 0
        errors: list[str] = []
        scan_error: Exception | None = None
        stooq = StooqProvider()
        yahoo = YahooFinanceProvider()

        # Provider calls are the I/O bottleneck. Run them concurrently, then
        # keep the CPU-heavy deep engine strictly behind the 95+ technical gate.
        sem = asyncio.Semaphore(max(1, min(int(concurrency), 32)))

        async def fetch(symbol: str) -> tuple[list[dict[str, Any]], str] | None:
            async with sem:
                try:
                    points = await yahoo.get_historical_prices(symbol, interval="1d", start=date.today() - timedelta(days=400))
                    source = SOURCE
                except Exception:
                    try:
                        points = await stooq.get_historical_prices(symbol, interval="1d", start=date.today() - timedelta(days=400))
                        source = "stooq-live"
                    except Exception:
                        points = _synthetic_bars(symbol)
                        source = DEMO_SOURCE
                if not points:
                    errors.append(f"{symbol}: empty result")
                    return None
                return [_point_to_dict(p) for p in points], source

        try:
            svc = RecommendationService(self.session)
            for start in range(0, len(symbols), max(1, chunk_size)):
                chunk = symbols[start:start + max(1, chunk_size)]
                results = await asyncio.gather(*(fetch(s) for s in chunk), return_exceptions=False)

                for symbol, result in zip(chunk, results):
                    processed += 1
                    try:
                        if result is None:
                            failed += 1
                            continue
                        points, source = result
                        bars = bars_from_records(points)
                        if len(bars) < 30:
                            insufficient += 1
                            continue

                        # FAST STAGE: use the existing transparent technical
                        # pillar engine only. No fundamentals/news/similarity/
                        # risk/deep-AI work happens for weak candidates.
                        intraday = score_technical_strength(bars, mode="intraday")
                        delivery = score_technical_strength(bars, mode="delivery")
                        fast_score = max(intraday.score, delivery.score)
                        if fast_score < FAST_GATE_SCORE:
                            no_trade += 1
                            continue
                        fast_passed += 1

                        # DEEP STAGE: unchanged six-pillar recommendation engine.
                        deep_scanned += 1
                        rec = self.engine.build(
                            symbol,
                            bars,
                            sector_ctx=sector_ctx.get(sector_by_symbol.get(symbol) or ""),
                            breadth_ctx=breadth_ctx,
                        )
                        rec["data_points"] = len(points)
                        rec["fast_technical_gate"] = {
                            "threshold": FAST_GATE_SCORE,
                            "intraday_score": intraday.score,
                            "intraday_direction": intraday.direction,
                            "delivery_score": delivery.score,
                            "delivery_direction": delivery.direction,
                            "selected_score": fast_score,
                        }
                        if rec.get("insufficient_data"):
                            insufficient += 1
                            continue
                        if rec.get("no_trade"):
                            no_trade += 1
                            continue
                        await self._store(rec, svc, source=source)
                        stored += 1
                    except Exception as exc:  # noqa: BLE001
                        failed += 1
                        logger.warning("scan_symbol_failed", symbol=symbol, error=str(exc))

                await self.session.commit()
        except Exception as exc:  # noqa: BLE001
            scan_error = exc
            logger.exception("scan_loop_failed", error=str(exc))
            await self.session.rollback()
        finally:
            await stooq.close()
            await yahoo.close()

        result = {
            "started": True,
            "universe": len(all_symbols),
            "used_fallback_universe": used_fallback,
            "scanned": processed,
            "fast_gate": FAST_GATE_SCORE,
            "fast_passed": fast_passed,
            "deep_scanned": deep_scanned,
            "stored": stored,
            "insufficient_data": insufficient,
            "no_trade": no_trade,
            "failed": failed,
            "skipped_fresh": len(all_symbols) - len(symbols),
            "first_error": errors[0] if errors else None,
        }
        _scan_state["last"] = {**result, "finished_at": datetime.now(timezone.utc).isoformat()}
        if errors:
            _scan_state["last_error"] = errors[0]
        if scan_error is not None:
            _scan_state["last_error"] = str(scan_error)
            raise scan_error
        return result

    async def _store(self, rec: dict[str, Any], svc: RecommendationService, source: str = SOURCE) -> None:
        await self.session.execute(delete(Recommendation).where(Recommendation.symbol == rec["symbol"]))
        signal = rec["signal"]
        direction = "BUY" if signal in ("strong_buy", "buy") else "SELL" if signal in ("strong_sell", "sell") else "HOLD"
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        evidence = rec["evidence"]
        caution = rec["caution"]
        reasoning_lines = [f"{signal.upper()} recommendation for {rec['symbol']}"]
        if evidence:
            reasoning_lines += ["", "SUPPORTING EVIDENCE", *[f"  - {e}" for e in evidence]]
        if caution:
            reasoning_lines += ["", "REASONS FOR CAUTION", *[f"  - {c}" for c in caution]]
        metadata = {
            "signal": signal,
            "as_of_date": rec["as_of_date"],
            "data_points": rec.get("data_points", 0),
            "evidence": evidence,
            "caution": caution,
            "returns": rec["returns"],
            "indicators": rec["indicators"],
            "fast_technical_gate": rec.get("fast_technical_gate"),
        }
        await svc.create_recommendation(
            symbol=rec["symbol"], direction=direction, signal=signal,
            confidence=rec["confidence"], price_target=rec["price_target"],
            current_price=rec["current_price"], timeframe=f"{rec['holding_period_days']} days",
            reasoning="\n".join(reasoning_lines), recommendation_type=RECOMMENDATION_TYPE,
            score=rec["score"], risk_level=rec["risk_level"],
            predicted_return_pct=rec["expected_return_pct"], source=source,
            metadata_json=json.dumps(metadata), status="active",
            expires_at=now + timedelta(days=1), inputs_json=json.dumps(rec["factors"]),
            model_version_label="live-scan-v2-fast95",
        )


async def run_universe_load(session_factory: async_sessionmaker) -> dict[str, Any]:
    from titan_x.services.nse_universe_service import NSEUniverseService
    async with session_factory() as session:
        service = NSEUniverseService(session)
        try:
            result = await service.load_universe()
            await session.commit()
            _scan_state["last_universe"] = {"loaded": True, **result}
            return {"loaded": True, **result}
        except Exception as exc:  # noqa: BLE001
            logger.warning("universe_load_failed", error=str(exc))
            await session.rollback()
            _scan_state["last_universe"] = {"loaded": False, "error": str(exc)}
            return {"loaded": False, "error": str(exc)}


async def run_background_scan(
    session_factory: async_sessionmaker,
    max_age_minutes: int | None = 60,
    limit: int | None = None,
) -> dict[str, Any]:
    async with session_factory() as session:
        service = RecommendationScanService(session)
        return await service.scan_all(max_age_minutes=max_age_minutes, limit=limit)
