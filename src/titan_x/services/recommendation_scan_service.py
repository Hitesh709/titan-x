"""Fast, selective full-market recommendation scanner.

Pipeline:
  full NSE/BSE universe -> batched live market data -> full technical gate
  -> >=95 shortlist -> unchanged deep AI recommendation engine.

Performance is improved by batching market-data requests instead of issuing one
HTTP request per symbol. Strategy thresholds, indicators, data-quality gates,
and the six-pillar deep engine are deliberately unchanged.
"""
from __future__ import annotations

import asyncio
import json
import random
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from titan_x.infrastructure.market_data_providers import MarketDataPoint, StooqProvider
from titan_x.models.company import Company
from titan_x.models.market_breadth import MarketBreadth
from titan_x.models.recommendation import Recommendation
from titan_x.models.sector import SectorPerformance
from titan_x.services.ai_recommendation_engine import AIRecommendationEngine, bars_from_records
from titan_x.services.recommendation_service import RecommendationService
from titan_x.services.technical_strength_engine import score_technical_strength

logger = structlog.get_logger(__name__)

FAST_GATE_SCORE = 95.0
DEFAULT_BATCH_SIZE = 100
DEFAULT_CONCURRENCY = 16
SOURCE = "yahoo-batch-live"
RECOMMENDATION_TYPE = "LIVE_SCAN"

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
    return {"trade_date": p.trade_date, "open": p.open, "high": p.high, "low": p.low, "close": p.close, "volume": p.volume}


def _parse_spark_result(symbol: str, response: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse Yahoo's multi-symbol Spark response without accepting partial rows."""
    timestamps = response.get("timestamp") or []
    indicators = response.get("indicators") or {}
    quote = (indicators.get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    rows: list[dict[str, Any]] = []
    for i, ts in enumerate(timestamps):
        close = closes[i] if i < len(closes) else None
        if close is None:
            continue
        try:
            d = datetime.fromtimestamp(ts, tz=datetime.now().astimezone().tzinfo).date()
            rows.append({
                "trade_date": d,
                "open": float(opens[i]) if i < len(opens) and opens[i] is not None else float(close),
                "high": float(highs[i]) if i < len(highs) and highs[i] is not None else float(close),
                "low": float(lows[i]) if i < len(lows) and lows[i] is not None else float(close),
                "close": float(close),
                "volume": int(volumes[i]) if i < len(volumes) and volumes[i] else 0,
            })
        except (TypeError, ValueError, OverflowError):
            continue
    return rows


class RecommendationScanService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.engine = AIRecommendationEngine()

    async def get_active_symbols(self, limit: int | None = None) -> list[str]:
        stmt = select(Company.symbol, Company.exchange).where(Company.status == "active").order_by(Company.symbol)
        result = await self.session.execute(stmt)
        # Keep one logical symbol while preferring NSE when the same company is
        # represented on both exchanges. BSE-only companies remain included.
        exchange_rank = {"NSE": 0, "BSE": 1}
        chosen: dict[str, str] = {}
        for symbol, exchange in result.all():
            if not symbol:
                continue
            sym = str(symbol).upper()
            ex = str(exchange or "NSE").upper()
            if sym not in chosen or exchange_rank.get(ex, 9) < exchange_rank.get(chosen[sym], 9):
                chosen[sym] = ex
        symbols = sorted(chosen)
        return symbols[:limit] if limit else symbols

    async def _exchange_map(self, symbols: list[str]) -> dict[str, str]:
        if not symbols:
            return {}
        result = await self.session.execute(
            select(Company.symbol, Company.exchange).where(Company.symbol.in_(symbols))
        )
        rank = {"NSE": 0, "BSE": 1}
        chosen: dict[str, str] = {}
        for symbol, exchange in result.all():
            sym = str(symbol).upper()
            ex = str(exchange or "NSE").upper()
            if sym not in chosen or rank.get(ex, 9) < rank.get(chosen[sym], 9):
                chosen[sym] = ex
        return chosen

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

    @staticmethod
    def _yahoo_symbol(symbol: str, exchange: str) -> str:
        if "." in symbol:
            return symbol
        return f"{symbol}.BO" if exchange.upper() == "BSE" else f"{symbol}.NS"

    async def _fetch_yahoo_batch(
        self,
        client: httpx.AsyncClient,
        symbols: list[str],
        exchange_map: dict[str, str],
        start: date,
    ) -> dict[str, list[dict[str, Any]]]:
        """Fetch many instruments in one Yahoo Spark request.

        This removes the previous 1-symbol=1-request bottleneck. The scanner
        still validates every symbol independently and never substitutes
        synthetic prices for a failed live-data response.
        """
        yahoo_symbols = [self._yahoo_symbol(s, exchange_map.get(s, "NSE")) for s in symbols]
        params = {
            "symbols": ",".join(yahoo_symbols),
            "range": "1y",
            "interval": "1d",
            "period1": str(int(datetime.combine(start, datetime.min.time()).replace(tzinfo=timezone.utc).timestamp())),
        }
        urls = (
            "https://query1.finance.yahoo.com/v7/finance/spark",
            "https://query2.finance.yahoo.com/v7/finance/spark",
        )
        last_error: Exception | None = None
        for url in urls:
            try:
                response = await client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
                results = ((payload.get("spark") or {}).get("result") or [])
                parsed: dict[str, list[dict[str, Any]]] = {}
                for item in results:
                    provider_symbol = str(item.get("symbol") or "").upper()
                    response_rows = item.get("response") or []
                    if not response_rows:
                        continue
                    rows = _parse_spark_result(provider_symbol, response_rows[0])
                    base = provider_symbol.rsplit(".", 1)[0]
                    if rows:
                        parsed[base] = rows
                return parsed
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        raise last_error or RuntimeError("Yahoo batch request failed")

    async def scan_all(
        self,
        max_age_minutes: int | None = 60,
        concurrency: int = DEFAULT_CONCURRENCY,
        chunk_size: int = DEFAULT_BATCH_SIZE,
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

    async def _scan_locked(self, max_age_minutes: int | None, concurrency: int, chunk_size: int, limit: int | None) -> dict[str, Any]:
        from sqlalchemy import func
        from titan_x.core.seed_demo import COMPANIES

        total_start = time.perf_counter()
        active_result = await self.session.execute(select(func.count(Company.id)).where(Company.status == "active"))
        active_count = active_result.scalar() or 0
        if active_count == 0:
            now = datetime.now(timezone.utc)
            import hashlib
            for entry in COMPANIES:
                symbol, name, sector, _industry, exchange, *_ = entry
                if exchange in ("NSE", "BSE") and symbol:
                    self.session.add(Company(
                        symbol=symbol, company_name=name,
                        isin="IN" + hashlib.md5(symbol.encode()).hexdigest()[:10].upper(),
                        sector=sector, exchange=exchange, status="active",
                        created_at=now, updated_at=now,
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
        exchange_map = await self._exchange_map(all_symbols)
        sector_ctx = await self._build_sector_context()
        breadth_ctx = await self._build_breadth_context()
        symbols = sorted(await self._stale_symbols(max_age_minutes, all_symbols))
        sector_by_symbol: dict[str, str | None] = {}
        if symbols:
            res = await self.session.execute(select(Company.symbol, Company.sector).where(Company.symbol.in_(symbols)))
            sector_by_symbol = {str(sym).upper(): sec for sym, sec in res.all()}

        processed = fast_passed = deep_scanned = stored = insufficient = no_trade = failed = 0
        errors: list[str] = []
        batch_failed = 0
        data_start = time.perf_counter()
        stooq = StooqProvider()
        timeout = httpx.Timeout(10.0, connect=5.0)
        limits = httpx.Limits(max_connections=max(16, min(int(concurrency), 32)), max_keepalive_connections=32)
        client = httpx.AsyncClient(timeout=timeout, limits=limits, headers={"User-Agent": "Titan-X/2.0"})
        market_data: dict[str, tuple[list[dict[str, Any]], str]] = {}

        async def one_batch(batch: list[str]) -> None:
            nonlocal batch_failed
            try:
                rows = await self._fetch_yahoo_batch(client, batch, exchange_map, date.today() - timedelta(days=400))
                for symbol in batch:
                    points = rows.get(symbol)
                    if points and len(points) >= 30:
                        market_data[symbol] = (points, SOURCE)
                    else:
                        # Live fallback for a missing symbol only; no synthetic
                        # data is ever accepted by the production recommendation scan.
                        try:
                            points2 = await stooq.get_historical_prices(symbol, interval="1d", start=date.today() - timedelta(days=400))
                            if points2 and len(points2) >= 30:
                                market_data[symbol] = ([_point_to_dict(p) for p in points2], "stooq-live")
                            else:
                                errors.append(f"{symbol}: insufficient live history")
                        except Exception as exc:  # noqa: BLE001
                            errors.append(f"{symbol}: live data unavailable ({exc})")
            except Exception as exc:  # noqa: BLE001
                batch_failed += 1
                errors.append(f"batch {batch[0]}..{batch[-1]}: {exc}")
                # A failed batch is retried as smaller individual live requests
                # rather than weakening the quality gate with synthetic data.
                fallback_sem = asyncio.Semaphore(8)
                async def fallback(symbol: str) -> None:
                    async with fallback_sem:
                        try:
                            points = await stooq.get_historical_prices(symbol, interval="1d", start=date.today() - timedelta(days=400))
                            if points and len(points) >= 30:
                                market_data[symbol] = ([_point_to_dict(p) for p in points], "stooq-live")
                        except Exception:
                            return
                await asyncio.gather(*(fallback(s) for s in batch))

        try:
            batches = [symbols[i:i + max(1, chunk_size)] for i in range(0, len(symbols), max(1, chunk_size))]
            batch_sem = asyncio.Semaphore(max(1, min(int(concurrency), 16)))
            async def guarded(batch: list[str]) -> None:
                async with batch_sem:
                    await one_batch(batch)
            await asyncio.gather(*(guarded(b) for b in batches))
            data_seconds = time.perf_counter() - data_start

            # Full fast technical calculation for every valid live-data stock.
            # Run both modes concurrently; the 95 gate remains unchanged.
            fast_start = time.perf_counter()
            fast_results: dict[str, tuple[Any, Any, list[dict[str, Any]], str]] = {}
            calc_sem = asyncio.Semaphore(max(1, min(int(concurrency) * 2, 32)))
            async def calculate(symbol: str) -> None:
                async with calc_sem:
                    points, source = market_data[symbol]
                    bars = bars_from_records(points)
                    if len(bars) < 30:
                        return
                    intraday, delivery = await asyncio.gather(
                        asyncio.to_thread(score_technical_strength, bars, mode="intraday"),
                        asyncio.to_thread(score_technical_strength, bars, mode="delivery"),
                    )
                    fast_results[symbol] = (intraday, delivery, points, source)
            await asyncio.gather(*(calculate(s) for s in market_data))
            fast_seconds = time.perf_counter() - fast_start

            processed = len(symbols)
            insufficient = len(symbols) - len(fast_results)
            svc = RecommendationService(self.session)
            deep_start = time.perf_counter()
            for symbol, (intraday, delivery, points, source) in fast_results.items():
                try:
                    fast_score = max(intraday.score, delivery.score)
                    if fast_score < FAST_GATE_SCORE:
                        no_trade += 1
                        continue
                    fast_passed += 1
                    deep_scanned += 1
                    bars = bars_from_records(points)
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
            deep_seconds = time.perf_counter() - deep_start
        except Exception as exc:  # noqa: BLE001
            await self.session.rollback()
            _scan_state["last_error"] = str(exc)
            logger.exception("scan_loop_failed", error=str(exc))
            raise
        finally:
            await stooq.close()
            await client.aclose()

        result = {
            "started": True,
            "universe": len(all_symbols),
            "used_fallback_universe": used_fallback,
            "scanned": processed,
            "live_data_symbols": len(market_data),
            "fast_gate": FAST_GATE_SCORE,
            "fast_passed": fast_passed,
            "deep_scanned": deep_scanned,
            "stored": stored,
            "insufficient_data": insufficient,
            "no_trade": no_trade,
            "failed": failed,
            "batch_failed": batch_failed,
            "skipped_fresh": len(all_symbols) - len(symbols),
            "first_error": errors[0] if errors else None,
            "timing_seconds": {
                "market_data": round(data_seconds, 3),
                "fast_technical": round(fast_seconds, 3),
                "deep_scan": round(deep_seconds, 3),
                "total": round(time.perf_counter() - total_start, 3),
            },
            "data_quality": {
                "synthetic_data_used": False,
                "live_only_fast_gate": True,
                "provider": "Yahoo Spark batch + Stooq per-symbol fallback",
            },
        }
        _scan_state["last"] = {**result, "finished_at": datetime.now(timezone.utc).isoformat()}
        if errors:
            _scan_state["last_error"] = errors[0]
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
            model_version_label="live-scan-v3-batched-fast95",
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


async def run_background_scan(session_factory: async_sessionmaker, max_age_minutes: int | None = 60, limit: int | None = None) -> dict[str, Any]:
    async with session_factory() as session:
        service = RecommendationScanService(session)
        return await service.scan_all(max_age_minutes=max_age_minutes, limit=limit)
