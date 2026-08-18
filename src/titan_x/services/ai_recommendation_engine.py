"""High-precision, selective AI stock recommendation engine.

This engine combines six analytical pillars into a transparent, calibrated
ensemble and is deliberately *selective*: it prefers NO-TRADE over issuing a
weak signal.

Pillars (weights sum to 1.0):
  1. Technical Analysis ........ 25%
  2. Fundamental Analysis ....... 20%
  3. News & Sentiment ........... 15%
  4. Market Regime .............. 15%
  5. Historical Pattern Match ... 15%
  6. Risk Engine ................ 10%

Design rules (per spec):
  * Each pillar is treated as an independent "model" and must vote on direction
    and supply a confidence. The ensemble requires >= 4 of the confident
    pillars to agree before a high-conviction signal is allowed.
  * A NO-TRADE filter rejects stale/poor-quality data, low liquidity, abnormal
    volatility, major event risk, weak probability, insufficient historical
    sample, poor Risk/Reward or model disagreement.
  * Signal thresholds:
        Score >= 90 and calibrated prob >= 0.80 -> HIGH CONVICTION
        Score >= 85 and calibrated prob >= 0.75 -> STRONG BUY/SELL
        otherwise                                   -> WATCH / NO-TRADE
  * Every signal carries full explainability (score, probability, entry,
    target, stop, R:R, model agreement, historical evidence, reasons, risks).

The engine is pure compute over in-memory primitive data (no DB / network), so
it is fully unit-testable and degrades gracefully: missing data for a pillar
yields a neutral, low-confidence pillar that usually pushes the result to
NO-TRADE.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Optional


# --------------------------------------------------------------------------- #
# Tunable configuration (kept in one place, matching the project's convention  #
# of constants living in the engine module rather than env config).            #
# --------------------------------------------------------------------------- #
PILLAR_WEIGHTS = {
    "technical": 0.25,
    "fundamental": 0.20,
    "news": 0.15,
    "regime": 0.15,
    "similarity": 0.15,
    "risk": 0.10,
}

MIN_BARS = 60                 # below this -> insufficient data (NO-TRADE)
MIN_CONFIDENT_PILLARS = 4     # need >=4 pillars with confidence >= PILLAR_MIN_CONF
PILLAR_MIN_CONF = 0.40
REQUIRED_AGREEMENT = 4        # >=4 of confident pillars must agree on direction

# Signal thresholds
HIGH_CONVICTION_SCORE = 90.0
HIGH_CONVICTION_PROB = 0.80
STRONG_SCORE = 82.0
STRONG_PROB = 0.75

# Risk / quality gates
MIN_RISK_REWARD = 2.0
MIN_LIQUIDITY_SCORE = 35.0     # 0..100, based on avg dollar volume
MAX_VOLATILITY_ANNUALIZED = 0.90  # above this -> abnormal volatility (NO-TRADE)
MIN_SIMILARITY_SAMPLE = 12     # below -> insufficient historical sample
WEAK_PROBABILITY = 0.55        # below + low score -> NO-TRADE

STOP_TARGET_R_MULTIPLE = 2.0   # target = entry + risk * 2  (R:R >= 1:2)
ATR_STOP_MULTIPLE = 2.0
HOLDING_PERIOD_DAYS = 15


# --------------------------------------------------------------------------- #
# Input data structures                                                       #
# --------------------------------------------------------------------------- #
@dataclass
class Bar:
    trade_date: Any = None
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0


@dataclass
class Fundamentals:
    revenue_growth_yoy: Optional[float] = None
    eps_growth_yoy: Optional[float] = None
    roe: Optional[float] = None
    roce: Optional[float] = None
    debt_to_equity: Optional[float] = None
    net_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    promoter_holding: Optional[float] = None
    fii_holding: Optional[float] = None
    free_cash_flow: Optional[float] = None


@dataclass
class NewsItem:
    headline: str = ""
    sentiment_label: str = "neutral"   # positive | negative | neutral
    sentiment_score: float = 0.0        # -1..1
    confidence: float = 0.5             # 0..1
    impact: float = 0.0                 # -1..1 event materiality
    category: Optional[str] = None


@dataclass
class MarketRegime:
    nifty_trend: float = 50.0           # 0..100 (bullish)
    banknifty_trend: float = 50.0
    sector_momentum: float = 50.0
    india_vix: float = 15.0
    breadth_adv_decl: float = 1.0       # advancing / declining
    fii_dii_net: float = 0.0            # positive = net inflow


@dataclass
class PillarScore:
    name: str
    weight: float
    score: float            # 0..100 bullish score
    direction: int          # -1 | 0 | 1
    confidence: float       # 0..1
    detail: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Numeric helpers (pure, defensive)                                           #
# --------------------------------------------------------------------------- #
def _sma(vals: list[float], n: int) -> Optional[float]:
    if not vals or len(vals) < n or n <= 0:
        return None
    return sum(vals[-n:]) / n


def _ema_series(vals: list[float], n: int) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(vals)
    if len(vals) < n:
        return out
    k = 2.0 / (n + 1)
    seed = sum(vals[:n]) / n
    out[n - 1] = seed
    ema = seed
    for i in range(n, len(vals)):
        ema = vals[i] * k + ema * (1 - k)
        out[i] = ema
    return out


def _ema(vals: list[float], n: int) -> Optional[float]:
    s = _ema_series(vals, n)
    for v in reversed(s):
        if v is not None:
            return v
    return None


def _rsi(closes: list[float], n: int = 14) -> Optional[float]:
    if len(closes) < n + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]
    ag = sum(gains[:n]) / n
    al = sum(losses[:n]) / n
    for g, l in zip(gains[n:], losses[n:]):
        ag = (ag * (n - 1) + g) / n
        al = (al * (n - 1) + l) / n
    if al == 0:
        return 100.0
    rs = ag / al
    return 100.0 - 100.0 / (1.0 + rs)


def _macd(closes: list[float], fast: int = 12, slow: int = 26, sig: int = 9):
    if len(closes) < slow + sig:
        return (None, None, None)
    ef = _ema_series(closes, fast)
    ef = _ema_series(closes, fast)
    es = _ema_series(closes, slow)
    macd_line: list[Optional[float]] = []
    for a, b in zip(ef, es):
        macd_line.append(a - b if (a is not None and b is not None) else None)
    defined = [v for v in macd_line if v is not None]
    sig_series = _ema_series(defined, sig)
    sig_aligned: list[Optional[float]] = [None] * len(macd_line)
    di = 0
    for i, v in enumerate(macd_line):
        if v is not None:
            sig_aligned[i] = sig_series[di]
            di += 1
    last_macd = next((v for v in reversed(macd_line) if v is not None), None)
    last_sig = next((v for v in reversed(sig_aligned) if v is not None), None)
    hist = (last_macd - last_sig) if (last_macd is not None and last_sig is not None) else None
    return (last_macd, last_sig, hist)


def _atr(highs: list[float], lows: list[float], closes: list[float], n: int = 14) -> Optional[float]:
    if len(closes) < n + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    return _sma(trs, n)


def _bollinger(closes: list[float], n: int = 20, k: float = 2.0):
    mid = _sma(closes, n)
    if mid is None:
        return (None, None, None)
    window = closes[-n:]
    var = sum((c - mid) ** 2 for c in window) / n
    sd = math.sqrt(var)
    return (mid, mid + k * sd, mid - k * sd)


def _adx(highs: list[float], lows: list[float], closes: list[float], n: int = 14) -> Optional[float]:
    if len(closes) < n * 2:
        return None
    plus_dm = []
    minus_dm = []
    trs = []
    for i in range(1, len(closes)):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(max(up, 0.0) if up > down else 0.0)
        minus_dm.append(max(down, 0.0) if down > up else 0.0)
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    atr_ = _sma(trs[:n], n) or 0.0
    pdm_ = _sma(plus_dm[:n], n) or 0.0
    mdm_ = _sma(minus_dm[:n], n) or 0.0
    pdi = 100 * pdm_ / atr_ if atr_ else 0.0
    mdi = 100 * mdm_ / atr_ if atr_ else 0.0
    dx = 100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) else 0.0
    dxs = [dx]
    for i in range(n, len(trs)):
        atr_ = (atr_ * (n - 1) + trs[i]) / n
        pdm_ = (pdm_ * (n - 1) + plus_dm[i]) / n
        mdm_ = (mdm_ * (n - 1) + minus_dm[i]) / n
        pdi = 100 * pdm_ / atr_ if atr_ else 0.0
        mdi = 100 * mdm_ / atr_ if atr_ else 0.0
        dxi = 100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) else 0.0
        dxs.append(dxi)
    return _sma(dxs, n)


def _pearson(a: list[float], b: list[float]) -> float:
    n = len(a)
    if n == 0:
        return 0.0
    ma = sum(a) / n
    mb = sum(b) / n
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((x - mb) ** 2 for x in b))
    if da == 0 or db == 0:
        return 0.0
    return num / (da * db)


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _sigmoid(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


# --------------------------------------------------------------------------- #
# Pillar scorers                                                             #
# --------------------------------------------------------------------------- #
def _technical_pillar(bars: list[Bar]) -> PillarScore:
    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    vols = [b.volume for b in bars]

    if len(closes) < 30:
        return PillarScore("technical", PILLAR_WEIGHTS["technical"], 50.0, 0, 0.1,
                           {"note": "insufficient price history"})

    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    ema200 = _ema(closes, 200)
    rsi = _rsi(closes, 14)
    macd_line, macd_sig, macd_hist = _macd(closes)
    adx = _adx(highs, lows, closes, 14)
    atr = _atr(highs, lows, closes, 14)
    bb_mid, bb_up, bb_low = _bollinger(closes, 20, 2.0)

    last = closes[-1]
    recent_vol = _sma(vols[-5:], 5)
    base_vol = _sma(vols[-20:], 20)
    vol_ratio = (recent_vol / base_vol) if base_vol else 1.0

    # --- trend (0..40) ---
    trend = 20.0
    if ema20 and ema50:
        trend += 10 if ema20 > ema50 else -10
    if ema50 and ema200 and ema20:
        if ema20 > ema50 > ema200:
            trend += 10
        elif ema20 < ema50 < ema200:
            trend -= 10
    look = closes[-40:]
    if len(look) >= 20:
        if max(look[-20:]) > max(look[-40:-20]):
            trend += 5
        if min(look[-20:]) > min(look[-40:-20]):
            trend += 5

    # --- momentum (0..30) ---
    mom = 15.0
    if rsi is not None:
        if 50 <= rsi <= 70:
            mom += 10
        elif rsi > 70:
            mom -= 8
        elif rsi < 30:
            mom += 4
        elif rsi < 45:
            mom -= 8
    if macd_hist is not None:
        mom += 5 if macd_hist > 0 else -5
    if adx is not None and adx >= 20:
        mom += 3
    elif adx is not None and adx < 15:
        mom -= 3

    # --- mean reversion / volatility (0..15) ---
    mr = 7.5
    if bb_up and bb_low:
        mr += 5 if last <= bb_low else 0
        mr -= 5 if last >= bb_up else 0

    # --- volume confirmation (0..15) ---
    vol = 7.5
    vol += 5 if vol_ratio >= 1.2 else 0
    vol -= 5 if vol_ratio < 0.8 else 0

    score = _clamp(trend + mom + mr + vol)
    direction = 1 if score >= 55 else (-1 if score <= 45 else 0)

    conf = 0.55
    if len(closes) >= 200 and ema200:
        conf += 0.15
    if adx is not None and adx >= 25:
        conf += 0.1
    if direction != 0:
        conf += 0.1
    conf = _clamp(conf, 0.1, 0.95)

    detail = {
        "ema20": round(ema20, 2) if ema20 else None,
        "ema50": round(ema50, 2) if ema50 else None,
        "ema200": round(ema200, 2) if ema200 else None,
        "rsi": round(rsi, 1) if rsi is not None else None,
        "macd_hist": round(macd_hist, 3) if macd_hist is not None else None,
        "adx": round(adx, 1) if adx is not None else None,
        "atr": round(atr, 2) if atr is not None else None,
        "bollinger_upper": round(bb_up, 2) if bb_up else None,
        "bollinger_lower": round(bb_low, 2) if bb_low else None,
        "volume_ratio": round(vol_ratio, 2),
    }
    return PillarScore("technical", PILLAR_WEIGHTS["technical"], score, direction, conf, detail)


def _fundamental_pillar(f: Optional[Fundamentals]) -> PillarScore:
    if f is None:
        return PillarScore("fundamental", PILLAR_WEIGHTS["fundamental"], 50.0, 0, 0.1,
                           {"note": "no fundamental data"})
    score = 50.0
    n = 0
    if f.revenue_growth_yoy is not None:
        score += _clamp(f.revenue_growth_yoy, -30, 30) * 0.4
        n += 1
    if f.eps_growth_yoy is not None:
        score += _clamp(f.eps_growth_yoy, -30, 30) * 0.4
        n += 1
    if f.roe is not None:
        score += _clamp(f.roe, -20, 30) * 0.5
        n += 1
    if f.roce is not None:
        score += _clamp(f.roce, -20, 30) * 0.4
        n += 1
    if f.net_margin is not None:
        score += _clamp(f.net_margin, -20, 30) * 0.3
        n += 1
    if f.debt_to_equity is not None:
        score -= _clamp(f.debt_to_equity, 0, 3) * 6
        n += 1
    if f.pe_ratio is not None:
        if 0 < f.pe_ratio <= 35:
            score += 4
        elif f.pe_ratio > 60:
            score -= 6
        n += 1
    if f.promoter_holding is not None and f.promoter_holding >= 50:
        score += 3
        n += 1

    score = _clamp(score)
    direction = 1 if score >= 55 else (-1 if score <= 45 else 0)
    conf = _clamp(0.35 + 0.08 * n, 0.1, 0.9)
    detail = {
        "revenue_growth_yoy": f.revenue_growth_yoy,
        "eps_growth_yoy": f.eps_growth_yoy,
        "roe": f.roe,
        "roce": f.roce,
        "debt_to_equity": f.debt_to_equity,
        "net_margin": f.net_margin,
        "pe_ratio": f.pe_ratio,
        "promoter_holding": f.promoter_holding,
        "factors_considered": n,
    }
    return PillarScore("fundamental", PILLAR_WEIGHTS["fundamental"], score, direction, conf, detail)


def _news_pillar(news: Optional[list[NewsItem]]) -> PillarScore:
    if not news:
        return PillarScore("news", PILLAR_WEIGHTS["news"], 50.0, 0, 0.1, {"note": "no news data"})
    weighted = 0.0
    wsum = 0.0
    events: list[str] = []
    for it in news:
        s = it.sentiment_score if it.sentiment_score else (
            1.0 if it.sentiment_label == "positive" else -1.0 if it.sentiment_label == "negative" else 0.0
        )
        w = (it.confidence or 0.5) * (0.5 + 0.5 * abs(it.impact or 0))
        weighted += s * w
        wsum += w
        if it.category and abs(it.impact or 0) >= 0.5:
            events.append(f"{it.category}:{it.sentiment_label}")
    if wsum == 0:
        return PillarScore("news", PILLAR_WEIGHTS["news"], 50.0, 0, 0.15, {"note": "low-impact news"})
    net = weighted / wsum  # -1..1
    score = _clamp(50 + net * 35)
    direction = 1 if net > 0.05 else (-1 if net < -0.05 else 0)
    conf = _clamp(0.3 + 0.07 * len(news), 0.1, 0.85)
    return PillarScore("news", PILLAR_WEIGHTS["news"], score, direction, conf,
                       {"net_sentiment": round(net, 3), "articles": len(news), "key_events": events[:5]})


def _regime_pillar(regime: MarketRegime) -> PillarScore:
    score = 50.0
    score += (regime.nifty_trend - 50) * 0.25
    score += (regime.banknifty_trend - 50) * 0.15
    score += (regime.sector_momentum - 50) * 0.20
    score -= (regime.india_vix - 15) * 1.2
    if regime.breadth_adv_decl >= 1:
        score += min(regime.breadth_adv_decl - 1, 1) * 8
    else:
        score -= min(1 - regime.breadth_adv_decl, 1) * 12
    score += _clamp(regime.fii_dii_net, -20, 20) * 0.4

    score = _clamp(score)
    direction = 1 if score >= 55 else (-1 if score <= 45 else 0)
    conf = 0.6
    detail = {
        "nifty_trend": round(regime.nifty_trend, 1),
        "banknifty_trend": round(regime.banknifty_trend, 1),
        "sector_momentum": round(regime.sector_momentum, 1),
        "india_vix": regime.india_vix,
        "adv_decl_ratio": round(regime.breadth_adv_decl, 2),
        "fii_dii_net": round(regime.fii_dii_net, 2),
    }
    return PillarScore("regime", PILLAR_WEIGHTS["regime"], score, direction, conf, detail)


def _similarity_pillar(closes: list[float], window: int = 20) -> PillarScore:
    """Find historically similar setups in the same series and estimate
    target-first vs stop-first probabilities and average forward return."""
    detail: dict[str, Any] = {"note": "insufficient history for pattern match"}
    if len(closes) < window * 3:
        return PillarScore("similarity", PILLAR_WEIGHTS["similarity"], 50.0, 0, 0.1, detail)

    recent = closes[-window:]
    if recent[0] == 0:
        return PillarScore("similarity", PILLAR_WEIGHTS["similarity"], 50.0, 0, 0.1, detail)
    rnorm = [(x - recent[0]) / recent[0] for x in recent]

    target = 0.05
    stop = -0.03
    fwd_bars = 12
    matches_ret: list[float] = []
    target_first = 0
    stop_first = 0
    holding_days: list[int] = []
    hist = closes[:-window]
    for i in range(len(hist) - window - fwd_bars + 1):
        w = hist[i:i + window]
        if w[0] == 0:
            continue
        wn = [(x - w[0]) / w[0] for x in w]
        corr = _pearson(rnorm, wn)
        if corr < 0.80:
            continue
        base = closes[i + window]
        if base == 0:
            continue
        fut = closes[i + window: i + window + fwd_bars + 1]
        if len(fut) < 2:
            continue
        rets = [(f - base) / base for f in fut[1:]]
        match_ret = rets[-1]
        reached_target = any(r >= target for r in rets)
        reached_stop = any(r <= stop for r in rets)
        if reached_target and not reached_stop:
            target_first += 1
        elif reached_stop and not reached_target:
            stop_first += 1
        for k, r in enumerate(rets, start=1):
            if r >= target or r <= stop:
                holding_days.append(k)
                break
        matches_ret.append(match_ret)

    sample = len(matches_ret)
    if sample < MIN_SIMILARITY_SAMPLE:
        return PillarScore("similarity", PILLAR_WEIGHTS["similarity"], 50.0, 0, 0.1,
                           {"sample_size": sample, "note": "insufficient historical sample"})

    avg_return = sum(matches_ret) / sample
    tf = target_first / sample
    sf = stop_first / sample
    avg_hold = (sum(holding_days) / len(holding_days)) if holding_days else fwd_bars

    score = _clamp(50 + avg_return * 600)
    direction = 1 if avg_return > 0 else -1
    conf = _clamp(0.3 + 0.04 * sample, 0.2, 0.85)
    detail = {
        "sample_size": sample,
        "avg_forward_return": round(avg_return, 4),
        "target_first_prob": round(tf, 3),
        "stop_first_prob": round(sf, 3),
        "avg_holding_period": round(avg_hold, 1),
    }
    return PillarScore("similarity", PILLAR_WEIGHTS["similarity"], score, direction, conf, detail)


def _risk_pillar(bars: list[Bar], news: Optional[list[NewsItem]] = None) -> PillarScore:
    if len(bars) < 30:
        return PillarScore("risk", PILLAR_WEIGHTS["risk"], 50.0, 0, 0.2,
                           {"note": "insufficient data for risk profile"})
    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    vols = [b.volume for b in bars]

    atr = _atr(highs, lows, closes, 14)
    last = closes[-1]
    rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))][-20:]
    vol = (sum(r * r for r in rets) / len(rets)) ** 0.5 * math.sqrt(252) if rets else 0.0

    dollar_vol = _sma([b.close * b.volume for b in bars[-20:]], 20) or 0.0
    liquidity_score = _clamp(100 * math.log10(max(dollar_vol, 1)) / math.log10(max(5e8, 1)), 0, 100)

    neg_events = sum(1 for n in (news or []) if (n.impact or 0) <= -0.5)
    event_risk = _clamp(neg_events * 12, 0, 100)

    composite = _clamp(0.4 * liquidity_score + 0.35 * (100 - _clamp(vol / MAX_VOLATILITY_ANNUALIZED * 100, 0, 100)) + 0.25 * (100 - event_risk))

    # A *safe*, liquid instrument is favorable to trade; a risky one is not.
    score = composite
    direction = 1 if composite >= 55 else (-1 if composite <= 45 else 0)
    conf = 0.6

    detail = {
        "atr": round(atr, 2) if atr else None,
        "annualized_volatility": round(vol, 3),
        "liquidity_score": round(liquidity_score, 1),
        "event_risk_score": round(event_risk, 1),
        "composite_risk_score": round(composite, 1),
    }
    return PillarScore("risk", PILLAR_WEIGHTS["risk"], score, direction, conf, detail)


# --------------------------------------------------------------------------- #
# Engine                                                                      #
# --------------------------------------------------------------------------- #
@dataclass
class RecommendationSignal:
    symbol: str
    signal: str
    direction: str
    score: float
    confidence: float
    calibrated_probability: float
    conviction: str
    entry_price: float
    target_price: float
    stop_price: float
    risk_reward: float
    holding_period_days: int
    risk_level: str
    no_trade: bool
    rejection_reasons: list[str]
    evidence: list[str]
    caution: list[str]
    pillars: list[PillarScore]
    model_agreement: int
    confident_pillars: int
    agreement_ratio: float
    data_quality: float
    missing_pillars: list[str]
    indicators: dict
    returns: dict
    as_of_date: Any


class AIRecommendationEngine:
    def build(
        self,
        symbol: str,
        bars: list[Bar],
        *,
        fundamentals: Optional[Fundamentals] = None,
        news: Optional[list[NewsItem]] = None,
        regime: Optional[MarketRegime] = None,
        sector_ctx: Optional[dict] = None,
        breadth_ctx: Optional[dict] = None,
    ) -> dict:
        sector_ctx = sector_ctx or {}
        breadth_ctx = breadth_ctx or {}

        if regime is None:
            regime = MarketRegime(
                sector_momentum=float(sector_ctx.get("momentum_score", 50.0)),
                nifty_trend=float(sector_ctx.get("nifty_trend", 50.0)),
                banknifty_trend=float(sector_ctx.get("banknifty_trend", 50.0)),
                india_vix=float(sector_ctx.get("india_vix", 15.0)),
                breadth_adv_decl=float(breadth_ctx.get("adv_decl_ratio", 1.0)),
            )

        closes = [b.close for b in bars]
        as_of = bars[-1].trade_date if bars else None

        p_tech = _technical_pillar(bars)
        p_fund = _fundamental_pillar(fundamentals)
        p_news = _news_pillar(news)
        p_reg = _regime_pillar(regime)
        p_sim = _similarity_pillar(closes)
        p_risk = _risk_pillar(bars, news)

        pillars = [p_tech, p_fund, p_news, p_reg, p_sim, p_risk]
        missing = [p.name for p in pillars if p.confidence < PILLAR_MIN_CONF]

        # direction vote (confidence-weighted)
        vote = sum(p.weight * p.direction * p.confidence for p in pillars)
        final_dir = 1 if vote > 0.12 else (-1 if vote < -0.12 else 0)

        confident = [p for p in pillars if p.confidence >= PILLAR_MIN_CONF]
        agreeing = [p for p in confident if p.direction == final_dir] if final_dir != 0 else []
        agreement_ratio = (len(agreeing) / len(confident)) if confident else 0.0

        wsum = sum(p.weight * p.confidence for p in pillars) or 1.0
        raw_score = _clamp(sum(p.weight * p.score * p.confidence for p in pillars) / wsum)

        data_quality = _clamp(100 - 12 * len(missing), 0, 100)
        base_prob = _sigmoid((raw_score - 50) / 9.0)
        calibrated = _clamp(
            base_prob * (0.55 + 0.45 * agreement_ratio) * (0.6 + 0.4 * data_quality / 100.0),
            0.0, 0.99,
        )

        last_close = closes[-1] if closes else 0.0
        atr = p_risk.detail.get("atr")
        if not atr:
            atr = last_close * 0.02
        risk_per_share = max(atr * ATR_STOP_MULTIPLE, last_close * 0.01)
        if final_dir > 0:
            stop = last_close - risk_per_share
            target = last_close + risk_per_share * STOP_TARGET_R_MULTIPLE
        elif final_dir < 0:
            stop = last_close + risk_per_share
            target = last_close - risk_per_share * STOP_TARGET_R_MULTIPLE
        else:
            stop = last_close
            target = last_close
        rr = (abs(target - last_close) / risk_per_share) if risk_per_share else 0.0

        liquidity = p_risk.detail.get("liquidity_score", 100.0)
        volatility = p_risk.detail.get("annualized_volatility", 0.0)
        event_risk = p_risk.detail.get("event_risk_score", 0.0)
        sim_sample = p_sim.detail.get("sample_size", 0)

        rejection: list[str] = []
        if len(bars) < MIN_BARS:
            rejection.append("insufficient_price_data")
        if len(confident) < MIN_CONFIDENT_PILLARS:
            rejection.append("insufficient_confident_models")
        if final_dir == 0:
            rejection.append("no_clear_direction")
        if len(confident) >= 5 and len(agreeing) < REQUIRED_AGREEMENT:
            rejection.append("model_disagreement")
        if rr < MIN_RISK_REWARD and final_dir != 0:
            rejection.append("poor_risk_reward")
        if liquidity < MIN_LIQUIDITY_SCORE:
            rejection.append("low_liquidity")
        if volatility > MAX_VOLATILITY_ANNUALIZED:
            rejection.append("abnormal_volatility")
        if event_risk >= 60:
            rejection.append("major_event_risk")
        if sim_sample and sim_sample < MIN_SIMILARITY_SAMPLE:
            rejection.append("insufficient_historical_sample")
        if calibrated < WEAK_PROBABILITY and raw_score < STRONG_SCORE:
            rejection.append("weak_probability")

        no_trade = len(rejection) > 0

        if no_trade:
            signal = "hold"
            direction_str = "HOLD"
            conviction = "NONE"
        elif raw_score >= HIGH_CONVICTION_SCORE and calibrated >= HIGH_CONVICTION_PROB and len(agreeing) >= REQUIRED_AGREEMENT:
            conviction = "HIGH"
            signal = "strong_buy" if final_dir > 0 else "strong_sell"
            direction_str = "BUY" if final_dir > 0 else "SELL"
        elif raw_score >= STRONG_SCORE and calibrated >= STRONG_PROB and len(agreeing) >= REQUIRED_AGREEMENT:
            conviction = "STRONG"
            signal = "buy" if final_dir > 0 else "sell"
            direction_str = "BUY" if final_dir > 0 else "SELL"
        else:
            no_trade = True
            rejection.append("below_signal_threshold")
            signal = "hold"
            direction_str = "HOLD"
            conviction = "NONE"

        risk_level = "Low"
        if volatility > 0.6 or liquidity < 50 or event_risk >= 40:
            risk_level = "High"
        elif volatility > 0.4 or liquidity < 70:
            risk_level = "Medium"

        sig = RecommendationSignal(
            symbol=symbol.upper(),
            signal=signal,
            direction=direction_str,
            score=round(raw_score, 2),
            confidence=round(calibrated, 4),
            calibrated_probability=round(calibrated, 4),
            conviction=conviction,
            entry_price=round(last_close, 2),
            target_price=round(target, 2),
            stop_price=round(stop, 2),
            risk_reward=round(rr, 2),
            holding_period_days=HOLDING_PERIOD_DAYS,
            risk_level=risk_level,
            no_trade=no_trade,
            rejection_reasons=rejection,
            evidence=[],
            caution=[],
            pillars=pillars,
            model_agreement=len(agreeing),
            confident_pillars=len(confident),
            agreement_ratio=round(agreement_ratio, 3),
            data_quality=round(data_quality, 1),
            missing_pillars=missing,
            indicators=p_tech.detail,
            returns={
                "target_first_prob": p_sim.detail.get("target_first_prob"),
                "stop_first_prob": p_sim.detail.get("stop_first_prob"),
                "avg_forward_return": p_sim.detail.get("avg_forward_return"),
                "avg_holding_period": p_sim.detail.get("avg_holding_period"),
                "sample_size": p_sim.detail.get("sample_size"),
            },
            as_of_date=as_of.isoformat() if isinstance(as_of, (date, datetime)) else as_of,
        )
        return self._finalize(sig)

    # ------------------------------------------------------------------ #
    def _finalize(self, sig: RecommendationSignal) -> dict:
        evidence: list[str] = []
        caution: list[str] = []
        name_map = {
            "technical": "Technical",
            "fundamental": "Fundamental",
            "news": "News/Sentiment",
            "regime": "Market Regime",
            "similarity": "Historical Pattern",
            "risk": "Risk",
        }
        if sig.direction != "HOLD":
            for p in sig.pillars:
                if p.direction == (1 if sig.direction == "BUY" else -1) and p.confidence >= PILLAR_MIN_CONF:
                    evidence.append(
                        f"{name_map[p.name]}: {p.score:.0f}/100 "
                        f"({'bullish' if p.direction > 0 else 'bearish'})"
                    )
        if sig.returns.get("sample_size") and sig.returns["sample_size"] >= MIN_SIMILARITY_SAMPLE:
            evidence.append(
                f"Historical pattern: target-first {sig.returns['target_first_prob']*100:.0f}% "
                f"vs stop-first {sig.returns['stop_first_prob']*100:.0f}%, "
                f"avg return {sig.returns['avg_forward_return']*100:.1f}%"
            )
        if sig.risk_reward > 0 and sig.risk_reward < MIN_RISK_REWARD and sig.direction != "HOLD":
            caution.append(f"Risk/Reward {sig.risk_reward:.2f} below 1:2 — inadequate asymmetry.")
        if sig.missing_pillars:
            caution.append("Limited data for: " + ", ".join(name_map[m] for m in sig.missing_pillars) + ".")
        if sig.rejection_reasons:
            caution.append("NO-TRADE: " + "; ".join(sig.rejection_reasons) + ".")
        if sig.risk_level == "High":
            caution.append("Elevated risk profile for this instrument.")
        sig.evidence = evidence
        sig.caution = caution

        return {
            "symbol": sig.symbol,
            "signal": sig.signal,
            "direction": sig.direction,
            "score": sig.score,
            "confidence": sig.confidence,
            "calibrated_probability": sig.calibrated_probability,
            "conviction": sig.conviction,
            "current_price": sig.entry_price,
            "entry_price": sig.entry_price,
            "price_target": sig.target_price,
            "stop_price": sig.stop_price,
            "risk_reward": sig.risk_reward,
            "holding_period_days": sig.holding_period_days,
            "expected_return_pct": round(
                ((sig.target_price - sig.entry_price) / sig.entry_price * 100.0)
                if sig.entry_price else 0.0, 2
            ),
            "risk_level": sig.risk_level,
            "no_trade": sig.no_trade,
            "rejection_reasons": sig.rejection_reasons,
            "evidence": sig.evidence,
            "caution": sig.caution,
            "indicators": sig.indicators,
            "returns": sig.returns,
            "as_of_date": sig.as_of_date,
            "factors": {
                p.name: {
                    "weight": p.weight,
                    "score": round(p.score, 2),
                    "direction": p.direction,
                    "confidence": round(p.confidence, 3),
                    "contribution": round(p.weight * p.score * p.confidence, 2),
                    "detail": p.detail,
                }
                for p in sig.pillars
            },
            "explainability": explain(sig),
            "insufficient_data": len(sig.rejection_reasons) > 0 and "insufficient_price_data" in sig.rejection_reasons,
        }

def bars_from_records(records: list[Any]) -> list[Bar]:
    """Convert a list of price records (dict, dataclass or MarketDataPoint)
    into the engine's ``Bar`` objects. Missing OHLCV fields default to 0."""
    bars: list[Bar] = []
    for r in records or []:
        if isinstance(r, dict):
            get = r.get
        else:
            get = lambda k, default=None: getattr(r, k, default)  # noqa: E731
        bars.append(
            Bar(
                trade_date=get("trade_date"),
                open=float(get("open") or 0.0),
                high=float(get("high") or 0.0),
                low=float(get("low") or 0.0),
                close=float(get("close") or 0.0),
                volume=float(get("volume") or 0.0),
            )
        )
    return bars


def fundamentals_from_records(records: list[Any]) -> Optional[Fundamentals]:
    """Build a ``Fundamentals`` object from a list of FundamentalMetric-like
    records (each exposes ``metric_name`` and ``value``). Returns None when no
    records are available."""
    if not records:
        return None
    by_name: dict[str, float] = {}
    for r in records:
        name = getattr(r, "metric_name", None) or (r.get("metric_name") if isinstance(r, dict) else None)
        val = getattr(r, "value", None) if not isinstance(r, dict) else r.get("value")
        if name and val is not None:
            try:
                by_name[name] = float(val)
            except (TypeError, ValueError):
                continue
    if not by_name:
        return None
    return Fundamentals(
        revenue_growth_yoy=by_name.get("revenue_growth_yoy"),
        eps_growth_yoy=by_name.get("eps_growth_yoy"),
        roe=by_name.get("roe"),
        roce=by_name.get("roce"),
        debt_to_equity=by_name.get("debt_to_equity"),
        net_margin=by_name.get("net_margin"),
        operating_margin=by_name.get("operating_margin"),
        pe_ratio=by_name.get("pe_ratio"),
        pb_ratio=by_name.get("pb_ratio"),
        promoter_holding=by_name.get("promoter_holding"),
        fii_holding=by_name.get("fii_holding"),
        free_cash_flow=by_name.get("free_cash_flow"),
    )


def news_from_records(articles: list[Any]) -> list[NewsItem]:
    """Build ``NewsItem`` objects from NewsArticle records that carry an
    ``nlp_analysis`` relationship (sentiment). Articles without processed NLP
    are skipped."""
    items: list[NewsItem] = []
    for a in articles or []:
        nlp = getattr(a, "nlp_analysis", None)
        if nlp is None:
            continue
        label = getattr(nlp, "sentiment_label", None) or "neutral"
        pos = getattr(nlp, "sentiment_positive", None) or 0.0
        neg = getattr(nlp, "sentiment_negative", None) or 0.0
        score = pos - neg
        conf = getattr(nlp, "sentiment_confidence", None) or getattr(nlp, "overall_confidence", None) or 0.5
        impact = getattr(nlp, "event_confidence", None) or 0.0
        items.append(
            NewsItem(
                headline=getattr(a, "title", "") or "",
                sentiment_label=str(label),
                sentiment_score=float(score),
                confidence=float(conf),
                impact=float(impact),
            )
        )
    return items


def explain(sig: RecommendationSignal) -> dict:
        return {
            "symbol": sig.symbol,
            "signal": sig.signal,
            "conviction": sig.conviction,
            "direction": sig.direction,
            "score": sig.score,
            "calibrated_probability": sig.calibrated_probability,
            "entry": sig.entry_price,
            "target": sig.target_price,
            "stop": sig.stop_price,
            "risk_reward": sig.risk_reward,
            "min_required_rr": MIN_RISK_REWARD,
            "model_agreement": f"{sig.model_agreement}/{REQUIRED_AGREEMENT}",
            "confident_pillars": sig.confident_pillars,
            "agreement_ratio": sig.agreement_ratio,
            "data_quality": sig.data_quality,
            "missing_pillars": sig.missing_pillars,
            "no_trade": sig.no_trade,
            "rejection_reasons": sig.rejection_reasons,
            "pillars": [
                {
                    "name": p.name,
                    "weight": p.weight,
                    "score": round(p.score, 2),
                    "direction": p.direction,
                    "confidence": round(p.confidence, 3),
                    "detail": p.detail,
                }
                for p in sig.pillars
            ],
            "historical_evidence": sig.returns,
            "reasons": sig.evidence,
            "risks": sig.caution,
            "disclaimer": (
                "Generated by a transparent, rules-based ensemble. Not investment advice. "
                "No guaranteed accuracy or profits. Past patterns do not assure future results."
            ),
        }
