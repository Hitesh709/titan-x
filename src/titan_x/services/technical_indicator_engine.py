import hashlib
import json
import math
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.db.repository import BaseRepository
from titan_x.models.price import DailyPrice
from titan_x.models.technical import TechnicalIndicator

logger = structlog.get_logger(__name__)

INDICATOR_REGISTRY: dict[str, dict[str, Any]] = {}


def register_indicator(name: str, category: str, description: str, default_params: dict[str, Any]) -> None:
    INDICATOR_REGISTRY[name] = {
        "name": name, "category": category,
        "description": description, "default_params": default_params,
    }


class IndicatorMath:
    @staticmethod
    def sma(values: list[float], period: int) -> list[float | None]:
        result: list[float | None] = [None] * (period - 1)
        for i in range(period - 1, len(values)):
            result.append(sum(values[i - period + 1:i + 1]) / period)
        return result

    @staticmethod
    def ema(values: list[float], period: int) -> list[float | None]:
        multiplier = 2.0 / (period + 1)
        result: list[float | None] = [None] * (period - 1)
        if len(values) >= period:
            ema_val = sum(values[:period]) / period
            result.append(ema_val)
            for v in values[period:]:
                ema_val = (v - ema_val) * multiplier + ema_val
                result.append(ema_val)
        return result

    @staticmethod
    def rsi(values: list[float], period: int) -> list[float | None]:
        if len(values) < period + 1:
            return [None] * len(values)
        result: list[float | None] = [None] * period
        gains: list[float] = []
        losses: list[float] = []
        for i in range(1, period + 1):
            diff = values[i] - values[i - 1]
            gains.append(diff if diff > 0 else 0.0)
            losses.append(abs(diff) if diff < 0 else 0.0)
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        rs = avg_gain / avg_loss if avg_loss != 0 else 100.0
        result.append(100.0 - (100.0 / (1.0 + rs)))
        for i in range(period + 1, len(values)):
            diff = values[i] - values[i - 1]
            gain = diff if diff > 0 else 0.0
            loss = abs(diff) if diff < 0 else 0.0
            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period
            rs = avg_gain / avg_loss if avg_loss != 0 else 100.0
            result.append(100.0 - (100.0 / (1.0 + rs)))
        return result

    @staticmethod
    def macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[list[float | None], list[float | None], list[float | None]]:
        ema_fast = IndicatorMath.ema(values, fast)
        ema_slow = IndicatorMath.ema(values, slow)
        macd_line: list[float | None] = []
        for ef, es in zip(ema_fast, ema_slow):
            if ef is not None and es is not None:
                macd_line.append(ef - es)
            else:
                macd_line.append(None)
        signal_line = IndicatorMath.ema([v for v in macd_line if v is not None], signal) if any(v is not None for v in macd_line) else []
        signal_padded: list[float | None] = [None] * len(macd_line)
        sig_idx = len(macd_line) - len(signal_line)
        if sig_idx >= 0:
            for i, sv in enumerate(signal_line):
                signal_padded[sig_idx + i] = sv
        histogram: list[float | None] = []
        for ml, sl in zip(macd_line, signal_padded):
            if ml is not None and sl is not None:
                histogram.append(ml - sl)
            else:
                histogram.append(None)
        return macd_line, signal_padded, histogram

    @staticmethod
    def bollinger_bands(values: list[float], period: int = 20, std_dev: float = 2.0) -> tuple[list[float | None], list[float | None], list[float | None]]:
        middle = IndicatorMath.sma(values, period)
        upper: list[float | None] = []
        lower: list[float | None] = []
        for i in range(len(values)):
            if middle[i] is not None:
                slice_vals = values[i - period + 1:i + 1]
                mean = middle[i]
                variance = sum((x - mean) ** 2 for x in slice_vals) / period
                std = math.sqrt(variance)
                upper.append(mean + std_dev * std)
                lower.append(mean - std_dev * std)
            else:
                upper.append(None)
                lower.append(None)
        return upper, middle, lower

    @staticmethod
    def atr(high: list[float], low: list[float], close: list[float], period: int = 14) -> list[float | None]:
        if len(close) < 2:
            return [None] * len(close)
        tr: list[float] = []
        for i in range(1, len(close)):
            hl = high[i] - low[i]
            hc = abs(high[i] - close[i - 1])
            lc = abs(low[i] - close[i - 1])
            tr.append(max(hl, hc, lc))
        result: list[float | None] = [None]
        for i in range(1, period):
            result.append(None)
        if len(tr) >= period:
            atr_val = sum(tr[:period]) / period
            result.append(atr_val)
            for i in range(period, len(tr)):
                atr_val = (atr_val * (period - 1) + tr[i]) / period
                result.append(atr_val)
        while len(result) < len(close):
            result.append(None)
        return result[:len(close)]

    @staticmethod
    def adx(high: list[float], low: list[float], close: list[float], period: int = 14) -> tuple[list[float | None], list[float | None], list[float | None]]:
        n = len(close)
        if n < period + 1:
            return [None] * n, [None] * n, [None] * n
        plus_dm: list[float] = []
        minus_dm: list[float] = []
        tr: list[float] = []
        for i in range(1, n):
            h_diff = high[i] - high[i - 1]
            l_diff = low[i - 1] - low[i]
            plus_dm.append(h_diff if h_diff > l_diff and h_diff > 0 else 0.0)
            minus_dm.append(l_diff if l_diff > h_diff and l_diff > 0 else 0.0)
            tr_val = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
            tr.append(tr_val)
        atr_vals: list[float] = []
        plus_di: list[float] = []
        minus_di: list[float] = []
        atr_val = sum(tr[:period]) / period
        pdi = (sum(plus_dm[:period]) / period) / atr_val * 100 if atr_val > 0 else 0
        mdi = (sum(minus_dm[:period]) / period) / atr_val * 100 if atr_val > 0 else 0
        atr_vals.append(atr_val)
        plus_di.append(pdi)
        minus_di.append(mdi)
        for i in range(period, len(tr)):
            atr_val = (atr_val * (period - 1) + tr[i]) / period
            pdi = ((plus_di[-1] * (period - 1) + (plus_dm[i] / atr_val * 100 if atr_val > 0 else 0)) / period) if period > 0 else 0
            mdi = ((minus_di[-1] * (period - 1) + (minus_dm[i] / atr_val * 100 if atr_val > 0 else 0)) / period) if period > 0 else 0
            atr_vals.append(atr_val)
            plus_di.append(pdi)
            minus_di.append(mdi)
        dx_values: list[float] = []
        for pdi_v, mdi_v in zip(plus_di, minus_di):
            sum_di = pdi_v + mdi_v
            dx_values.append(abs(pdi_v - mdi_v) / sum_di * 100 if sum_di > 0 else 0)
        adx_line: list[float | None] = [None] * (period + period - 1)
        if len(dx_values) >= period:
            adx_val = sum(dx_values[:period]) / period
            adx_line.append(adx_val)
            for i in range(period, len(dx_values)):
                adx_val = (adx_val * (period - 1) + dx_values[i]) / period
                adx_line.append(adx_val)
        pdi_line: list[float | None] = [None] * period
        pdi_line.extend(plus_di)
        mdi_line: list[float | None] = [None] * period
        mdi_line.extend(minus_di)
        while len(adx_line) < n:
            adx_line.append(None)
        return adx_line[:n], pdi_line[:n], mdi_line[:n]

    @staticmethod
    def vwap(high: list[float], low: list[float], close: list[float], volume: list[int]) -> list[float | None]:
        cum_pv = 0.0
        cum_vol = 0
        result: list[float | None] = []
        for h, l, c, v in zip(high, low, close, volume):
            tp = (h + l + c) / 3
            cum_pv += tp * v
            cum_vol += v
            result.append(cum_pv / cum_vol if cum_vol > 0 else None)
        return result

    @staticmethod
    def sma_aligned(values: list[float], period: int) -> list[float]:
        return [v if v is not None else 0.0 for v in IndicatorMath.sma(values, period)]

    @staticmethod
    def ema_aligned(values: list[float], period: int) -> list[float]:
        return [v if v is not None else 0.0 for v in IndicatorMath.ema(values, period)]

    @staticmethod
    def wma(values: list[float], period: int) -> list[float | None]:
        result: list[float | None] = [None] * (period - 1)
        for i in range(period - 1, len(values)):
            weight_sum = 0.0
            weighted_sum = 0.0
            for j in range(period):
                weight = j + 1
                weighted_sum += values[i - period + 1 + j] * weight
                weight_sum += weight
            result.append(weighted_sum / weight_sum if weight_sum > 0 else None)
        return result

    @staticmethod
    def hma(values: list[float], period: int) -> list[float | None]:
        half = period // 2
        sqrt_n = int(math.sqrt(period))
        wma_half = IndicatorMath.wma(values, half)
        wma_full = IndicatorMath.wma(values, period)
        diff: list[float] = []
        for wh, wf in zip(wma_half, wma_full):
            wh_val = wh if wh is not None else 0.0
            wf_val = wf if wf is not None else 0.0
            diff.append(2 * wh_val - wf_val)
        return IndicatorMath.wma(diff, sqrt_n)

    @staticmethod
    def trima(values: list[float], period: int) -> list[float | None]:
        result: list[float | None] = [None] * (period - 1)
        for i in range(period - 1, len(values)):
            if period % 2 == 1:
                mid = (period + 1) // 2
                start = i - period + 1
                sma_mid = sum(values[start + (mid - 1):start + period - (mid - 1)]) / mid
                result.append(sma_mid)
            else:
                mid1 = period // 2
                mid2 = mid1 + 1
                start = i - period + 1
                sma1 = sum(values[start + mid1 - 1:i]) / mid1
                sma2 = sum(values[start + mid2 - 1:i + 1]) / mid2
                result.append((sma1 + sma2) / 2)
        return result

    @staticmethod
    def _tsf(values: list[float], period: int) -> list[float | None]:
        result: list[float | None] = [None] * (period - 1)
        for i in range(period - 1, len(values)):
            x = list(range(period))
            y = values[i - period + 1:i + 1]
            n = period
            sum_x = sum(x)
            sum_y = sum(y)
            sum_xy = sum(xi * yi for xi, yi in zip(x, y))
            sum_x2 = sum(xi * xi for xi in x)
            denom = n * sum_x2 - sum_x * sum_x
            if denom == 0:
                result.append(None)
            else:
                slope = (n * sum_xy - sum_x * sum_y) / denom
                intercept = (sum_y - slope * sum_x) / n
                result.append(intercept + slope * (period))
        return result

    @staticmethod
    def kama(values: list[float], period: int = 10, fast: int = 2, slow: int = 30) -> list[float | None]:
        n = len(values)
        if n < period:
            return [None] * n
        result: list[float | None] = [None] * (period - 1)
        kama_val = sum(values[:period]) / period
        result.append(kama_val)
        fast_sc = 2.0 / (fast + 1)
        slow_sc = 2.0 / (slow + 1)
        for i in range(period, n):
            price_change = abs(values[i] - values[i - period])
            volatility = sum(abs(values[j] - values[j - 1]) for j in range(i - period + 1, i + 1))
            er = price_change / volatility if volatility > 0 else 0.0
            sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
            kama_val = kama_val + sc * (values[i] - kama_val)
            result.append(kama_val)
        return result

    @staticmethod
    def mama(values: list[float], fast_limit: float = 0.5, slow_limit: float = 0.05) -> list[float | None]:
        n = len(values)
        if n < 4:
            return [None] * n
        mama_val = values[0]
        fama_val = values[0]
        result_mama: list[float | None] = [None] * 3
        result_fama: list[float | None] = [None] * 3
        result_mama.append(mama_val)
        result_fama.append(fama_val)
        for i in range(4, n):
            signal = (2 * values[i - 3] - values[i - 2] + values[i - 1] - 2 * values[i] + values[i - 3]) / 6
            if signal != 0:
                phase = abs(math.atan(values[i] - values[i - 1]))
            else:
                phase = 0
            if phase > 1.0:
                phase = 1.0
            if phase < 0.0:
                phase = 0.0
            alpha = fast_limit + (slow_limit - fast_limit) * (1.0 - phase)
            mama_val = alpha * values[i] + (1 - alpha) * mama_val
            fama_val = 0.5 * alpha * mama_val + (1 - 0.5 * alpha) * fama_val
            result_mama.append(mama_val)
            result_fama.append(fama_val)
        return result_mama

    @staticmethod
    def cci(high: list[float], low: list[float], close: list[float], period: int = 20) -> list[float | None]:
        tp = [(h + l + c) / 3 for h, l, c in zip(high, low, close)]
        sma_tp = IndicatorMath.sma(tp, period)
        result: list[float | None] = [None] * (period - 1)
        for i in range(period - 1, len(tp)):
            slice_tp = tp[i - period + 1:i + 1]
            mean_tp = sma_tp[i]
            mad = sum(abs(x - mean_tp) for x in slice_tp) / period
            if mad == 0:
                result.append(0.0)
            else:
                result.append((tp[i] - mean_tp) / (0.015 * mad))
        return result

    @staticmethod
    def williams_r(high: list[float], low: list[float], close: list[float], period: int = 14) -> list[float | None]:
        result: list[float | None] = [None] * (period - 1)
        for i in range(period - 1, len(close)):
            hh = max(high[i - period + 1:i + 1])
            ll = min(low[i - period + 1:i + 1])
            if hh - ll == 0:
                result.append(-50.0)
            else:
                result.append(-100.0 * (hh - close[i]) / (hh - ll))
        return result

    @staticmethod
    def stoch_k(high: list[float], low: list[float], close: list[float], k_period: int = 14, d_period: int = 3) -> tuple[list[float | None], list[float | None]]:
        k_raw: list[float | None] = [None] * (k_period - 1)
        for i in range(k_period - 1, len(close)):
            hh = max(high[i - k_period + 1:i + 1])
            ll = min(low[i - k_period + 1:i + 1])
            if hh - ll == 0:
                k_raw.append(50.0)
            else:
                k_raw.append(100.0 * (close[i] - ll) / (hh - ll))
        k_values = [v if v is not None else 50.0 for v in k_raw]
        k_smooth = IndicatorMath.sma(k_values, d_period)
        d_smooth = IndicatorMath.sma([v if v is not None else 50.0 for v in k_smooth], d_period)
        return k_smooth, d_smooth

    @staticmethod
    def obv(close: list[float], volume: list[int]) -> list[float]:
        result: list[float] = [float(volume[0])]
        for i in range(1, len(close)):
            if close[i] > close[i - 1]:
                result.append(result[-1] + volume[i])
            elif close[i] < close[i - 1]:
                result.append(result[-1] - volume[i])
            else:
                result.append(result[-1])
        return result

    @staticmethod
    def volume_profile(volume: list[int], close: list[float], num_bins: int = 10) -> dict[str, Any]:
        if not volume:
            return {}
        min_price = min(close)
        max_price = max(close)
        bin_size = (max_price - min_price) / num_bins if max_price > min_price else 1
        bins: dict[int, float] = {}
        for c, v in zip(close, volume):
            bin_idx = int((c - min_price) / bin_size) if bin_size > 0 else 0
            bin_idx = min(bin_idx, num_bins - 1)
            bins[bin_idx] = bins.get(bin_idx, 0) + v
        poc_bin = max(bins, key=bins.get) if bins else 0
        poc_price = min_price + (poc_bin + 0.5) * bin_size
        return {
            "min_price": round(min_price, 2), "max_price": round(max_price, 2),
            "bin_size": round(bin_size, 4), "bins": bins,
            "point_of_control": round(poc_price, 2),
            "total_volume": sum(volume),
        }

    @staticmethod
    def psar(high: list[float], low: list[float], accel_start: float = 0.02, accel_max: float = 0.2) -> list[float | None]:
        n = len(high)
        if n < 2:
            return [None] * n
        result: list[float | None] = [None]
        is_up = high[1] > high[0]
        ep = high[0] if is_up else low[0]
        sar = low[0] if is_up else high[0]
        af = accel_start
        for i in range(1, n):
            sar = sar + af * (ep - sar)
            if is_up:
                sar = min(sar, low[i - 1], low[i - 2] if i >= 2 else low[i - 1])
                if low[i] < sar:
                    is_up = False
                    sar = ep
                    ep = low[i]
                    af = accel_start
                else:
                    if high[i] > ep:
                        ep = high[i]
                        af = min(af + accel_start, accel_max)
            else:
                sar = max(sar, high[i - 1], high[i - 2] if i >= 2 else high[i - 1])
                if high[i] > sar:
                    is_up = True
                    sar = ep
                    ep = high[i]
                    af = accel_start
                else:
                    if low[i] < ep:
                        ep = low[i]
                        af = min(af + accel_start, accel_max)
            result.append(sar)
        return result

    @staticmethod
    def roc(values: list[float], period: int = 12) -> list[float | None]:
        result: list[float | None] = [None] * period
        for i in range(period, len(values)):
            result.append(((values[i] - values[i - period]) / values[i - period]) * 100 if values[i - period] != 0 else None)
        return result

    @staticmethod
    def cmf(high: list[float], low: list[float], close: list[float], volume: list[int], period: int = 20) -> list[float | None]:
        mfv: list[float] = []
        for h, l, c, v in zip(high, low, close, volume):
            hl = h - l
            cl = c - l
            mf = ((cl - (hl - cl)) / hl * v) if hl > 0 else 0.0
            mfv.append(mf)
        result: list[float | None] = [None] * (period - 1)
        for i in range(period - 1, len(mfv)):
            sum_mf = sum(mfv[i - period + 1:i + 1])
            sum_v = sum(volume[i - period + 1:i + 1])
            result.append(sum_mf / sum_v if sum_v > 0 else 0.0)
        return result

    @staticmethod
    def keltner_channels(high: list[float], low: list[float], close: list[float], period: int = 20, multiplier: float = 2.0) -> tuple[list[float | None], list[float | None], list[float | None]]:
        middle = IndicatorMath.ema(close, period)
        atr_vals = IndicatorMath.atr(high, low, close, period)
        upper: list[float | None] = []
        lower: list[float | None] = []
        for m, a in zip(middle, atr_vals):
            if m is not None and a is not None:
                upper.append(m + multiplier * a)
                lower.append(m - multiplier * a)
            else:
                upper.append(None)
                lower.append(None)
        return upper, middle, lower


register_indicator("SMA", "moving_average", "Simple Moving Average", {"period": 20})
register_indicator("EMA", "moving_average", "Exponential Moving Average", {"period": 20})
register_indicator("WMA", "moving_average", "Weighted Moving Average", {"period": 20})
register_indicator("HMA", "moving_average", "Hull Moving Average", {"period": 20})
register_indicator("TRIMA", "moving_average", "Triangular Moving Average", {"period": 20})
register_indicator("KAMA", "moving_average", "Kaufman Adaptive Moving Average", {"period": 10, "fast": 2, "slow": 30})
register_indicator("MAMA", "moving_average", "MESA Adaptive Moving Average", {"fast_limit": 0.5, "slow_limit": 0.05})
register_indicator("RSI", "oscillator", "Relative Strength Index", {"period": 14})
register_indicator("MACD", "oscillator", "MACD", {"fast": 12, "slow": 26, "signal": 9})
register_indicator("STOCH", "oscillator", "Stochastic Oscillator", {"k_period": 14, "d_period": 3})
register_indicator("WILLIAMS_R", "oscillator", "Williams %R", {"period": 14})
register_indicator("CCI", "oscillator", "Commodity Channel Index", {"period": 20})
register_indicator("BBANDS", "volatility", "Bollinger Bands", {"period": 20, "std_dev": 2.0})
register_indicator("ATR", "volatility", "Average True Range", {"period": 14})
register_indicator("KC", "volatility", "Keltner Channels", {"period": 20, "multiplier": 2.0})
register_indicator("ADX", "trend", "Average Directional Index", {"period": 14})
register_indicator("PSAR", "trend", "Parabolic SAR", {"accel_start": 0.02, "accel_max": 0.2})
register_indicator("VWAP", "volume", "Volume-Weighted Average Price", {})
register_indicator("OBV", "volume", "On-Balance Volume", {})
register_indicator("CMF", "volume", "Chaikin Money Flow", {"period": 20})
register_indicator("ROC", "momentum", "Rate of Change", {"period": 12})
register_indicator("VOLUME_PROFILE", "volume", "Volume Profile", {"num_bins": 10})

COMPUTATION_MAP: dict[str, dict[str, Any]] = {
    "SMA": {"func": IndicatorMath.sma, "inputs": ["close"], "outputs": ["value"]},
    "EMA": {"func": IndicatorMath.ema, "inputs": ["close"], "outputs": ["value"]},
    "WMA": {"func": IndicatorMath.wma, "inputs": ["close"], "outputs": ["value"]},
    "HMA": {"func": IndicatorMath.hma, "inputs": ["close"], "outputs": ["value"]},
    "TRIMA": {"func": IndicatorMath.trima, "inputs": ["close"], "outputs": ["value"]},
    "KAMA": {"func": IndicatorMath.kama, "inputs": ["close"], "outputs": ["value"]},
    "MAMA": {"func": IndicatorMath.mama, "inputs": ["close"], "outputs": ["value"]},
    "RSI": {"func": IndicatorMath.rsi, "inputs": ["close"], "outputs": ["value"]},
    "MACD": {"func": IndicatorMath.macd, "inputs": ["close"], "outputs": ["value", "value_secondary", "value_tertiary"]},
    "BBANDS": {"func": IndicatorMath.bollinger_bands, "inputs": ["close"], "outputs": ["value", "value_secondary", "value_tertiary"]},
    "ATR": {"func": IndicatorMath.atr, "inputs": ["high", "low", "close"], "outputs": ["value"]},
    "ADX": {"func": IndicatorMath.adx, "inputs": ["high", "low", "close"], "outputs": ["value", "value_secondary", "value_tertiary"]},
    "VWAP": {"func": IndicatorMath.vwap, "inputs": ["high", "low", "close", "volume"], "outputs": ["value"]},
    "STOCH": {"func": IndicatorMath.stoch_k, "inputs": ["high", "low", "close"], "outputs": ["value", "value_secondary"]},
    "WILLIAMS_R": {"func": IndicatorMath.williams_r, "inputs": ["high", "low", "close"], "outputs": ["value"]},
    "CCI": {"func": IndicatorMath.cci, "inputs": ["high", "low", "close"], "outputs": ["value"]},
    "OBV": {"func": IndicatorMath.obv, "inputs": ["close", "volume"], "outputs": ["value"]},
    "CMF": {"func": IndicatorMath.cmf, "inputs": ["high", "low", "close", "volume"], "outputs": ["value"]},
    "ROC": {"func": IndicatorMath.roc, "inputs": ["close"], "outputs": ["value"]},
    "KC": {"func": IndicatorMath.keltner_channels, "inputs": ["high", "low", "close"], "outputs": ["value", "value_secondary", "value_tertiary"]},
    "PSAR": {"func": IndicatorMath.psar, "inputs": ["high", "low"], "outputs": ["value"]},
    "VOLUME_PROFILE": {"func": IndicatorMath.volume_profile, "inputs": ["close", "volume"], "outputs": ["value"]},
}


def _params_hash(indicator: str, params: dict[str, Any]) -> str:
    raw = indicator + "|" + json.dumps(params, sort_keys=True, default=str)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


class TechnicalIndicatorEngine:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = BaseRepository(session, TechnicalIndicator)

    def list_indicators(self) -> list[dict[str, Any]]:
        return list(INDICATOR_REGISTRY.values())

    async def compute(
        self, symbol: str, indicator: str, params: dict[str, Any] | None = None,
        store: bool = True,
    ) -> list[dict[str, Any]]:
        symbol = symbol.upper()
        indicator = indicator.upper()
        params = params or {}

        spec = COMPUTATION_MAP.get(indicator)
        if spec is None:
            raise ValueError(f"Unknown indicator: {indicator}. Available: {', '.join(COMPUTATION_MAP.keys())}")

        prices = await self._session.execute(
            select(DailyPrice)
            .where(DailyPrice.symbol == symbol)
            .order_by(DailyPrice.trade_date.asc())
        )
        all_prices: list[DailyPrice] = list(prices.scalars().all())
        if not all_prices:
            return []

        close = [p.close for p in all_prices]
        high = [p.high for p in all_prices]
        low = [p.low for p in all_prices]
        volume = [p.volume for p in all_prices]
        dates = [p.trade_date for p in all_prices]

        full_params = dict(INDICATOR_REGISTRY[indicator]["default_params"])
        full_params.update(params)
        input_args = self._build_input_args(spec["inputs"], high=high, low=low, close=close, volume=volume, **full_params)
        result = spec["func"](**input_args)

        if indicator == "VOLUME_PROFILE" and isinstance(result, dict):
            out = [{"trade_date": str(dates[-1]) if dates else "", "indicator": indicator, "params": full_params, "metadata_json": json.dumps(result)}]
            if store:
                ph = _params_hash(indicator, full_params)
                existing = await self._session.execute(
                    select(TechnicalIndicator).where(
                        TechnicalIndicator.symbol == symbol,
                        TechnicalIndicator.indicator == indicator,
                        TechnicalIndicator.params_hash == ph,
                        TechnicalIndicator.trade_date == dates[-1],
                    )
                )
                if existing.scalar_one_or_none() is None:
                    ti = TechnicalIndicator(
                        symbol=symbol, trade_date=dates[-1],
                        indicator=indicator, params_hash=ph,
                        period=full_params.get("period"),
                        params=json.dumps(full_params),
                        metadata_json=json.dumps(result),
                    )
                    self._session.add(ti)
                    await self._session.flush()
            return out

        output_fields = spec["outputs"]
        results_list: list[dict[str, Any]] = []
        ph = _params_hash(indicator, full_params) if store else ""

        if isinstance(result, tuple):
            result_lists = list(result)
        else:
            result_lists = [result]

        for i in range(len(dates)):
            row: dict[str, Any] = {
                "trade_date": dates[i].isoformat(),
                "indicator": indicator,
            }

            stored_row: dict[str, Any] = {}
            for field_name, rl in zip(output_fields, result_lists):
                if i < len(rl):
                    val = rl[i]
                    row[field_name] = val
                    stored_row[field_name] = val if val is not None else None

            if store and any(stored_row.get(f) is not None for f in output_fields if f != "value_tertiary") and indicator != "VOLUME_PROFILE":
                existing = await self._session.execute(
                    select(TechnicalIndicator).where(
                        TechnicalIndicator.symbol == symbol,
                        TechnicalIndicator.indicator == indicator,
                        TechnicalIndicator.params_hash == ph,
                        TechnicalIndicator.trade_date == dates[i],
                    )
                )
                if existing.scalar_one_or_none() is None:
                    ti = TechnicalIndicator(
                        symbol=symbol, trade_date=dates[i],
                        indicator=indicator, params_hash=ph,
                        period=full_params.get("period"),
                        params=json.dumps(full_params),
                        value=stored_row.get("value"),
                        value_secondary=stored_row.get("value_secondary"),
                        value_tertiary=stored_row.get("value_tertiary"),
                    )
                    self._session.add(ti)

            results_list.append(row)

        if store:
            await self._session.flush()

        return results_list

    async def get_stored(
        self, symbol: str, indicator: str, *,
        period: int | None = None, date_from: date | None = None, date_to: date | None = None,
        skip: int = 0, limit: int = 500,
    ) -> tuple[Sequence[TechnicalIndicator], int]:
        symbol = symbol.upper()
        stmt = select(TechnicalIndicator).where(
            TechnicalIndicator.symbol == symbol,
            TechnicalIndicator.indicator == indicator.upper(),
        )
        if period is not None:
            stmt = stmt.where(TechnicalIndicator.period == period)
        if date_from:
            stmt = stmt.where(TechnicalIndicator.trade_date >= date_from)
        if date_to:
            stmt = stmt.where(TechnicalIndicator.trade_date <= date_to)

        count_result = await self._session.execute(stmt)
        total = len(count_result.scalars().all())
        stmt = stmt.order_by(TechnicalIndicator.trade_date.desc()).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    async def delete_stored(self, indicator_id: int) -> bool:
        return await self._repo.delete(indicator_id)

    def _build_input_args(self, inputs: list[str], **kwargs: Any) -> dict[str, Any]:
        arg_map: dict[str, Any] = {}
        for inp in inputs:
            if inp in kwargs:
                arg_map[inp] = kwargs[inp]
        for k, v in kwargs.items():
            if k not in ("high", "low", "close", "volume", "inputs"):
                arg_map[k] = v
        return arg_map
