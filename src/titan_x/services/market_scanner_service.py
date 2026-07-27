"""Market scanner service.

Scans all symbols for breakouts, breakdowns, EMA crossovers,
RSI, MACD, ADX, ATR, and volume signals. Generates composite
scores and rankings.
"""
from __future__ import annotations

import json
import math
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from titan_x.models.company import Company
from titan_x.models.market_scanner import MarketScanResult
from titan_x.models.price import DailyPrice
from titan_x.models.technical import TechnicalIndicator

logger = structlog.get_logger(__name__)

LOOKBACK_DAYS = 120
SIGNAL_STRENGTH_MAX = 100


class MarketScannerService:
    """Scan all symbols for technical signals and rank them."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ═════════════════════════════════════════════════════════════════════
    # Main scan entry points
    # ═════════════════════════════════════════════════════════════════════

    async def scan_all(self) -> list[MarketScanResult]:
        companies = await self._get_active_symbols()
        results: list[MarketScanResult] = []
        today = date.today()

        for company in companies:
            try:
                r = await self._scan_symbol(company.symbol, today)
                results.append(r)
            except Exception as exc:
                logger.error("scan_failed", symbol=company.symbol, error=str(exc))

        await self.session.commit()

        for r in results:
            await self.session.refresh(r)
        return results

    async def scan_symbol(
        self, symbol: str, scan_date: date | None = None,
    ) -> MarketScanResult:
        today = scan_date or date.today()
        result = await self._scan_symbol(symbol.upper(), today)
        await self.session.commit()
        await self.session.refresh(result)
        return result

    async def _scan_symbol(
        self, symbol: str, scan_date: date,
    ) -> MarketScanResult:
        prices = await self._get_prices(symbol, 90)
        lookback = await self._get_prices(symbol, LOOKBACK_DAYS)

        signals: dict[str, Any] = {}
        scores: dict[str, float] = {}
        signal_values: dict[str, str | None] = {}

        for detector in [
            self._detect_breakout,
            self._detect_breakdown,
            self._detect_ema_cross,
            self._detect_rsi,
            self._detect_macd,
            self._detect_adx,
            self._detect_atr,
            self._detect_volume,
        ]:
            try:
                result = await detector(symbol, prices, lookback)
                signals[result["name"]] = result
                scores[result["name"]] = result["score"]
                signal_values[result["name"]] = result.get("signal")
            except Exception as exc:
                logger.warning("detector_failed", symbol=symbol, detector=detector.__name__, error=str(exc))

        breakout = scores.get("breakout", 0.0)
        breakdown = scores.get("breakdown", 0.0)
        bull_scores = [
            scores.get("ema_cross", 0.0),
            scores.get("rsi", 0.0),
            scores.get("macd", 0.0),
            scores.get("adx", 0.0),
            scores.get("volume", 0.0),
        ]
        bear_scores = [
            (SIGNAL_STRENGTH_MAX - scores.get("ema_cross", 0.0)),
            (SIGNAL_STRENGTH_MAX - scores.get("rsi", 0.0)),
            (SIGNAL_STRENGTH_MAX - scores.get("macd", 0.0)),
            SIGNAL_STRENGTH_MAX - scores.get("adx", 0.0) if scores.get("adx", 0.0) > 50 else 0,
            scores.get("volume", 0.0),
        ]
        composite = (breakout + (SIGNAL_STRENGTH_MAX - breakdown) + sum(bull_scores) + sum(bear_scores)) / 10
        composite = max(0.0, min(SIGNAL_STRENGTH_MAX, composite))

        result = MarketScanResult(
            symbol=symbol,
            scan_date=scan_date,
            composite_score=round(composite, 2),
            breakout_score=round(breakout, 2),
            breakdown_score=round(breakdown, 2),
            ema_cross_score=round(scores.get("ema_cross", 0.0), 2),
            rsi_score=round(scores.get("rsi", 0.0), 2),
            macd_score=round(scores.get("macd", 0.0), 2),
            adx_score=round(scores.get("adx", 0.0), 2),
            atr_score=round(scores.get("atr", 0.0), 2),
            volume_score=round(scores.get("volume", 0.0), 2),
            breakout_signal=signal_values.get("breakout"),
            breakdown_signal=signal_values.get("breakdown"),
            ema_cross_signal=signal_values.get("ema_cross"),
            rsi_signal=signal_values.get("rsi"),
            macd_signal=signal_values.get("macd"),
            adx_signal=signal_values.get("adx"),
            atr_signal=signal_values.get("atr"),
            volume_signal=signal_values.get("volume"),
            signals_json=json.dumps(signals, default=str),
        )
        self.session.add(result)
        await self.session.flush()
        return result

    # ═════════════════════════════════════════════════════════════════════
    # Signal detectors
    # ═════════════════════════════════════════════════════════════════════

    async def _detect_breakout(
        self, symbol: str, prices: list[DailyPrice], lookback: list[DailyPrice],
    ) -> dict[str, Any]:
        if len(prices) < 2 or len(lookback) < 25:
            return _neutral("breakout")
        latest = prices[-1]
        prev = prices[-2]
        recent_highs = [p.high for p in lookback[-21:-1] if p.high]
        resistance = max(recent_highs) if recent_highs else latest.close
        if resistance == 0:
            return _neutral("breakout")

        close = latest.close or 0
        pct_above = (close - resistance) / resistance * 100
        if pct_above > 0 and close > (prev.close or 0):
            strength = min(SIGNAL_STRENGTH_MAX, int(pct_above * 10))
            vol_signal = await self._check_volume_confirmation(symbol, prices)
            strength = min(SIGNAL_STRENGTH_MAX, int(strength * (1.2 if vol_signal else 0.8)))
            return {
                "name": "breakout", "signal": "bullish",
                "score": strength,
                "description": f"Price broke above resistance at {resistance:.2f} (+{pct_above:.1f}%)",
                "resistance": round(resistance, 2),
                "pct_above": round(pct_above, 2),
            }
        return _neutral("breakout")

    async def _detect_breakdown(
        self, symbol: str, prices: list[DailyPrice], lookback: list[DailyPrice],
    ) -> dict[str, Any]:
        if len(prices) < 2 or len(lookback) < 25:
            return _neutral("breakdown")
        latest = prices[-1]
        prev = prices[-2]
        recent_lows = [p.low for p in lookback[-21:-1] if p.low]
        support = min(recent_lows) if recent_lows else latest.close
        if support == 0:
            return _neutral("breakdown")

        close = latest.close or 0
        pct_below = (support - close) / support * 100
        if pct_below > 0 and close < (prev.close or 0):
            strength = min(SIGNAL_STRENGTH_MAX, int(pct_below * 10))
            return {
                "name": "breakdown", "signal": "bearish",
                "score": strength,
                "description": f"Price broke below support at {support:.2f} (-{pct_below:.1f}%)",
                "support": round(support, 2),
                "pct_below": round(pct_below, 2),
            }
        return _neutral("breakdown")

    async def _detect_ema_cross(
        self, symbol: str, prices: list[DailyPrice], lookback: list[DailyPrice],
    ) -> dict[str, Any]:
        closes = [p.close for p in prices if p.close]
        if len(closes) < 27:
            return _neutral("ema_cross")
        ema_fast = self._compute_ema(closes, 12)
        ema_slow = self._compute_ema(closes, 26)
        ef = ema_fast[-1]
        es = ema_slow[-1]
        ef_prev = ema_fast[-2] if len(ema_fast) >= 2 else ef
        es_prev = ema_slow[-2] if len(ema_slow) >= 2 else es
        if ef is None or es is None:
            return _neutral("ema_cross")

        gap_pct = abs(ef - es) / es * 100 if es != 0 else 0
        prev_gap = (ef_prev or 0) - (es_prev or 0)

        if ef > es and (ef_prev or 0) <= (es_prev or 0):
            strength = min(SIGNAL_STRENGTH_MAX, int(gap_pct * 20))
            return {
                "name": "ema_cross", "signal": "bullish",
                "score": strength,
                "description": f"EMA-12 crossed above EMA-26 (gap: {gap_pct:.2f}%)",
                "ema_fast": round(ef, 2), "ema_slow": round(es, 2),
                "gap_pct": round(gap_pct, 2),
            }
        if ef < es and (ef_prev or 0) >= (es_prev or 0):
            strength = min(SIGNAL_STRENGTH_MAX, int(gap_pct * 20))
            return {
                "name": "ema_cross", "signal": "bearish",
                "score": strength,
                "description": f"EMA-12 crossed below EMA-26 (gap: {gap_pct:.2f}%)",
                "ema_fast": round(ef, 2), "ema_slow": round(es, 2),
                "gap_pct": round(gap_pct, 2),
            }
        if ef > es:
            return {
                "name": "ema_cross", "signal": "bullish",
                "score": min(SIGNAL_STRENGTH_MAX, int(gap_pct * 10) + 10),
                "description": f"EMA-12 above EMA-26 (bullish alignment, gap: {gap_pct:.2f}%)",
                "ema_fast": round(ef, 2), "ema_slow": round(es, 2),
                "gap_pct": round(gap_pct, 2),
            }
        return {
            "name": "ema_cross", "signal": "bearish",
            "score": min(SIGNAL_STRENGTH_MAX, int(gap_pct * 10) + 10),
            "description": f"EMA-12 below EMA-26 (bearish alignment, gap: {gap_pct:.2f}%)",
            "ema_fast": round(ef, 2), "ema_slow": round(es, 2),
            "gap_pct": round(gap_pct, 2),
        }

    async def _detect_rsi(
        self, symbol: str, prices: list[DailyPrice], lookback: list[DailyPrice],
    ) -> dict[str, Any]:
        rsi_values = await self._get_indicator_values(symbol, "RSI", period=14)
        if not rsi_values:
            return _neutral("rsi")
        rsi = rsi_values[-1]
        if rsi is None:
            return _neutral("rsi")

        if rsi < 30:
            strength = int((30 - rsi) * 3.33)
            return {
                "name": "rsi", "signal": "bullish",
                "score": min(SIGNAL_STRENGTH_MAX, strength),
                "description": f"RSI oversold at {rsi:.1f}",
                "rsi": round(rsi, 2),
            }
        if rsi > 70:
            strength = int((rsi - 70) * 3.33)
            return {
                "name": "rsi", "signal": "bearish",
                "score": min(SIGNAL_STRENGTH_MAX, strength),
                "description": f"RSI overbought at {rsi:.1f}",
                "rsi": round(rsi, 2),
            }
        if rsi < 45:
            return {
                "name": "rsi", "signal": "bullish",
                "score": int((45 - rsi) * 2),
                "description": f"RSI bullish at {rsi:.1f}",
                "rsi": round(rsi, 2),
            }
        if rsi > 55:
            return {
                "name": "rsi", "signal": "bearish",
                "score": int((rsi - 55) * 2),
                "description": f"RSI bearish at {rsi:.1f}",
                "rsi": round(rsi, 2),
            }
        return {
            "name": "rsi", "signal": "neutral",
            "score": 50,
            "description": f"RSI neutral at {rsi:.1f}",
            "rsi": round(rsi, 2),
        }

    async def _detect_macd(
        self, symbol: str, prices: list[DailyPrice], lookback: list[DailyPrice],
    ) -> dict[str, Any]:
        macd_line_vals = await self._get_indicator_values(symbol, "MACD", period=12)
        signal_vals = await self._get_indicator_values(symbol, "MACD", period=9, field="value_secondary")
        hist_vals = await self._get_indicator_values(symbol, "MACD", period=9, field="value_tertiary")

        latest_vals = await self._get_indicator_values(symbol, "MACD", period=12)
        if not latest_vals:
            return _neutral("macd")

        macd_row = await self._get_last_technical(symbol, "MACD")
        if not macd_row or macd_row.value is None:
            return _neutral("macd")

        macd = macd_row.value
        signal = macd_row.value_secondary
        hist = macd_row.value_tertiary

        if macd is None:
            return _neutral("macd")

        if hist is not None and abs(hist) < 0.001:
            if macd > (signal or 0):
                return {
                    "name": "macd", "signal": "bullish",
                    "score": 70,
                    "description": f"MACD bullish at zero crossover (MACD: {macd:.2f})",
                    "macd": round(macd, 4), "signal": round(signal or 0, 4),
                    "histogram": round(hist, 4),
                }
            return {
                "name": "macd", "signal": "bearish",
                "score": 70,
                "description": f"MACD bearish at zero crossover (MACD: {macd:.2f})",
                "macd": round(macd, 4), "signal": round(signal or 0, 4),
                "histogram": round(hist, 4),
            }

        if hist is not None and hist > 0:
            strength = min(SIGNAL_STRENGTH_MAX, int(abs(macd) * 100))
            return {
                "name": "macd", "signal": "bullish",
                "score": strength,
                "description": f"MACD bullish, histogram rising (MACD: {macd:.2f})",
                "macd": round(macd, 4), "signal": round(signal or 0, 4),
                "histogram": round(hist, 4),
            }
        if hist is not None and hist < 0:
            strength = min(SIGNAL_STRENGTH_MAX, int(abs(macd) * 100))
            return {
                "name": "macd", "signal": "bearish",
                "score": strength,
                "description": f"MACD bearish, histogram falling (MACD: {macd:.2f})",
                "macd": round(macd, 4), "signal": round(signal or 0, 4),
                "histogram": round(hist, 4),
            }
        return _neutral("macd")

    async def _detect_adx(
        self, symbol: str, prices: list[DailyPrice], lookback: list[DailyPrice],
    ) -> dict[str, Any]:
        adx_values = await self._get_indicator_values(symbol, "ADX", period=14)
        if not adx_values:
            return _neutral("adx")

        di_plus = await self._get_indicator_values(symbol, "ADX", period=14, field="value_secondary")
        di_minus = await self._get_indicator_values(symbol, "ADX", period=14, field="value_tertiary")

        row = await self._get_last_technical(symbol, "ADX")
        if not row or row.value is None:
            return _neutral("adx")

        adx = row.value
        dp = row.value_secondary or 0
        dm = row.value_tertiary or 0

        if adx >= 25:
            strength = min(SIGNAL_STRENGTH_MAX, int((adx - 25) * 2))
            direction = "bullish" if dp > dm else "bearish"
            return {
                "name": "adx", "signal": direction,
                "score": strength,
                "description": f"Strong trend (ADX: {adx:.1f}, DI+: {dp:.1f}, DI-: {dm:.1f})",
                "adx": round(adx, 2), "di_plus": round(dp, 2),
                "di_minus": round(dm, 2),
            }
        if adx < 20:
            strength = min(SIGNAL_STRENGTH_MAX, int((20 - adx) * 3))
            return {
                "name": "adx", "signal": "neutral",
                "score": strength,
                "description": f"Weak trend, possible consolidation (ADX: {adx:.1f})",
                "adx": round(adx, 2), "di_plus": round(dp, 2),
                "di_minus": round(dm, 2),
            }
        direction = "bullish" if dp > dm else "bearish"
        return {
            "name": "adx", "signal": direction,
            "score": int(adx * 2),
            "description": f"Moderate trend (ADX: {adx:.1f}, DI+: {dp:.1f}, DI-: {dm:.1f})",
            "adx": round(adx, 2), "di_plus": round(dp, 2),
            "di_minus": round(dm, 2),
        }

    async def _detect_atr(
        self, symbol: str, prices: list[DailyPrice], lookback: list[DailyPrice],
    ) -> dict[str, Any]:
        atr_values = await self._get_indicator_values(symbol, "ATR", period=14)
        if len(atr_values) < 15:
            return _neutral("atr")

        atr_now = atr_values[-1]
        atr_prev_avg = sum(a for a in atr_values[-15:-1] if a is not None) / 14 if atr_values[-15:-1] else 0
        if atr_now is None or atr_prev_avg == 0:
            return _neutral("atr")

        atr_ratio = atr_now / atr_prev_avg

        if atr_ratio > 1.3:
            strength = min(SIGNAL_STRENGTH_MAX, int((atr_ratio - 1.3) * 100))
            return {
                "name": "atr", "signal": "bullish",
                "score": strength,
                "description": f"Volatility expansion (ATR ratio: {atr_ratio:.2f})",
                "atr": round(atr_now, 4), "atr_ratio": round(atr_ratio, 2),
            }
        if atr_ratio < 0.7:
            strength = min(SIGNAL_STRENGTH_MAX, int((0.7 - atr_ratio) * 100))
            return {
                "name": "atr", "signal": "neutral",
                "score": strength,
                "description": f"Volatility contraction (ATR ratio: {atr_ratio:.2f})",
                "atr": round(atr_now, 4), "atr_ratio": round(atr_ratio, 2),
            }
        return {
            "name": "atr", "signal": "neutral",
            "score": 50,
            "description": f"Normal volatility (ATR: {atr_now:.4f})",
            "atr": round(atr_now, 4), "atr_ratio": round(atr_ratio, 2),
        }

    async def _detect_volume(
        self, symbol: str, prices: list[DailyPrice], lookback: list[DailyPrice],
    ) -> dict[str, Any]:
        volumes = [p.volume for p in prices[-22:] if p.volume]
        if len(volumes) < 2:
            return _neutral("volume")

        latest_vol = volumes[-1]
        avg_vol = sum(volumes[:-1]) / len(volumes[:-1]) if len(volumes) > 1 else latest_vol
        if avg_vol == 0:
            return _neutral("volume")

        vol_ratio = latest_vol / avg_vol
        close_up = prices[-1].close and prices[-2].close and prices[-1].close > prices[-2].close

        if vol_ratio > 1.5 and close_up:
            strength = min(SIGNAL_STRENGTH_MAX, int((vol_ratio - 1.5) * 50))
            return {
                "name": "volume", "signal": "bullish",
                "score": strength,
                "description": f"Volume spike with price up ({vol_ratio:.1f}x avg)",
                "volume_ratio": round(vol_ratio, 2),
                "latest_volume": int(latest_vol),
                "avg_volume": int(avg_vol),
            }
        if vol_ratio > 1.5 and not close_up:
            strength = min(SIGNAL_STRENGTH_MAX, int((vol_ratio - 1.5) * 50))
            return {
                "name": "volume", "signal": "bearish",
                "score": strength,
                "description": f"Volume spike with price down ({vol_ratio:.1f}x avg)",
                "volume_ratio": round(vol_ratio, 2),
                "latest_volume": int(latest_vol),
                "avg_volume": int(avg_vol),
            }
        if vol_ratio < 0.5:
            return {
                "name": "volume", "signal": "neutral",
                "score": int((0.5 - vol_ratio) * 50),
                "description": f"Low volume ({vol_ratio:.1f}x avg)",
                "volume_ratio": round(vol_ratio, 2),
                "latest_volume": int(latest_vol),
                "avg_volume": int(avg_vol),
            }
        return {
            "name": "volume", "signal": "bullish" if close_up else "bearish",
            "score": int(vol_ratio * 30),
            "description": f"Normal volume ({vol_ratio:.1f}x avg)",
            "volume_ratio": round(vol_ratio, 2),
            "latest_volume": int(latest_vol),
            "avg_volume": int(avg_vol),
        }

    # ═════════════════════════════════════════════════════════════════════
    # Query helpers
    # ═════════════════════════════════════════════════════════════════════

    async def get_rankings(
        self, scan_date: date | None = None,
        min_score: float = 0,
        limit: int = 100,
    ) -> list[MarketScanResult]:
        d = scan_date or date.today()
        stmt = (
            select(MarketScanResult)
            .where(
                MarketScanResult.scan_date == d,
                MarketScanResult.composite_score >= min_score,
            )
            .order_by(MarketScanResult.composite_score.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_scan(
        self, symbol: str,
    ) -> MarketScanResult | None:
        result = await self.session.execute(
            select(MarketScanResult)
            .where(MarketScanResult.symbol == symbol.upper())
            .order_by(MarketScanResult.scan_date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_scan_history(
        self, symbol: str, limit: int = 30,
    ) -> list[MarketScanResult]:
        result = await self.session.execute(
            select(MarketScanResult)
            .where(MarketScanResult.symbol == symbol.upper())
            .order_by(MarketScanResult.scan_date.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_top_by_signal(
        self, signal_field: str, scan_date: date | None = None,
        limit: int = 20,
    ) -> list[MarketScanResult]:
        d = scan_date or date.today()
        score_col = getattr(MarketScanResult, f"{signal_field}_score", None)
        if score_col is None:
            return []
        sig_col = getattr(MarketScanResult, f"{signal_field}_signal", None)
        stmt = select(MarketScanResult).where(
            MarketScanResult.scan_date == d,
        )
        if sig_col is not None:
            stmt = stmt.where(sig_col.in_(["bullish", "bearish"]))
        stmt = stmt.order_by(score_col.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_scan_summary(
        self, scan_date: date | None = None,
    ) -> dict[str, Any]:
        d = scan_date or date.today()
        total = await self.session.execute(
            select(func.count(MarketScanResult.id)).where(
                MarketScanResult.scan_date == d,
            )
        )
        avg = await self.session.execute(
            select(func.avg(MarketScanResult.composite_score)).where(
                MarketScanResult.scan_date == d,
            )
        )
        bullish = await self.session.execute(
            select(func.count(MarketScanResult.id)).where(
                MarketScanResult.scan_date == d,
                MarketScanResult.composite_score >= 60,
            )
        )
        bearish_count = await self.session.execute(
            select(func.count(MarketScanResult.id)).where(
                MarketScanResult.scan_date == d,
                MarketScanResult.composite_score <= 40,
            )
        )
        return {
            "scan_date": d.isoformat(),
            "total_scanned": total.scalar() or 0,
            "avg_composite_score": round(float(avg.scalar() or 0), 2),
            "bullish_count": bullish.scalar() or 0,
            "bearish_count": bearish_count.scalar() or 0,
        }

    async def get_all_scan_dates(self) -> list[date]:
        result = await self.session.execute(
            select(MarketScanResult.scan_date)
            .distinct()
            .order_by(MarketScanResult.scan_date.desc())
        )
        return [r[0] for r in result.all()]

    # ═════════════════════════════════════════════════════════════════════
    # Internal helpers
    # ═════════════════════════════════════════════════════════════════════

    async def _get_active_symbols(self) -> list[Company]:
        result = await self.session.execute(
            select(Company).where(Company.status == "active")
        )
        return list(result.scalars().all())

    async def _get_prices(
        self, symbol: str, days: int,
    ) -> list[DailyPrice]:
        cutoff = date.today() - timedelta(days=days)
        result = await self.session.execute(
            select(DailyPrice)
            .where(
                DailyPrice.symbol == symbol,
                DailyPrice.trade_date >= cutoff,
                DailyPrice.close.isnot(None),
            )
            .order_by(DailyPrice.trade_date)
        )
        return list(result.scalars().all())

    async def _get_indicator_values(
        self, symbol: str, indicator: str,
        period: int = 14, field: str = "value",
    ) -> list[float | None]:
        vals: list[float | None] = []
        result = await self.session.execute(
            select(TechnicalIndicator)
            .where(
                TechnicalIndicator.symbol == symbol,
                TechnicalIndicator.indicator == indicator,
                TechnicalIndicator.period == period,
            )
            .order_by(TechnicalIndicator.trade_date)
            .limit(10)
        )
        for row in result.scalars().all():
            vals.append(getattr(row, field, None))
        return vals

    async def _get_last_technical(
        self, symbol: str, indicator: str,
    ) -> TechnicalIndicator | None:
        result = await self.session.execute(
            select(TechnicalIndicator)
            .where(
                TechnicalIndicator.symbol == symbol,
                TechnicalIndicator.indicator == indicator,
            )
            .order_by(TechnicalIndicator.trade_date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _check_volume_confirmation(
        self, symbol: str, prices: list[DailyPrice],
    ) -> bool:
        volumes = [p.volume for p in prices[-6:] if p.volume]
        if len(volumes) < 2:
            return False
        latest = volumes[-1]
        avg_prev = sum(volumes[:-1]) / len(volumes[:-1])
        return avg_prev > 0 and latest > avg_prev * 1.2

    @staticmethod
    def _compute_ema(values: list[float], period: int) -> list[float | None]:
        if len(values) < period:
            return [None] * len(values)
        multiplier = 2.0 / (period + 1)
        result: list[float | None] = [None] * (period - 1)
        ema = sum(values[:period]) / period
        result.append(ema)
        for v in values[period:]:
            ema = (v - ema) * multiplier + ema
            result.append(ema)
        return result


def _neutral(name: str) -> dict[str, Any]:
    return {
        "name": name, "signal": "neutral",
        "score": 0,
        "description": "No signal detected",
    }
