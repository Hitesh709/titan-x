"""Top Pick service: 6-layer "why to buy" evidence scoring across the universe.

Layers (weights):
  L1 Trend        0.25 - trend quality from EMA stack, ADX, MACD, RSI
  L2 Smart Money  0.20 - institutional / FII-DII / promoter activity (volume-flow proxy fallback)
  L3 Fundamentals 0.15 - valuation, market cap, sector, 52-week position
  L4 News/Events  0.15 - recent news sentiment & event density
  L5 Regime       0.15 - bull / bear / sideways regime from price structure
  L6 Risk Filter  0.10 - volatility, drawdown, overbought/oversold sanity gate
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.company import Company
from titan_x.models.institutional_holdings import FIIHolding
from titan_x.models.news import NewsArticle
from titan_x.models.news_nlp import NewsNLPAnalysis
from titan_x.models.price import DailyPrice
from titan_x.services.technical_indicator_engine import IndicatorMath

logger = structlog.get_logger(__name__)

LAYER_WEIGHTS = {
    "trend": 0.25,
    "smart_money": 0.20,
    "fundamentals": 0.15,
    "news": 0.15,
    "regime": 0.15,
    "risk": 0.10,
}


class TopPickService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_top_picks(self, limit: int = 10) -> dict[str, Any]:
        symbols = (
            (await self._session.execute(
                select(DailyPrice.symbol)
                .group_by(DailyPrice.symbol)
                .having(func.count() >= 120)
                .order_by(desc(func.max(DailyPrice.trade_date)))
            )).scalars().all()
        )
        results = []
        for symbol in symbols:
            try:
                scored = await self._score(symbol)
            except Exception as exc:  # noqa: BLE001
                logger.warning("top_pick_skip", symbol=symbol, error=str(exc))
                continue
            if scored["composite"] is None:
                continue
            results.append(scored)

        results.sort(key=lambda r: r["composite"], reverse=True)
        picks = results[:limit]
        return {
            "generated_at": date.today().isoformat(),
            "universe_size": len(symbols),
            "scored": len(results),
            "layers": [{"key": k, "label": _LAYER_LABELS[k], "weight": w}
                       for k, w in LAYER_WEIGHTS.items()],
            "top_picks": picks,
        }

    # ------------------------------------------------------------------
    async def _score(self, symbol: str) -> dict[str, Any]:
        prices = list((await self._session.execute(
            select(DailyPrice)
            .where(DailyPrice.symbol == symbol)
            .order_by(DailyPrice.trade_date.asc())
        )).scalars().all())
        if len(prices) < 120:
            return {"symbol": symbol, "composite": None}

        company = (await self._session.execute(
            select(Company).where(Company.symbol == symbol)
        )).scalar_one_or_none()

        close = [p.close for p in prices]
        high = [p.high for p in prices]
        low = [p.low for p in prices]
        volume = [p.volume for p in prices]
        last_price = close[-1]

        layers = {
            "trend": self._score_trend(close, high, low, volume),
            "smart_money": await self._score_smart_money(symbol, close, high, low, volume),
            "fundamentals": self._score_fundamentals(company, close),
            "news": await self._score_news(symbol),
            "regime": self._score_regime(close),
            "risk": self._score_risk(close, high, low, volume),
        }

        composite = sum(layers[k]["score"] * LAYER_WEIGHTS[k] for k in LAYER_WEIGHTS)
        signal = _signal_for(composite, layers["risk"]["signal"])

        change_pct = 0.0
        if len(close) >= 2 and close[-2]:
            change_pct = (close[-1] - close[-2]) / close[-2] * 100
        chg_1m = 0.0
        if len(close) >= 21 and close[-22]:
            chg_1m = (close[-1] - close[-22]) / close[-22] * 100

        return {
            "symbol": symbol,
            "name": company.company_name if company else symbol,
            "sector": company.sector if company else None,
            "price": round(last_price, 2),
            "change_pct": round(change_pct, 2),
            "change_1m_pct": round(chg_1m, 2),
            "composite": round(composite, 1),
            "signal": signal,
            "layers": layers,
            "summary": self._build_summary(layers, signal),
        }

    # ------------------------------------------------------------------
    # L1 - Trend
    # ------------------------------------------------------------------
    def _score_trend(
        self, close: list[float], high: list[float], low: list[float], volume: list[int]
    ) -> dict[str, Any]:
        ema20 = _last(IndicatorMath.ema(close, 20))
        ema50 = _last(IndicatorMath.ema(close, 50))
        sma200 = _last(IndicatorMath.sma(close, 200))
        rsi = _last(IndicatorMath.rsi(close, 14))
        adx, pdi, mdi = IndicatorMath.adx(high, low, close, 14)
        adx_v = _last(adx)
        pdi_v, mdi_v = _last(pdi), _last(mdi)
        macd_line, signal_line, hist = IndicatorMath.macd(close)
        hist_v = _last(hist)
        price = close[-1]

        score = 0.0
        evidence: list[str] = []
        counters: dict[str, int] = {}

        def bump(points: float, label: str, key: str) -> None:
            nonlocal score
            score += points
            counters[key] = counters.get(key, 0) + 1
            evidence.append(label)

        if ema20 and ema50 and ema20 > ema50:
            bump(15, "20-EMA above 50-EMA (uptrend structure)", "ema_stack")
        if sma200 and price > sma200:
            bump(15, f"Price above 200-SMA ({sma200:,.2f})", "above_sma200")
        if ema20 and price > ema20:
            bump(10, "Price above 20-EMA (short-term support)", "price_above_ema20")
        if rsi is not None:
            if 50 <= rsi <= 70:
                bump(15, f"RSI {rsi:.0f} in healthy bullish zone (50-70)", "rsi")
            elif rsi > 70:
                bump(5, f"RSI {rsi:.0f} overbought - chase risk", "rsi")
            elif 40 <= rsi < 50:
                bump(5, f"RSI {rsi:.0f} recovering from neutral", "rsi")
            else:
                bump(0, f"RSI {rsi:.0f} weak momentum", "rsi")
        if adx_v is not None and pdi_v is not None and mdi_v is not None:
            if adx_v >= 25 and pdi_v > mdi_v:
                bump(15, f"ADX {adx_v:.0f} strong trend, +DI above -DI (bullish pressure)", "adx")
            elif adx_v >= 20 and pdi_v > mdi_v:
                bump(10, f"ADX {adx_v:.0f} developing uptrend", "adx")
            else:
                bump(0, f"ADX {adx_v:.0f} weak/choppy trend", "adx")
        if hist_v is not None:
            if hist_v > 0:
                bump(15, "MACD histogram positive (momentum expanding)", "macd")
            else:
                bump(0, "MACD histogram negative (momentum fading)", "macd")
        if len(volume) >= 20:
            avg_vol = sum(volume[-20:]) / 20
            last_vol = volume[-1]
            if avg_vol > 0 and last_vol > avg_vol * 1.2:
                bump(5, "Rising volume confirming move", "volume_confirm")

        capped = min(score, 100.0)
        return {
            "score": round(capped, 1),
            "signal": "bullish" if capped >= 60 else ("bearish" if capped <= 35 else "neutral"),
            "confidence": round(capped / 100, 2),
            "evidence": evidence[:6],
            "metrics": {
                "rsi": round(rsi, 1) if rsi is not None else None,
                "adx": round(adx_v, 1) if adx_v is not None else None,
                "ema20": round(ema20, 2) if ema20 else None,
                "ema50": round(ema50, 2) if ema50 else None,
                "sma200": round(sma200, 2) if sma200 else None,
            },
        }

    # ------------------------------------------------------------------
    # L2 - Smart Money
    # ------------------------------------------------------------------
    async def _score_smart_money(
        self,
        symbol: str,
        close: list[float],
        high: list[float],
        low: list[float],
        volume: list[int],
    ) -> dict[str, Any]:
        company = (await self._session.execute(
            select(Company).where(Company.symbol == symbol)
        )).scalar_one_or_none()
        if company is None:
            return self._volume_flow_score(close, high, low, volume)

        fii = (await self._session.execute(
            select(FIIHolding)
            .where(FIIHolding.company_id == company.id)
            .order_by(desc(FIIHolding.filing_date))
            .limit(1)
        )).scalar_one_or_none()

        if fii is None:
            return self._volume_flow_score(close, high, low, volume)

        # Real institutional data available
        score = 50.0
        evidence = [f"FII holding {fii.percentage:.2f}% as of {fii.filing_date}"]
        if fii.percentage is not None:
            if fii.percentage >= 20:
                score += 25
                evidence.append("High FII ownership (>20%)")
            elif fii.percentage >= 10:
                score += 15
            else:
                score -= 10
        if fii.change_percentage is not None:
            if fii.change_percentage > 0:
                score += 20
                evidence.append(f"FII increased stake by {fii.change_percentage:+.2f}%")
            elif fii.change_percentage < 0:
                score -= 15
                evidence.append(f"FII trimmed stake {fii.change_percentage:+.2f}%")
        capped = min(max(score, 0), 100)
        return {
            "score": round(capped, 1),
            "signal": "bullish" if capped >= 60 else ("bearish" if capped <= 35 else "neutral"),
            "confidence": round(abs(capped - 50) / 50, 2),
            "evidence": evidence[:6],
            "metrics": {"fii_percent": fii.percentage, "fii_change": fii.change_percentage},
            "source": "institutional_holdings",
        }

    def _volume_flow_score(
        self, close: list[float], high: list[float], low: list[float], volume: list[int]
    ) -> dict[str, Any]:
        score = 50.0
        evidence = ["Institutional filings absent - using volume-flow proxy"]
        if len(close) < 30:
            return {"score": 50, "signal": "neutral", "confidence": 0.0,
                    "evidence": evidence, "metrics": {}, "source": "volume_proxy"}

        obv = IndicatorMath.obv(close, volume)
        if len(obv) >= 21 and obv[-1] > obv[-21]:
            score += 15
            evidence.append("OBV rising 20 sessions (accumulation signal)")
        else:
            score -= 10
            evidence.append("OBV flat/falling (distribution risk)")

        cmf_values = IndicatorMath.cmf(high, low, close, volume, 20)
        cmf_v = _last(cmf_values)
        if cmf_v is not None:
            if cmf_v > 0.05:
                score += 15
                evidence.append(f"CMF {cmf_v:.2f} positive (money flowing in)")
            elif cmf_v < -0.05:
                score -= 15
                evidence.append(f"CMF {cmf_v:.2f} negative (money flowing out)")

        if len(volume) >= 20:
            avg_vol = sum(volume[-20:]) / 20
            up_days = sum(
                1 for i in range(max(1, len(close) - 20), len(close))
                if close[i] > close[i - 1] and volume[i] > avg_vol
            )
            if up_days >= 8:
                score += 10
                evidence.append("Multiple up days on above-average volume")
            elif up_days <= 3:
                score -= 10
                evidence.append("Few up days on above-average volume")

        capped = min(max(score, 0), 100)
        return {
            "score": round(capped, 1),
            "signal": "bullish" if capped >= 60 else ("bearish" if capped <= 35 else "neutral"),
            "confidence": round(abs(capped - 50) / 50, 2),
            "evidence": evidence[:6],
            "metrics": {"cmf": round(cmf_v, 3) if cmf_v is not None else None,
                        "obv_trend": "up" if obv[-1] > obv[-21] else "down"},
            "source": "volume_proxy",
        }

    # ------------------------------------------------------------------
    # L3 - Fundamentals
    # ------------------------------------------------------------------
    def _score_fundamentals(self, company: Company | None, close: list[float]) -> dict[str, Any]:
        evidence: list[str] = []
        score = 50.0
        metrics: dict[str, Any] = {}

        if company is None:
            return {"score": 50, "signal": "neutral", "confidence": 0.0,
                    "evidence": ["No fundamentals profile on file"], "metrics": metrics}

        if company.market_cap:
            mc_b = company.market_cap / 1e9
            if mc_b >= 500:
                score += 20
                evidence.append(f"Large-cap ({mc_b:.0f}B INR) - lower default risk")
                metrics["market_cap_b"] = round(mc_b, 1)
            elif mc_b >= 100:
                score += 10
                evidence.append(f"Mid/large-cap ({mc_b:.0f}B INR)")
                metrics["market_cap_b"] = round(mc_b, 1)
            else:
                score -= 5
                evidence.append(f"Small-cap ({mc_b:.1f}B INR) - higher volatility")
                metrics["market_cap_b"] = round(mc_b, 1)

        if company.sector:
            evidence.append(f"Sector: {company.sector}")

        # 52-week position
        hi, lo = max(close), min(close)
        price = close[-1]
        if hi > lo and price > 0:
            position = (price - lo) / (hi - lo) * 100
            metrics["52w_position_pct"] = round(position, 1)
            if position >= 80:
                score += 15
                evidence.append(
                    f"Trading near 52-week high ({position:.0f}% of range) - strong uptrend"
                )
            elif position >= 50:
                score += 5
                evidence.append(f"Upper half of 52-week range ({position:.0f}%)")
            elif position <= 20:
                score -= 15
                evidence.append(f"Near 52-week low ({position:.0f}% of range)")

        capped = min(max(score, 0), 100)
        return {
            "score": round(capped, 1),
            "signal": "bullish" if capped >= 60 else ("bearish" if capped <= 35 else "neutral"),
            "confidence": round(abs(capped - 50) / 50, 2),
            "evidence": evidence[:6],
            "metrics": metrics,
        }

    # ------------------------------------------------------------------
    # L4 - News / Events
    # ------------------------------------------------------------------
    async def _score_news(self, symbol: str) -> dict[str, Any]:
        since = datetime_now() - timedelta(days=7)
        articles = list((await self._session.execute(
            select(NewsArticle)
            .where(NewsArticle.symbol == symbol, NewsArticle.published_at >= since)
            .order_by(desc(NewsArticle.published_at))
            .limit(10)
        )).scalars().all())

        if not articles:
            return {"score": 50, "signal": "neutral", "confidence": 0.0,
                    "evidence": ["No news flow in last 7 days (sentiment unknown)"],
                    "metrics": {"article_count": 0}}

        pos = neg = 0
        sentiments: list[str] = []
        for a in articles:
            nlp = (await self._session.execute(
                select(NewsNLPAnalysis).where(NewsNLPAnalysis.article_id == a.id)
            )).scalar_one_or_none()
            label = nlp.sentiment_label if nlp else "neutral"
            sentiments.append(label)
            if label in ("positive", "bullish"):
                pos += 1
            elif label in ("negative", "bearish"):
                neg += 1

        total = len(sentiments)
        score = 50.0
        evidence = [f"{total} article(s) in last 7 days"]
        if pos > neg:
            score += 20 * min(pos / max(total, 1), 1) + 10
            evidence.append(f"{pos} positive, {neg} negative headlines")
        elif neg > pos:
            score -= 20 * min(neg / max(total, 1), 1) + 10
            evidence.append(f"{pos} positive, {neg} negative headlines - caution")
        else:
            evidence.append("Balanced neutral news flow")

        capped = min(max(score, 0), 100)
        return {
            "score": round(capped, 1),
            "signal": "bullish" if capped >= 60 else ("bearish" if capped <= 35 else "neutral"),
            "confidence": round(abs(capped - 50) / 50, 2),
            "evidence": evidence[:6],
            "metrics": {"article_count": total, "positive": pos, "negative": neg},
        }

    # ------------------------------------------------------------------
    # L5 - Market Regime
    # ------------------------------------------------------------------
    def _score_regime(self, close: list[float]) -> dict[str, Any]:
        price = close[-1]
        sma50 = _last(IndicatorMath.sma(close, 50))
        sma200 = _last(IndicatorMath.sma(close, 200))
        sma20 = _last(IndicatorMath.sma(close, 20))

        if not sma50 or not sma200:
            return {"score": 50, "signal": "neutral", "confidence": 0.0,
                    "evidence": ["Insufficient history for regime detection"]}

        score = 50.0
        evidence: list[str] = []
        if price > sma200 and sma50 > sma200:
            score += 25
            evidence.append("Bull regime: price & 50-SMA above 200-SMA")
        elif price < sma200 and sma50 < sma200:
            score -= 25
            evidence.append("Bear regime: price & 50-SMA below 200-SMA")
        else:
            evidence.append("Mixed/sideways regime (50-SMA crossing 200-SMA)")

        if sma20 and price > sma20:
            score += 15
            evidence.append("Short-term uptrend intact (price above 20-SMA)")
        else:
            score -= 10
            evidence.append("Price below 20-SMA (short-term weakness)")

        momentum_3m = 0.0
        if len(close) >= 64 and close[-64]:
            momentum_3m = (price - close[-64]) / close[-64] * 100
            if momentum_3m > 5:
                score += 10
                evidence.append(f"3-month momentum +{momentum_3m:.1f}%")
            elif momentum_3m < -5:
                score -= 10
                evidence.append(f"3-month momentum {momentum_3m:.1f}%")

        capped = min(max(score, 0), 100)
        regime = "bull" if capped >= 65 else ("bear" if capped <= 35 else "sideways")
        return {
            "score": round(capped, 1),
            "signal": regime,
            "confidence": round(abs(capped - 50) / 50, 2),
            "evidence": evidence[:6],
            "metrics": {"regime": regime, "momentum_3m_pct": round(momentum_3m, 1)},
        }

    # ------------------------------------------------------------------
    # L6 - Risk Filter
    # ------------------------------------------------------------------
    def _score_risk(
        self, close: list[float], high: list[float], low: list[float], volume: list[int]
    ) -> dict[str, Any]:
        score = 100.0
        evidence: list[str] = ["Risk filter passes"]
        warnings: list[str] = []
        metrics: dict[str, Any] = {}

        atr_v = _last(IndicatorMath.atr(high, low, close, 14))
        price = close[-1]
        if atr_v and price:
            atr_pct = atr_v / price * 100
            metrics["atr_pct"] = round(atr_pct, 2)
            if atr_pct > 6:
                score -= 40
                warnings.append(f"High volatility: daily ATR {atr_pct:.1f}%")
            elif atr_pct > 3.5:
                score -= 15
                warnings.append(f"Elevated volatility: daily ATR {atr_pct:.1f}%")
            elif atr_pct < 1.5:
                score -= 5
                warnings.append("Very low volatility (illiquid/large-cap slow mover)")

        # max drawdown over lookback
        peak = close[0]
        max_dd = 0.0
        for c in close:
            if c > peak:
                peak = c
            dd = (peak - c) / peak if peak else 0
            max_dd = max(max_dd, dd)
        max_dd_pct = max_dd * 100
        metrics["max_drawdown_pct"] = round(max_dd_pct, 1)
        if max_dd_pct > 40:
            score -= 25
            warnings.append(f"Deep drawdown profile ({max_dd_pct:.0f}% peak-to-trough)")
        elif max_dd_pct > 25:
            score -= 10
            warnings.append(f"Moderate drawdown risk ({max_dd_pct:.0f}%)")

        rsi = _last(IndicatorMath.rsi(close, 14))
        if rsi is not None and rsi > 80:
            score -= 10
            warnings.append(f"RSI {rsi:.0f} severely overbought")
        elif rsi is not None and rsi > 72:
            score -= 5
            warnings.append(f"RSI {rsi:.0f} approaching overbought")

        capped = min(max(score, 0), 100)
        status = "pass" if capped >= 70 else ("caution" if capped >= 40 else "fail")
        if warnings:
            evidence = warnings
        return {
            "score": round(capped, 1),
            "signal": status,
            "confidence": round(capped / 100, 2),
            "evidence": evidence[:6],
            "metrics": metrics,
        }

    # ------------------------------------------------------------------
    def _build_summary(self, layers: dict[str, Any], signal: str) -> str:
        strong = [k for k, v in layers.items() if v["score"] >= 60]
        weak = [k for k, v in layers.items() if v["score"] <= 40]
        parts = []
        if strong:
            parts.append("Strong on " + ", ".join(_LAYER_LABELS[k] for k in strong))
        if weak:
            parts.append("Weak on " + ", ".join(_LAYER_LABELS[k] for k in weak))
        if not parts:
            parts.append("Mixed signals across all layers")
        return f"{signal.upper()}: " + "; ".join(parts) + "."


_LAYER_LABELS = {
    "trend": "Trend",
    "smart_money": "Smart Money",
    "fundamentals": "Fundamentals",
    "news": "News & Events",
    "regime": "Market Regime",
    "risk": "Risk Filter",
}


def _last(values: list[Any]) -> Any:
    return values[-1] if values else None


def _signal_for(composite: float, risk_status: str) -> str:
    if risk_status == "fail":
        return "avoid"
    if composite >= 75:
        return "strong_buy"
    if composite >= 62:
        return "buy"
    if composite >= 48:
        return "hold"
    return "avoid"


def datetime_now():
    from datetime import UTC, datetime
    return datetime.now(UTC)
