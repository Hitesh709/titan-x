import json
import math
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.chart_pattern import ChartPattern, SupportResistance
from titan_x.models.company import Company
from titan_x.models.price import DailyPrice

logger = structlog.get_logger(__name__)

PEAK_TROUGH_WINDOW = 5
DOUBLE_TOP_BOTTOM_TOLERANCE = 0.02
CUP_MIN_BARS = 20
CUP_MAX_BARS = 200
FLAG_MIN_BARS = 5
FLAG_MAX_BARS = 20
TRIANGLE_MIN_BARS = 15
SR_CLUSTER_PERCENT = 0.01
MIN_SR_TOUCHES = 2
LOOKBACK_DAYS = 365

PATTERN_TYPES = [
    "double_top", "double_bottom", "cup_handle",
    "bull_flag", "bear_flag",
    "symmetrical_triangle", "ascending_triangle", "descending_triangle",
]


class PatternRecognitionEngine:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._pattern_repo = BaseRepository(session, ChartPattern)
        self._sr_repo = BaseRepository(session, SupportResistance)

    async def _get_active_symbols(self) -> list[str]:
        result = await self._session.execute(
            select(Company.symbol).where(Company.status == "active"),
        )
        return [r[0] for r in result.all()]

    async def _get_prices(
        self, symbol: str, end_date: date, lookback: int = LOOKBACK_DAYS,
    ) -> list[dict[str, Any]]:
        start_date = end_date - timedelta(days=lookback)
        result = await self._session.execute(
            select(DailyPrice)
            .where(
                DailyPrice.symbol == symbol,
                DailyPrice.trade_date.between(start_date, end_date),
            )
            .order_by(DailyPrice.trade_date)
        )
        return [
            {
                "trade_date": r.trade_date,
                "open": r.open, "high": r.high,
                "low": r.low, "close": r.close,
                "volume": r.volume,
            }
            for r in result.scalars().all()
        ]

    def _find_peaks(
        self, prices: list[dict[str, Any]], window: int = PEAK_TROUGH_WINDOW,
    ) -> list[int]:
        peaks: list[int] = []
        n = len(prices)
        if n < 2 * window + 1:
            return peaks
        for i in range(window, n - window):
            is_peak = True
            for j in range(1, window + 1):
                if prices[i]["high"] <= prices[i - j]["high"] or prices[i]["high"] <= prices[i + j]["high"]:
                    is_peak = False
                    break
            if is_peak:
                peaks.append(i)
        return peaks

    def _find_troughs(
        self, prices: list[dict[str, Any]], window: int = PEAK_TROUGH_WINDOW,
    ) -> list[int]:
        troughs: list[int] = []
        n = len(prices)
        if n < 2 * window + 1:
            return troughs
        for i in range(window, n - window):
            is_trough = True
            for j in range(1, window + 1):
                if prices[i]["low"] >= prices[i - j]["low"] or prices[i]["low"] >= prices[i + j]["low"]:
                    is_trough = False
                    break
            if is_trough:
                troughs.append(i)
        return troughs

    def _linear_regression_slope(
        self, prices: list[dict[str, Any]], indices: list[int], use_high: bool = True,
    ) -> float:
        n = len(indices)
        if n < 2:
            return 0.0
        xs = list(range(n))
        ys = [prices[i]["high"] if use_high else prices[i]["low"] for i in indices]
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        den = sum((x - mean_x) ** 2 for x in xs)
        return num / den if den != 0 else 0.0

    async def detect_double_top(
        self, symbol: str, end_date: date | None = None,
    ) -> list[dict[str, Any]]:
        if end_date is None:
            end_date = date.today()
        prices = await self._get_prices(symbol, end_date)
        if len(prices) < 30:
            return []
        peaks = self._find_peaks(prices, window=PEAK_TROUGH_WINDOW)
        if len(peaks) < 2:
            return []
        results: list[dict[str, Any]] = []
        for i in range(len(peaks) - 1):
            p1 = peaks[i]
            p2 = peaks[i + 1]
            peak1_price = prices[p1]["high"]
            peak2_price = prices[p2]["high"]
            price_diff = abs(peak1_price - peak2_price) / max(peak1_price, peak2_price)
            if price_diff > DOUBLE_TOP_BOTTOM_TOLERANCE:
                continue
            trough_idx = min(
                range(p1, p2 + 1),
                key=lambda j: prices[j]["low"],
            )
            neckline = prices[trough_idx]["low"]
            if peak1_price <= neckline or peak2_price <= neckline:
                continue
            confirmation = prices[p2]["close"] < neckline if p2 < len(prices) - 1 else False
            target = neckline - (max(peak1_price, peak2_price) - neckline)
            avg_price = (peak1_price + peak2_price) / 2
            depth_pct = (avg_price - neckline) / neckline * 100

            volume_ok = True
            if p1 < len(prices) and p2 < len(prices):
                vol1 = prices[p1]["volume"]
                vol2 = prices[p2]["volume"]
                volume_ok = vol2 < vol1 * 1.1

            confidence = self._score_double_pattern(
                symmetry=1.0 - price_diff / DOUBLE_TOP_BOTTOM_TOLERANCE,
                depth_pct=depth_pct,
                volume_ok=volume_ok,
                confirmed=confirmation,
                bar_distance=(p2 - p1),
            )

            results.append({
                "pattern_type": "double_top",
                "direction": "bearish",
                "start_date": prices[p1]["trade_date"].isoformat(),
                "end_date": prices[p2]["trade_date"].isoformat(),
                "entry_price": round(neckline, 2),
                "target_price": round(target, 2) if target > 0 else None,
                "stop_loss": round(avg_price * 1.02, 2),
                "confidence_score": round(confidence, 1),
                "pattern_data": {
                    "peak1_price": round(peak1_price, 2),
                    "peak1_date": prices[p1]["trade_date"].isoformat(),
                    "peak2_price": round(peak2_price, 2),
                    "peak2_date": prices[p2]["trade_date"].isoformat(),
                    "neckline_price": round(neckline, 2),
                    "target_price": round(target, 2) if target > 0 else None,
                    "depth_pct": round(depth_pct, 2),
                    "confirmed": confirmation,
                },
            })
        return results

    async def detect_double_bottom(
        self, symbol: str, end_date: date | None = None,
    ) -> list[dict[str, Any]]:
        if end_date is None:
            end_date = date.today()
        prices = await self._get_prices(symbol, end_date)
        if len(prices) < 30:
            return []
        troughs = self._find_troughs(prices, window=PEAK_TROUGH_WINDOW)
        if len(troughs) < 2:
            return []
        results: list[dict[str, Any]] = []
        for i in range(len(troughs) - 1):
            t1 = troughs[i]
            t2 = troughs[i + 1]
            trough1_price = prices[t1]["low"]
            trough2_price = prices[t2]["low"]
            price_diff = abs(trough1_price - trough2_price) / max(trough1_price, trough2_price)
            if price_diff > DOUBLE_TOP_BOTTOM_TOLERANCE:
                continue
            peak_idx = max(
                range(t1, t2 + 1),
                key=lambda j: prices[j]["high"],
            )
            neckline = prices[peak_idx]["high"]
            if trough1_price >= neckline or trough2_price >= neckline:
                continue
            confirmation = prices[t2]["close"] > neckline if t2 < len(prices) - 1 else False
            target = neckline + (neckline - min(trough1_price, trough2_price))
            avg_price = (trough1_price + trough2_price) / 2
            depth_pct = (neckline - avg_price) / avg_price * 100

            volume_ok = True
            if t1 < len(prices) and t2 < len(prices):
                vol1 = prices[t1]["volume"]
                vol2 = prices[t2]["volume"]
                volume_ok = vol2 > vol1 * 0.9

            confidence = self._score_double_pattern(
                symmetry=1.0 - price_diff / DOUBLE_TOP_BOTTOM_TOLERANCE,
                depth_pct=depth_pct,
                volume_ok=volume_ok,
                confirmed=confirmation,
                bar_distance=(t2 - t1),
            )

            results.append({
                "pattern_type": "double_bottom",
                "direction": "bullish",
                "start_date": prices[t1]["trade_date"].isoformat(),
                "end_date": prices[t2]["trade_date"].isoformat(),
                "entry_price": round(neckline, 2),
                "target_price": round(target, 2),
                "stop_loss": round(avg_price * 0.98, 2),
                "confidence_score": round(confidence, 1),
                "pattern_data": {
                    "trough1_price": round(trough1_price, 2),
                    "trough1_date": prices[t1]["trade_date"].isoformat(),
                    "trough2_price": round(trough2_price, 2),
                    "trough2_date": prices[t2]["trade_date"].isoformat(),
                    "neckline_price": round(neckline, 2),
                    "target_price": round(target, 2),
                    "depth_pct": round(depth_pct, 2),
                    "confirmed": confirmation,
                },
            })
        return results

    def _score_double_pattern(
        self, symmetry: float, depth_pct: float,
        volume_ok: bool, confirmed: bool, bar_distance: int,
    ) -> float:
        score = 50.0
        score += symmetry * 20
        if 5 <= depth_pct <= 30:
            score += 10
        elif depth_pct > 30:
            score += 5
        if volume_ok:
            score += 10
        if confirmed:
            score += 10
        if 10 <= bar_distance <= 60:
            score += 5
        elif bar_distance > 60:
            score += 2
        return max(0.0, min(100.0, score))

    async def detect_cup_handle(
        self, symbol: str, end_date: date | None = None,
    ) -> list[dict[str, Any]]:
        if end_date is None:
            end_date = date.today()
        prices = await self._get_prices(symbol, end_date, lookback=CUP_MAX_BARS + 30)
        if len(prices) < CUP_MIN_BARS:
            return []
        results: list[dict[str, Any]] = []
        for cup_end in range(CUP_MIN_BARS, len(prices)):
            cup_start = max(0, cup_end - CUP_MAX_BARS)
            for start in range(cup_start, cup_end - CUP_MIN_BARS + 1):
                left_peak = max(
                    range(start, start + (cup_end - start) // 3),
                    key=lambda j: prices[j]["high"],
                )
                right_peak_idx = min(
                    range(cup_end - (cup_end - start) // 3, cup_end + 1),
                    key=lambda j: abs(j - cup_end),
                )
                if right_peak_idx >= len(prices):
                    continue
                if right_peak_idx <= left_peak:
                    continue
                trough = min(
                    range(left_peak, right_peak_idx + 1),
                    key=lambda j: prices[j]["low"],
                )
                cup_high = max(prices[left_peak]["high"], prices[right_peak_idx]["high"])
                cup_low = prices[trough]["low"]
                cup_depth = (cup_high - cup_low) / cup_high * 100
                if cup_depth < 10 or cup_depth > 50:
                    continue
                right_recovery = (prices[right_peak_idx]["close"] - cup_low) / cup_low * 100
                if right_recovery < 50:
                    continue
                handle_end = cup_end + 15
                if handle_end >= len(prices):
                    handle_end = len(prices) - 1
                handle_high = max(
                    range(right_peak_idx, handle_end + 1),
                    key=lambda j: prices[j]["high"],
                )
                handle_low = min(
                    range(right_peak_idx, handle_end + 1),
                    key=lambda j: prices[j]["low"],
                )
                handle_depth = (
                    (prices[handle_high]["high"] - prices[handle_low]["low"])
                    / prices[handle_high]["high"] * 100
                )
                if handle_depth > cup_depth / 3:
                    continue
                entry = prices[right_peak_idx]["close"]
                target = entry + (cup_high - cup_low)
                confidence = self._score_cup_handle(cup_depth, handle_depth, cup_end - start)
                results.append({
                    "pattern_type": "cup_handle",
                    "direction": "bullish",
                    "start_date": prices[start]["trade_date"].isoformat(),
                    "end_date": prices[handle_end]["trade_date"].isoformat(),
                    "entry_price": round(entry, 2),
                    "target_price": round(target, 2),
                    "stop_loss": round(cup_low * 0.98, 2),
                    "confidence_score": round(confidence, 1),
                    "pattern_data": {
                        "cup_high": round(cup_high, 2),
                        "cup_low": round(cup_low, 2),
                        "cup_depth_pct": round(cup_depth, 2),
                        "handle_depth_pct": round(handle_depth, 2),
                        "cup_duration": cup_end - start,
                        "handle_duration": handle_end - right_peak_idx,
                    },
                })
                break
        return results

    def _score_cup_handle(self, cup_depth: float, handle_depth: float, duration: int) -> float:
        score = 50.0
        if 15 <= cup_depth <= 35:
            score += 15
        elif cup_depth > 35:
            score += 10
        if handle_depth < cup_depth / 4:
            score += 15
        elif handle_depth < cup_depth / 3:
            score += 10
        if 30 <= duration <= 120:
            score += 10
        elif duration > 120:
            score += 5
        return max(0.0, min(100.0, score))

    async def detect_flags(
        self, symbol: str, end_date: date | None = None,
    ) -> list[dict[str, Any]]:
        if end_date is None:
            end_date = date.today()
        prices = await self._get_prices(symbol, end_date)
        if len(prices) < 30:
            return []
        results: list[dict[str, Any]] = []
        for i in range(len(prices) - FLAG_MIN_BARS):
            flagpole_end = i + FLAG_MIN_BARS
            if flagpole_end >= len(prices):
                break
            flagpole_change = (
                (prices[flagpole_end]["close"] - prices[i]["close"])
                / prices[i]["close"] * 100
            )
            if abs(flagpole_change) < 8:
                continue
            direction = "bullish" if flagpole_change > 0 else "bearish"
            for flag_len in range(FLAG_MIN_BARS, min(FLAG_MAX_BARS, len(prices) - flagpole_end)):
                flag_end = flagpole_end + flag_len
                flag_start = flagpole_end
                flag_change = (
                    (prices[flag_end]["close"] - prices[flag_start]["close"])
                    / prices[flag_start]["close"] * 100
                )
                if direction == "bullish" and flag_change > -2:
                    continue
                if direction == "bearish" and flag_change < 2:
                    continue
                flag_high = max(prices[j]["high"] for j in range(flag_start, flag_end + 1))
                flag_low = min(prices[j]["low"] for j in range(flag_start, flag_end + 1))
                flag_width = (flag_high - flag_low) / flag_low * 100
                if flag_width > 15:
                    continue
                entry = prices[flag_end]["close"]
                target = entry + (prices[flagpole_end]["close"] - prices[i]["close"]) if direction == "bullish" else entry - (prices[i]["close"] - prices[flagpole_end]["close"])
                confidence = self._score_flag(abs(flagpole_change), flag_width, flag_len, flag_change)
                results.append({
                    "pattern_type": f"{'bull' if direction == 'bullish' else 'bear'}_flag",
                    "direction": direction,
                    "start_date": prices[i]["trade_date"].isoformat(),
                    "end_date": prices[flag_end]["trade_date"].isoformat(),
                    "entry_price": round(entry, 2),
                    "target_price": round(target, 2),
                    "stop_loss": round(
                        flag_low * 0.98 if direction == "bullish" else flag_high * 1.02, 2,
                    ),
                    "confidence_score": round(confidence, 1),
                    "pattern_data": {
                        "flagpole_change_pct": round(flagpole_change, 2),
                        "flag_change_pct": round(flag_change, 2),
                        "flag_width_pct": round(flag_width, 2),
                        "flagpole_bars": FLAG_MIN_BARS,
                        "flag_bars": flag_len,
                    },
                })
                break
        return results

    def _score_flag(
        self, pole_pct: float, width_pct: float, duration: int, flag_retrace: float,
    ) -> float:
        score = 50.0
        if pole_pct >= 15:
            score += 15
        elif pole_pct >= 10:
            score += 10
        if width_pct <= 8:
            score += 15
        elif width_pct <= 12:
            score += 10
        if 5 <= duration <= 15:
            score += 10
        if abs(flag_retrace) <= 5:
            score += 5
        return max(0.0, min(100.0, score))

    async def detect_triangles(
        self, symbol: str, end_date: date | None = None,
    ) -> list[dict[str, Any]]:
        if end_date is None:
            end_date = date.today()
        prices = await self._get_prices(symbol, end_date)
        if len(prices) < TRIANGLE_MIN_BARS:
            return []
        peaks = self._find_peaks(prices, window=3)
        troughs = self._find_troughs(prices, window=3)
        results: list[dict[str, Any]] = []
        for end_idx in range(TRIANGLE_MIN_BARS, len(prices)):
            start_idx = max(0, end_idx - 60)
            relevant_peaks = [p for p in peaks if start_idx <= p <= end_idx]
            relevant_troughs = [t for t in troughs if start_idx <= t <= end_idx]
            if len(relevant_peaks) < 3 or len(relevant_troughs) < 3:
                continue
            upper_slope = self._linear_regression_slope(prices, relevant_peaks, use_high=True)
            lower_slope = self._linear_regression_slope(prices, relevant_troughs, use_high=False)
            upper_last = prices[relevant_peaks[-1]]["high"]
            lower_last = prices[relevant_troughs[-1]]["low"]
            upper_first = prices[relevant_peaks[0]]["high"]
            lower_first = prices[relevant_troughs[0]]["low"]
            gap_start = upper_first - lower_first
            gap_end = upper_last - lower_last
            if gap_start <= 0 or gap_end <= 0:
                continue
            convergence = (gap_start - gap_end) / gap_start
            if convergence < 0.2:
                continue
            pattern_type = "symmetrical_triangle"
            direction = "neutral"
            if upper_slope > -0.1 and lower_slope > 0.5:
                pattern_type = "ascending_triangle"
                direction = "bullish"
            elif lower_slope < 0.1 and upper_slope < -0.5:
                pattern_type = "descending_triangle"
                direction = "bearish"
            entry = prices[end_idx]["close"]
            if direction == "bullish":
                target = entry + (upper_first - lower_first)
            elif direction == "bearish":
                target = entry - (upper_first - lower_first)
            else:
                breakout_dir = "bullish" if entry > upper_last else "bearish" if entry < lower_last else "neutral"
                direction = breakout_dir
                target = entry + (upper_first - lower_first) if breakout_dir == "bullish" else entry - (upper_first - lower_first)
            confidence = self._score_triangle(convergence, len(relevant_peaks), gap_end)
            results.append({
                "pattern_type": pattern_type,
                "direction": direction,
                "start_date": prices[relevant_peaks[0]]["trade_date"].isoformat(),
                "end_date": prices[end_idx]["trade_date"].isoformat(),
                "entry_price": round(entry, 2),
                "target_price": round(target, 2),
                "stop_loss": round(
                    lower_last * 0.97 if direction == "bullish" else upper_last * 1.03, 2,
                ),
                "confidence_score": round(confidence, 1),
                "pattern_data": {
                    "upper_slope": round(upper_slope, 4),
                    "lower_slope": round(lower_slope, 4),
                    "convergence_ratio": round(convergence, 4),
                    "upper_peak_count": len(relevant_peaks),
                    "lower_trough_count": len(relevant_troughs),
                    "gap_pct": round(gap_end / upper_last * 100, 2),
                },
            })
            break
        return results

    def _score_triangle(self, convergence: float, touches: int, gap: float) -> float:
        score = 50.0
        if convergence >= 0.5:
            score += 15
        elif convergence >= 0.3:
            score += 10
        if touches >= 4:
            score += 15
        elif touches >= 3:
            score += 10
        if gap / 100 < 5:
            score += 10
        return max(0.0, min(100.0, score))

    async def detect_support_resistance(
        self, symbol: str, end_date: date | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        if end_date is None:
            end_date = date.today()
        prices = await self._get_prices(symbol, end_date)
        if len(prices) < 30:
            return {"support": [], "resistance": []}
        peaks = self._find_peaks(prices, window=3)
        troughs = self._find_troughs(prices, window=3)
        resistance_levels: list[dict[str, Any]] = []
        support_levels: list[dict[str, Any]] = []
        for p in peaks:
            self._add_to_cluster(
                resistance_levels, prices[p]["high"],
                prices[p]["trade_date"], "resistance", prices, SR_CLUSTER_PERCENT,
            )
        for t in troughs:
            self._add_to_cluster(
                support_levels, prices[t]["low"],
                prices[t]["trade_date"], "support", prices, SR_CLUSTER_PERCENT,
            )
        support_levels = [s for s in support_levels if s["touch_count"] >= MIN_SR_TOUCHES]
        resistance_levels = [r for r in resistance_levels if r["touch_count"] >= MIN_SR_TOUCHES]
        support_levels.sort(key=lambda x: x["strength_score"], reverse=True)
        resistance_levels.sort(key=lambda x: x["strength_score"], reverse=True)
        return {
            "support": support_levels[:10],
            "resistance": resistance_levels[:10],
        }

    def _add_to_cluster(
        self, levels: list[dict[str, Any]], price: float,
        trade_date: date, level_type: str,
        prices: list[dict[str, Any]], tolerance: float,
    ) -> None:
        for level in levels:
            if abs(level["price_level"] - price) / max(level["price_level"], price) <= tolerance:
                level["touch_count"] += 1
                level["last_tested"] = max(level["last_tested"], trade_date)
                level["price_level"] = round(
                    (level["price_level"] * (level["touch_count"] - 1) + price) / level["touch_count"], 2,
                )
                level["strength_score"] = round(
                    min(100.0, level["touch_count"] / max(MIN_SR_TOUCHES, 1) * 30 + 
                        (trade_date - level["first_detected"]).days / 10), 1,
                )
                return
        levels.append({
            "price_level": round(price, 2),
            "level_type": level_type,
            "strength_score": round(min(100.0, 20.0 + (trade_date - trade_date).days / 10), 1),
            "touch_count": 1,
            "first_detected": trade_date,
            "last_tested": trade_date,
        })

    async def classify_pattern(
        self, symbol: str, pattern_data: dict[str, Any],
    ) -> dict[str, Any]:
        features: dict[str, float] = {}
        confidence = 50.0
        reasons: list[str] = []
        pattern_type = pattern_data.get("pattern_type", "")
        prices = await self._get_prices(symbol, date.today())
        if not prices:
            return {"confidence_score": 0.0, "features": {}, "reasons": ["No price data"]}
        if pattern_type in ("double_top", "double_bottom"):
            pd_data = pattern_data.get("pattern_data", {})
            symmetry = 1.0 - abs(
                pd_data.get("peak1_price", 0) - pd_data.get("peak2_price", 0)
            ) / max(pd_data.get("peak1_price", 1), pd_data.get("peak2_price", 1))
            features["symmetry"] = symmetry
            depth = pd_data.get("depth_pct", 0)
            features["depth_pct"] = depth
            volume_trend = self._analyze_volume_trend(prices, len(prices) // 2, len(prices))
            features["volume_trend"] = volume_trend
            if symmetry > 0.95:
                confidence += 15
                reasons.append("High symmetry")
            elif symmetry > 0.85:
                confidence += 8
                reasons.append("Good symmetry")
            if 10 <= depth <= 25:
                confidence += 10
                reasons.append("Ideal depth")
            if volume_trend > 1.2:
                confidence += 10
                reasons.append("Rising volume on breakout")
        elif pattern_type == "cup_handle":
            pd_data = pattern_data.get("pattern_data", {})
            cup_depth = pd_data.get("cup_depth_pct", 0)
            handle_depth = pd_data.get("handle_depth_pct", 0)
            features["cup_depth"] = cup_depth
            features["handle_depth_ratio"] = handle_depth / max(cup_depth, 0.01)
            if 15 <= cup_depth <= 35:
                confidence += 15
                reasons.append("Ideal cup depth")
            if handle_depth / max(cup_depth, 0.01) < 0.25:
                confidence += 15
                reasons.append("Shallow handle")
        elif "flag" in pattern_type:
            pd_data = pattern_data.get("pattern_data", {})
            pole_pct = abs(pd_data.get("flagpole_change_pct", 0))
            width = pd_data.get("flag_width_pct", 0)
            features["flagpole_strength"] = pole_pct
            features["flag_width"] = width
            if pole_pct >= 15:
                confidence += 15
                reasons.append("Strong flagpole")
            if width <= 8:
                confidence += 10
                reasons.append("Tight flag consolidation")
        elif "triangle" in pattern_type:
            pd_data = pattern_data.get("pattern_data", {})
            convergence = pd_data.get("convergence_ratio", 0)
            features["convergence"] = convergence
            if convergence >= 0.5:
                confidence += 15
                reasons.append("Strong convergence")
            volume_trend = self._analyze_volume_trend(prices, len(prices) // 2, len(prices))
            features["volume_trend"] = volume_trend
            if volume_trend < 0.8:
                confidence += 10
                reasons.append("Declining volume during formation")
        adj_confidence = max(0.0, min(100.0, confidence))
        return {
            "confidence_score": round(adj_confidence, 1),
            "features": {k: round(v, 4) for k, v in features.items()},
            "reasons": reasons,
        }

    def _analyze_volume_trend(
        self, prices: list[dict[str, Any]], start: int, end: int,
    ) -> float:
        if end - start < 5:
            return 1.0
        first_half = sum(prices[i]["volume"] for i in range(start, start + (end - start) // 2))
        second_half = sum(prices[i]["volume"] for i in range(start + (end - start) // 2, end))
        first_count = (end - start) // 2
        second_count = end - start - first_count
        avg_first = first_half / max(first_count, 1)
        avg_second = second_half / max(second_count, 1)
        return avg_second / max(avg_first, 1)

    async def scan_symbol(
        self, symbol: str, end_date: date | None = None, store: bool = False,
    ) -> dict[str, Any]:
        if end_date is None:
            end_date = date.today()
        double_tops = await self.detect_double_top(symbol, end_date)
        double_bottoms = await self.detect_double_bottom(symbol, end_date)
        cup_handles = await self.detect_cup_handle(symbol, end_date)
        flags = await self.detect_flags(symbol, end_date)
        triangles = await self.detect_triangles(symbol, end_date)
        sr = await self.detect_support_resistance(symbol, end_date)
        all_patterns = double_tops + double_bottoms + cup_handles + flags + triangles
        classified: list[dict[str, Any]] = []
        if store:
            for p in all_patterns:
                ai_result = await self.classify_pattern(symbol, p)
                p["confidence_score"] = ai_result["confidence_score"]
                record = await self._pattern_repo.create(
                    symbol=symbol,
                    pattern_type=p["pattern_type"],
                    direction=p["direction"],
                    start_date=date.fromisoformat(p["start_date"]),
                    end_date=date.fromisoformat(p["end_date"]),
                    entry_price=p["entry_price"],
                    target_price=p["target_price"],
                    stop_loss=p["stop_loss"],
                    confidence_score=p["confidence_score"],
                    pattern_data_json=json.dumps(p["pattern_data"]),
                    is_active=True,
                    metadata_json=json.dumps({"ai_classification": ai_result}),
                )
                classified.append({**p, "id": record.id, "ai_classification": ai_result})
        else:
            for p in all_patterns:
                ai_result = await self.classify_pattern(symbol, p)
                p["confidence_score"] = ai_result["confidence_score"]
                classified.append({**p, "ai_classification": ai_result})
        for sr_list in [sr["support"], sr["resistance"]]:
            for level in sr_list:
                existing = await self._session.execute(
                    select(SupportResistance).where(
                        SupportResistance.symbol == symbol,
                        SupportResistance.level_type == level["level_type"],
                        func.abs(SupportResistance.price_level - level["price_level"]) / SupportResistance.price_level < 0.005,
                    )
                )
                if not existing.scalar_one_or_none():
                    await self._sr_repo.create(
                        symbol=symbol,
                        level_type=level["level_type"],
                        price_level=level["price_level"],
                        strength_score=level["strength_score"],
                        touch_count=level["touch_count"],
                        first_detected=level["first_detected"],
                        last_tested=level["last_tested"],
                        is_active=True,
                    )
        if store and all_patterns:
            await self._session.flush()
        return {
            "symbol": symbol,
            "end_date": end_date.isoformat(),
            "patterns": classified,
            "support_resistance": sr,
            "total_patterns": len(classified),
        }

    async def scan_all_symbols(
        self, end_date: date | None = None, store: bool = False,
    ) -> list[dict[str, Any]]:
        symbols = await self._get_active_symbols()
        results: list[dict[str, Any]] = []
        for symbol in symbols:
            try:
                result = await self.scan_symbol(symbol, end_date, store)
                results.append(result)
            except Exception:
                logger.exception("Failed to scan symbol", symbol=symbol)
        return results

    async def get_detected_patterns(
        self, symbol: str | None = None, pattern_type: str | None = None,
        direction: str | None = None, min_confidence: float | None = None,
        is_active: bool | None = None,
        skip: int = 0, limit: int = 100,
    ) -> tuple[Sequence[ChartPattern], int]:
        stmt = select(ChartPattern)
        if symbol:
            stmt = stmt.where(ChartPattern.symbol == symbol)
        if pattern_type:
            stmt = stmt.where(ChartPattern.pattern_type == pattern_type)
        if direction:
            stmt = stmt.where(ChartPattern.direction == direction)
        if min_confidence is not None:
            stmt = stmt.where(ChartPattern.confidence_score >= min_confidence)
        if is_active is not None:
            stmt = stmt.where(ChartPattern.is_active == is_active)
        count_result = await self._session.execute(stmt)
        total = len(count_result.scalars().all())
        stmt = stmt.order_by(ChartPattern.created_at.desc()).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    async def get_support_resistance(
        self, symbol: str, level_type: str | None = None,
        is_active: bool | None = None,
    ) -> list[SupportResistance]:
        stmt = select(SupportResistance).where(SupportResistance.symbol == symbol)
        if level_type:
            stmt = stmt.where(SupportResistance.level_type == level_type)
        if is_active is not None:
            stmt = stmt.where(SupportResistance.is_active == is_active)
        stmt = stmt.order_by(SupportResistance.strength_score.desc().nullslast())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_pattern_summary(
        self, symbol: str,
    ) -> dict[str, Any]:
        patterns, total = await self.get_detected_patterns(symbol=symbol, limit=500)
        sr = await self.get_support_resistance(symbol)
        type_counts: dict[str, int] = {}
        direction_counts: dict[str, int] = {}
        for p in patterns:
            type_counts[p.pattern_type] = type_counts.get(p.pattern_type, 0) + 1
            direction_counts[p.direction] = direction_counts.get(p.direction, 0) + 1
        return {
            "symbol": symbol,
            "total_patterns": total,
            "pattern_type_counts": type_counts,
            "direction_counts": direction_counts,
            "top_patterns": [
                {
                    "id": p.id, "pattern_type": p.pattern_type,
                    "direction": p.direction,
                    "confidence_score": p.confidence_score,
                    "end_date": p.end_date.isoformat(),
                }
                for p in sorted(patterns, key=lambda x: x.confidence_score or 0, reverse=True)[:10]
            ],
            "support_levels": [
                {"price": s.price_level, "strength": s.strength_score, "touches": s.touch_count}
                for s in sr if s.level_type == "support"
            ],
            "resistance_levels": [
                {"price": s.price_level, "strength": s.strength_score, "touches": s.touch_count}
                for s in sr if s.level_type == "resistance"
            ],
        }

    async def update_pattern_active(
        self, pattern_id: int, is_active: bool,
    ) -> ChartPattern | None:
        stmt = select(ChartPattern).where(ChartPattern.id == pattern_id)
        result = await self._session.execute(stmt)
        pattern = result.scalar_one_or_none()
        if pattern is None:
            return None
        pattern.is_active = is_active
        await self._session.flush()
        return pattern

    async def delete_pattern(self, pattern_id: int) -> bool:
        return await self._pattern_repo.delete(pattern_id)

    async def delete_sr_level(self, sr_id: int) -> bool:
        return await self._sr_repo.delete(sr_id)

    def list_pattern_types(self) -> list[str]:
        return list(PATTERN_TYPES)
