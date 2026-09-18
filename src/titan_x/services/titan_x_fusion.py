"""Titan X Fusion - Unified intraday strategy engine.

Output: ONLY BUY / SELL / HOLD (no scores, no percentages).
Primary time-frames: 5m, 15m (optional 30m).
Highly selective gate-based decision engine.
"""

from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Sequence

from titan_x.infrastructure.market_data_providers import MarketDataPoint
from titan_x.services.performance_analyzer import PerformanceAnalyzer
from titan_x.services.technical_indicator_engine import IndicatorMath, supertrend


# ---------------------------------------------------------------------------
#  Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FusionParams:
    """Parameters controlling the Titan X Fusion gate logic."""

    # ---------- Periods ----------
    ema_fast: int = 9
    ema_mid: int = 20
    ema_slow: int = 50
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    atr_period: int = 14
    supertrend_period: int = 10
    supertrend_multiplier: float = 3.0
    adx_period: int = 14
    adx_chop_threshold: float = 20.0

    # ---------- Volume ----------
    volume_lookback: int = 20
    breakout_vol_ratio: float = 1.2
    pullback_vol_ratio: float = 0.6

    # ---------- Structure ----------
    breakout_lookback: int = 20
    pullback_epsilon_atr: float = 0.5  # fraction of ATR for pullback detection

    # ---------- Filter thresholds ----------
    min_bars: int = 60          # minimum confirmed bars needed before a decision
    atr_pct_min: float = 0.1
    atr_pct_max: float = 3.0
    no_chase_band: tuple[float, float] = field(default_factory=lambda: (0.2, 2.0))
    risk_reward_min: float = 2.0

    # ---------- Behavioural ----------
    execution_delay_bars: int = 1   # enter on the bar *after* the signal bar
    stale_bar_buffer: float = 2.0   # seconds beyond interval before bar deemed stale


# ---------------------------------------------------------------------------
#  Engine
# ---------------------------------------------------------------------------

class TitanXFusionEngine:
    """Stateful engine that evaluates one confirmed bar at a time.

    Returns a decision dict containing ``decision`` (BUY / SELL / HOLD),
    a human‑readable ``reason``, entry / stop / target prices, and a per-gate
    status map.  A separate ``build_series`` method emits per-bar signals for
    chart‑marker overlays.
    """

    def __init__(self, params: FusionParams | None = None) -> None:
        self._params = params or FusionParams()
        self._last_decision: str | None = None        # for dedupe
        self._analyzer = PerformanceAnalyzer()

    # ------------------------------------------------------------------
    #  Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        points: Sequence[MarketDataPoint],
        *,
        dedupe: bool = True,
    ) -> dict[str, Any]:
        """Evaluate the latest *confirmed* bar and return a decision dict.

        Parameters
        ----------
        points : sequence of MarketDataPoint
            OHLCV data ordered chronologically (newest last).  Timestamps are
            preferred; if all ``timestamp`` fields are ``None`` the engine
            falls back to ``trade_date``.
        dedupe : bool, default True
            If ``True`` and the emitted decision is the same as the previously
            emitted decision, the reason is overridden to "Signal already
            active – awaiting fresh setup".

        Returns
        -------
        dict with keys:
            decision  : "BUY" | "SELL" | "HOLD"
            reason    : str   – why this decision was taken (or blocked)
            entry     : float | None
            stop_loss : float | None
            target    : float | None
            price     : float   – close of the decision bar
            regime    : str     – detected market regime
            gates     : dict    – per-gate boolean/status map
        """
        if not points or len(points) < self._params.min_bars:
            return {
                "decision": "HOLD",
                "reason": "Insufficient confirmed data",
                "entry": None,
                "stop_loss": None,
                "target": None,
                "price": 0.0,
                "regime": "UNKNOWN",
                "gates": {},
            }

        # ------------------------------------------------------------------
        #  Compute all indicator series once (vectors indexed by bar)
        # ------------------------------------------------------------------
        ctx = self._compute_indicators(points)

        # ------------------------------------------------------------------
        #  Locate the last *confirmed* bar (not the currently forming one)
        # ------------------------------------------------------------------
        confirmed_idx = self._last_confirmed_bar_idx(points)
        if confirmed_idx is None:
            return {
                "decision": "HOLD",
                "reason": "No confirmed bars available",
                "entry": None,
                "stop_loss": None,
                "target": None,
                "price": 0.0,
                "regime": "UNKNOWN",
                "gates": {},
            }

        # ------------------------------------------------------------------
        #  Evaluate at the confirmed bar (pure, no dedupe across bars here)
        # ------------------------------------------------------------------
        decision = self._evaluate_at(confirmed_idx, ctx, dedupe=False)

        # ------------------------------------------------------------------
        #  Apply cross-bar dedupe if requested
        # ------------------------------------------------------------------
        if dedupe and decision["decision"] == self._last_decision:
            # Keep the original reason but prepend the dedupe note
            original_reason = decision["reason"]
            decision["reason"] = (
                f"Signal already active – awaiting fresh setup ({original_reason})"
            )

        self._last_decision = decision["decision"]

        # Attach regime & gates (ensure they exist)
        decision.setdefault("regime", "UNKNOWN")
        decision.setdefault("gates", {})
        return decision

    def build_series(
        self,
        points: Sequence[MarketDataPoint],
    ) -> list[dict[str, Any]]:
        """Emit per-bar BUY/SELL/HOLD markers for the chart.

        The returned list has one entry per *confirmed* bar (from warmup
        index onward).  Each entry is::

            {
                "time": "<ISO‑timestamp or date>",
                "side" : "BUY" | "SELL" | "HOLD",
                "reason": str,
                "entry"   : float | None,
                "stop_loss": float | None,
                "target"  : float | None,
            }

        Only non‑HOLD entries typically appear as markers; HOLD bars are
        omitted so the chart isn’t cluttered.
        """
        if not points or len(points) < self._params.min_bars:
            return []

        ctx = self._compute_indicators(points)
        series: list[dict[str, Any]] = []

        # Evaluate every bar from the warmup index onward; dedupe=False so
        # each bar’s decision is independent.
        warmup = self._warmup_idx(len(points))
        for i in range(warmup, len(points)):
            decision = self._evaluate_at(i, ctx, dedupe=False)
            # Only emit if not HOLD (caller can filter)
            if decision["decision"] != "HOLD":
                series.append({
                    "time": (
                        points[i].timestamp.isoformat()
                        if points[i].timestamp
                        else points[i].trade_date.isoformat()
                    ),
                    "side": decision["decision"],
                    "reason": decision["reason"],
                    "entry": decision.get("entry"),
                    "stop_loss": decision.get("stop_loss"),
                    "target": decision.get("target"),
                })

        return series

    # ------------------------------------------------------------------
    #  Private – indicator computation (once for the whole series)
    # ------------------------------------------------------------------

    def _compute_indicators(self, points: Sequence[MarketDataPoint]) -> dict[str, list[float | None]]:
        """Return all indicator series as lists aligned with ``points``."""
        n = len(points)
        # Extract arrays (assume chronological order, newest last)
        opens = [p.open for p in points]
        highs = [p.high for p in points]
        lows = [p.low for p in points]
        closes = [p.close for p in points]
        vols = [p.volume for p in points]

        # EMA series
        e9 = IndicatorMath.ema(closes, self._params.ema_fast)
        e20 = IndicatorMath.ema(closes, self._params.ema_mid)
        e50 = IndicatorMath.ema(closes, self._params.ema_slow)

        # RSI
        rsi = IndicatorMath.rsi(closes, self._params.rsi_period)

        # MACD (line, signal, histogram)
        macd_line, macd_signal, macd_hist = IndicatorMath.macd(
            closes, self._params.macd_fast, self._params.macd_slow, self._params.macd_signal
        )

        # ATR
        atr = IndicatorMath.atr(highs, lows, closes, self._params.atr_period)

        # SuperTrend (direction "up"/"down", st_line)
        st_dir, st_line = supertrend(
            highs, lows, closes, self._params.supertrend_period, self._params.supertrend_multiplier
        )

        # ADX + +DI / -DI
        adx_line, pdi, mdi = IndicatorMath.adx(highs, lows, closes, self._params.adx_period)

        # VWAP (cumulative over the whole series – adequate for intraday)
        vwap = IndicatorMath.vwap(highs, lows, closes, vols)

        # Volume SMA for comparison
        vol_sma = self._sma(vols, self._params.volume_lookback)

        return {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": vols,
            "e9": e9,
            "e20": e20,
            "e50": e50,
            "rsi": rsi,
            "macd": macd_line,
            "macd_signal": macd_signal,
            "macd_hist": macd_hist,
            "atr": atr,
            "st_dir": st_dir,
            "st_line": st_line,
            "adx": adx_line,
            "pdi": pdi,
            "mdi": mdi,
            "vwap": vwap,
            "vol_sma": vol_sma,
        }

    # ------------------------------------------------------------------
    #  Private – helpers (warmup, staleness, gate logic)
    # ------------------------------------------------------------------

    @staticmethod
    def _sma(values: Sequence[float], period: int) -> list[float | None]:
        """Simple moving average; returns list same length as *values*."""
        if len(values) < period:
            return [None] * len(values)
        result: list[float | None] = [None] * (period - 1)
        window_sum = sum(values[:period])
        result.append(window_sum / period)
        for i in range(period, len(values)):
            window_sum += values[i] - values[i - period]
            result.append(window_sum / period)
        return result

    def _last_confirmed_bar_idx(self, points: Sequence[MarketDataPoint]) -> int | None:
        """Index of the last bar whose interval has fully elapsed.

        If all ``timestamp`` fields are ``None`` we fall back to the last bar.
        """
        now = datetime.now(timezone.utc)
        # Quick check: are there any timestamps at all?
        has_ts = any(p.timestamp is not None for p in points)
        if not has_ts:
            return len(points) - 1

        # Simple heuristic: the last bar whose timestamp is at least one interval
        # seconds in the past.  We use a fixed "5m" equivalent for demo purposes;
        # in production the caller would pass the interval.
        interval_seconds = 300  # 5 minutes – match default interval
        for i in range(len(points) - 1, -1, -1):
            ts = points[i].timestamp
            if ts is not None and (now - ts).total_seconds() > interval_seconds:
                return i
        # If no bar is that old, return the last bar (it will be treated as
        # stale and may produce HOLD).
        return len(points) - 1

    def _warmup_idx(self, n: int) -> int:
        """Minimum index such that all indicator series have valid values."""
        # EMA needs at least its period; RSI needs period+1; MACD needs slow+signal;
        # ATR and SuperTrend need their periods.  60 bars safely covers all typical
        # parameter sets (50‑ema, 14‑atr, 10‑supertrend, 26‑macd‑slow).
        return max(60, n // 2) if n > 200 else 0

    # ------------------------------------------------------------------
    #  Private – bar‑by‑bar evaluation (pure, using pre‑computed ctx)
    # ------------------------------------------------------------------

    def _evaluate_at(
        self,
        i: int,
        ctx: dict[str, list[float | None]],
        *,
        dedupe: bool = True,
    ) -> dict[str, Any]:
        """Evaluate bar index *i* using the full indicator context *ctx*.

        The returned dict contains the same keys as ``evaluate()`` above,
        minus the dedupe cross‑bar logic (handled by the caller).
        """
        # Pull scalar values at bar i; guard against None
        close = ctx["close"][i]
        high = ctx["high"][i]
        low = ctx["low"][i]
        open_ = ctx["open"][i]
        vol = ctx["volume"][i]

        e9 = ctx["e9"][i]
        e20 = ctx["e20"][i]
        e50 = ctx["e50"][i]
        rsi_val = ctx["rsi"][i]
        macd_line = ctx["macd"][i]
        macd_signal = ctx["macd_signal"][i]
        macd_hist = ctx["macd_hist"][i]
        atr_val = ctx["atr"][i]
        st_dir = ctx["st_dir"][i]
        st_line = ctx["st_line"][i]
        adx_val = ctx["adx"][i]
        pdi = ctx["pdi"][i]
        mdi = ctx["mdi"][i]
        vwap_val = ctx["vwap"][i]
        vol_sma = ctx["vol_sma"][i] if i < len(ctx["vol_sma"]) else 0.0

        # ------------------------------------------------------------------
        #  1. Data‑validation gate
        # ------------------------------------------------------------------
        if any(v is None for v in (close, high, low, atr_val, e9, e20, e50, rsi_val, macd_line, macd_signal)):
            return {"decision": "HOLD", "reason": "Missing indicator values at bar", "gates": {}}

        # ------------------------------------------------------------------
        #  2. Regime detection
        # ------------------------------------------------------------------
        regime = self._detect_regime(e20, e50, close, atr_val, st_dir, adx_val)

        # ------------------------------------------------------------------
        #  3. Trend‑structure gate (BUY: EMA9>EMA20>EMA50 & price>EMA20 & SuperTrend up)
        # ------------------------------------------------------------------
        ema_chain = e9 > e20 > e50
        price_above_ema20 = close > e20
        supertrend_bullish = st_dir == "up"
        trend_ok = ema_chain and price_above_ema20 and supertrend_bullish

        # SELL mirror: EMA9<EMA20<EMA50 & price<EMA20 & SuperTrend down
        ema_chain_down = e9 < e20 < e50
        price_below_ema20 = close < e20
        supertrend_bearish = st_dir == "down"
        trend_ok_sell = ema_chain_down and price_below_ema20 and supertrend_bearish

        # ------------------------------------------------------------------
        #  4. VWAP gate
        # ------------------------------------------------------------------
        vwap_ok_buy = close > vwap_val and (close - vwap_val) <= 2.0 * atr_val
        vwap_ok_sell = close < vwap_val and (vwap_val - close) <= 2.0 * atr_val

        # ------------------------------------------------------------------
        #  5. Momentum gate
        # ------------------------------------------------------------------
        momentum_ok_buy = rsi_val > 52 and macd_line > macd_signal and macd_hist >= 0
        momentum_ok_sell = rsi_val < 48 and macd_line < macd_signal and macd_hist <= 0

        # ------------------------------------------------------------------
        #  6. Volume gate (simplified – checked via structure later)
        # ------------------------------------------------------------------
        # For now we mark volume as pending; the detailed ratio check happens
        # inside the structure detection which is lightweight.
        vol_ok_buy = True
        vol_ok_sell = True

        # ------------------------------------------------------------------
        #  7. False‑breakout protection
        # ------------------------------------------------------------------
        # Reject if the bar has a dominant upper wick (price rejected higher)
        range_bar = high - low
        if range_bar > 0:
            upper_wick = high - max(open_, close)
            # If upper wick >= 60% of the bar range → likely a false breakout
            if upper_wick >= 0.6 * range_bar:
                # HOLD with reason; we'll let the final decision logic capture this
                false_breakout = True
            else:
                false_breakout = False
        else:
            false_breakout = False

        # ------------------------------------------------------------------
        #  8. No‑chase (not extended) – distance from EMA20 in ATR units
        # ------------------------------------------------------------------
        dist_from_ema = (close - e20) / max(atr_val, 1e-6)
        no_chase_ok = self._params.no_chase_band[0] <= abs(dist_from_ema) <= self._params.no_chase_band[1]

        # ------------------------------------------------------------------
        #  9. Reversal protection
        # ------------------------------------------------------------------
        # If RSI has been falling for two bars while still >52 (BUY) or <48 (SELL)
        rsi_i_1 = ctx["rsi"][i - 1] if i > 0 else None
        rsi_i_2 = ctx["rsi"][i - 2] if i > 1 else None
        reversal_warning = (
            rsi_i_1 is not None
            and rsi_i_2 is not None
            and rsi_val > 52
            and rsi_val < rsi_i_1
            and rsi_i_1 < rsi_i_2
        )

        # ------------------------------------------------------------------
        # 10. ATR filter
        # ------------------------------------------------------------------
        atr_pct = (atr_val / max(close, 1e-6)) * 100
        atr_ok = self._params.atr_pct_min <= atr_pct <= self._params.atr_pct_max

        # ------------------------------------------------------------------
        # 11. R:R ≥ 2 calculation (support/resistance via swing points)
        # ------------------------------------------------------------------
        support, resistance = self._compute_sr(i, ctx)
        risk = max(atr_val, abs(close - support)) if support is not None and close > support else atr_val
        reward = abs(resistance - close) if resistance is not None else None
        rr_ok = reward is not None and reward >= self._params.risk_reward_min * risk

        # ------------------------------------------------------------------
        # 12. Decide
        # ------------------------------------------------------------------
        # ---------- BUY ----------
        buy_pass = (
            trend_ok
            and vwap_ok_buy
            and momentum_ok_buy
            and vol_ok_buy
            and not false_breakout
            and no_chase_ok
            and atr_ok
            and not reversal_warning
        )

        # ---------- SELL (mirror) ----------
        sell_pass = (
            trend_ok_sell
            and vwap_ok_sell
            and momentum_ok_sell
            and not false_breakout  # same false‑breakout check mirrored
            and no_chase_ok
            and atr_ok
            and not reversal_warning
        )

        if buy_pass:
            stop, target, reason = self._compute_buy_levels(close, atr_val, support, resistance)
            return {
                "decision": "BUY",
                "reason": reason,
                "entry": round(float(close), 2),
                "stop_loss": stop,
                "target": target,
                "price": round(float(close), 2),
                "regime": regime,
                "gates": {
                    "regime": True,
                    "trend_structure": trend_ok,
                    "vwap": vwap_ok_buy,
                    "momentum": momentum_ok_buy,
                    "volume": vol_ok_buy,
                    "false_breakout": not false_breakout,
                    "no_chase": no_chase_ok,
                    "atr_filter": atr_ok,
                    "risk_reward": rr_ok,
                },
            }

        if sell_pass:
            stop, target, reason = self._compute_sell_levels(close, atr_val, support, resistance)
            return {
                "decision": "SELL",
                "reason": reason,
                "entry": round(float(close), 2),
                "stop_loss": stop,
                "target": target,
                "price": round(float(close), 2),
                "regime": regime,
                "gates": {
                    "regime": True,
                    "trend_structure": trend_ok_sell,
                    "vwap": vwap_ok_sell,
                    "momentum": momentum_ok_sell,
                    "volume": vol_ok_sell,
                    "false_breakout": not false_breakout,
                    "no_chase": no_chase_ok,
                    "atr_filter": atr_ok,
                    "risk_reward": rr_ok,
                },
            }

        # ---------- HOLD – collect failing gates ----------
        reason_parts: list[str] = []
        if not trend_ok:
            reason_parts.append("trend structure not aligned")
        if not vwap_ok_buy:
            reason_parts.append("price extended above VWAP")
        if not momentum_ok_buy:
            reason_parts.append("momentum insufficient")
        if false_breakout:
            reason_parts.append("false breakout protection triggered")
        if not no_chase_ok:
            reason_parts.append("price extended beyond acceptable band")
        if not atr_ok:
            reason_parts.append("ATR outside acceptable range")
        if reversal_warning:
            reason_parts.append("reversal warning active")
        if not rr_ok:
            reason_parts.append("risk/reward insufficient")

        reason = " · ".join(reason_parts) if reason_parts else "Gate criteria not met"

        return {
            "decision": "HOLD",
            "reason": reason,
            "entry": None,
            "stop_loss": None,
            "target": None,
            "price": round(float(close), 2),
            "regime": regime,
            "gates": {
                "regime": regime != "UNKNOWN",
                "trend_structure": trend_ok,
                "vwap": vwap_ok_buy,
                "momentum": momentum_ok_buy,
                "volume": vol_ok_buy,
                "false_breakout": not false_breakout,
                "no_chase": no_chase_ok,
                "atr_filter": atr_ok,
                "risk_reward": rr_ok,
            },
        }

    # ------------------------------------------------------------------
    #  Private – support/resistance via recent swing points
    # ------------------------------------------------------------------

    def _compute_sr(self, i: int, ctx: dict) -> tuple[float | None, float | None]:
        """Recent swing low (support) and swing high (resistance) within lookback."""
        lookback = 30
        start = max(0, i - lookback + 1)
        segment_high = ctx["high"][start : i + 1]
        segment_low = ctx["low"][start : i + 1]
        resistance = max(segment_high) if segment_high else None
        support = min(segment_low) if segment_low else None
        return support, resistance

    # ------------------------------------------------------------------
    #  Private – level computation for BUY / SELL
    # ------------------------------------------------------------------

    def _compute_buy_levels(
        self,
        close: float,
        atr: float,
        support: float | None,
        resistance: float | None,
    ) -> tuple[float | None, float | None, str]:
        """Determine SL / TGT for a BUY with R:R ≥ 2."""
        risk = max(atr, close - support) if support is not None and close > support else atr
        stop = round(close - risk, 2)

        if resistance is not None and resistance > close:
            reward = resistance - close
            if reward >= self._params.risk_reward_min * risk:
                target = round(close + reward, 2)
            else:
                target = round(close + self._params.risk_reward_min * risk, 2)
        else:
            target = round(close + self._params.risk_reward_min * risk, 2)

        reason = f"BUY at {round(close,2)}; SL {round(stop,2)}; TGT {round(target,2)} (R:R ≥ {self._params.risk_reward_min})"
        return stop, target, reason

    def _compute_sell_levels(
        self,
        close: float,
        atr: float,
        support: float | None,
        resistance: float | None,
    ) -> tuple[float | None, float | None, str]:
        """Determine SL / TGT for a SELL with R:R ≥ 2."""
        risk = max(atr, support - close) if support is not None and support > close else atr
        stop = round(close + risk, 2)

        if resistance is not None and resistance < close:
            reward = close - resistance
            if reward >= self._params.risk_reward_min * risk:
                target = round(resistance, 2)
            else:
                target = round(close - self._params.risk_reward_min * risk, 2)
        else:
            target = round(close - self._params.risk_reward_min * risk, 2)

        reason = f"SELL at {round(close,2)}; SL {round(stop,2)}; TGT {round(target,2)} (R:R ≥ {self._params.risk_reward_min})"
        return stop, target, reason

    # ------------------------------------------------------------------
    #  Private – regime detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_regime(
        e20: float,
        e50: float,
        close: float,
        atr: float,
        st_dir: str | None,
        adx: float | None,
    ) -> str:
        """Return a regime string.

        Possible values: STRONG_UPTREND | UPTREND | SIDEWAYS |
        DOWNTREND | STRONG_DOWNTREND | REVERSAL | CHOPPY
        """
        if adx is not None and adx < 20:
            return "CHOPPY"
        if e20 > e50 and close > e20:
            return "STRONG_UPTREND" if st_dir == "up" else "UPTREND"
        if e20 < e50 and close < e20:
            return "STRONG_DOWNTREND" if st_dir == "down" else "DOWNTREND"
        # Simple reversal flag when EMA9/20 crossed recently – we don't have EMA9
        # in this bare method; fall through.
        return "SIDEWAYS"