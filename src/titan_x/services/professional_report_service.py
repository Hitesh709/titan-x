import json
import math
from datetime import date, timedelta
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_x.models.chart_pattern import SupportResistance
from titan_x.models.company import Company
from titan_x.models.fundamental import FundamentalMetric
from titan_x.models.microstructure import MarketMicrostructure
from titan_x.models.news import NewsArticle
from titan_x.models.news_nlp import NewsNLPAnalysis
from titan_x.models.price import DailyPrice
from titan_x.models.professional_report import ProfessionalReport
from titan_x.models.regime import MarketRegime
from titan_x.models.risk import RiskMetrics
from titan_x.models.technical import TechnicalIndicator


class ProfessionalReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def generate(
        self, symbol: str, direction: str = "bullish",
    ) -> ProfessionalReport:
        symbol = symbol.upper()
        today = date.today()

        prices = await self._load_prices(symbol, today)
        current_price = prices[-1].close if prices else 0.0

        summary = await self._build_summary(symbol, today, current_price, direction)
        technical = await self._build_technical(symbol, today, prices)
        fundamental = await self._build_fundamental(symbol)
        news_data = await self._build_news(symbol, today)
        risk = await self._build_risk(symbol, today)
        prediction = await self._build_prediction(symbol, today, prices, direction)

        html = self._build_html(
            symbol, today, direction, current_price,
            summary, technical, fundamental, news_data, risk, prediction,
        )

        report = ProfessionalReport(
            symbol=symbol,
            trade_date=today,
            direction=direction,
            current_price=current_price,
            summary_json=json.dumps(summary),
            technical_json=json.dumps(technical),
            fundamental_json=json.dumps(fundamental),
            news_json=json.dumps(news_data),
            risk_json=json.dumps(risk),
            prediction_json=json.dumps(prediction),
            html_content=html,
            metadata_json=json.dumps({
                "direction": direction,
                "current_price": current_price,
            }),
        )
        self.session.add(report)
        await self.session.flush()
        await self.session.refresh(report)
        return report

    async def get_report(self, report_id: int) -> ProfessionalReport | None:
        r = await self.session.execute(
            select(ProfessionalReport).where(ProfessionalReport.id == report_id)
        )
        return r.scalar_one_or_none()

    async def get_reports(
        self, symbol: str, limit: int = 20, offset: int = 0,
    ) -> list[ProfessionalReport]:
        r = await self.session.execute(
            select(ProfessionalReport).where(ProfessionalReport.symbol == symbol.upper())
            .order_by(desc(ProfessionalReport.trade_date))
            .offset(offset).limit(limit)
        )
        return list(r.scalars().all())

    # ---- section builders ----

    async def _build_summary(
        self, symbol: str, today: date, current_price: float, direction: str,
    ) -> dict[str, Any]:
        company = await self.session.execute(
            select(Company).where(Company.symbol == symbol).limit(1)
        )
        c = company.scalar_one_or_none()

        regime = await self._get_latest_regime(symbol)
        liq = await self._get_latest_liquidity(symbol)

        prices = await self._load_prices(symbol, today, 30)
        price_change_1d = None
        price_change_5d = None
        price_change_20d = None
        if len(prices) >= 2:
            price_change_1d = round(
                (prices[-1].close - prices[-2].close) / prices[-2].close * 100, 2,
            )
        if len(prices) >= 5:
            price_change_5d = round(
                (prices[-1].close - prices[-5].close) / prices[-5].close * 100, 2,
            )
        if len(prices) >= 20:
            price_change_20d = round(
                (prices[-1].close - prices[-20].close) / prices[-20].close * 100, 2,
            )

        return {
            "symbol": symbol,
            "company_name": c.company_name if c else None,
            "sector": c.sector if c else None,
            "industry": c.industry if c else None,
            "current_price": current_price,
            "direction": direction,
            "trade_date": today.isoformat(),
            "price_change_1d_pct": price_change_1d,
            "price_change_5d_pct": price_change_5d,
            "price_change_20d_pct": price_change_20d,
            "trend_regime": regime.trend_regime if regime else None,
            "volatility_regime": regime.volatility_regime if regime else None,
            "liquidity_score": liq.liquidity_score if liq else None,
            "liquidity_rating": liq.liquidity_rating if liq else None,
        }

    async def _build_technical(
        self, symbol: str, today: date, prices: list[DailyPrice],
    ) -> dict[str, Any]:
        # Query TechnicalIndicator as key-value rows
        lookback = today - timedelta(days=5)
        tech_rows = await self.session.execute(
            select(TechnicalIndicator).where(
                TechnicalIndicator.symbol == symbol,
                TechnicalIndicator.trade_date >= lookback,
                TechnicalIndicator.trade_date <= today,
                TechnicalIndicator.indicator.in_(["rsi", "sma", "ema", "macd", "bb", "volume", "obv", "atr"]),
            ).order_by(TechnicalIndicator.indicator, desc(TechnicalIndicator.trade_date))
        )
        tech_map: dict[str, Any] = {}
        for row in tech_rows.scalars().all():
            if row.indicator not in tech_map:
                entry = {"value": row.value, "value_secondary": row.value_secondary, "value_tertiary": row.value_tertiary, "period": row.period}
                tech_map[row.indicator] = entry

        support = await self.session.execute(
            select(SupportResistance).where(
                SupportResistance.symbol == symbol,
                SupportResistance.level_type == "support",
                SupportResistance.is_active == True,
            ).order_by(desc(SupportResistance.strength_score))
        )
        supports = support.scalars().all()

        resistance = await self.session.execute(
            select(SupportResistance).where(
                SupportResistance.symbol == symbol,
                SupportResistance.level_type == "resistance",
                SupportResistance.is_active == True,
            ).order_by(desc(SupportResistance.strength_score))
        )
        resistances = resistance.scalars().all()

        closes = [p.close for p in prices]
        sma_20 = self._sma(closes, 20) if len(closes) >= 20 else None
        sma_50 = self._sma(closes, 50) if len(closes) >= 50 else None
        rsi_val = self._rsi(closes, 14) if len(closes) >= 15 else None

        sma_20_row = tech_map.get("sma", {})
        if sma_20_row.get("period") == 20 and sma_20_row.get("value") is not None:
            sma_20 = sma_20_row["value"]

        rsi_row = tech_map.get("rsi", {})
        if rsi_row.get("value") is not None:
            rsi_val = rsi_row["value"]

        macd_row = tech_map.get("macd", {})
        bb_row = tech_map.get("bb", {})
        vol_row = tech_map.get("volume", {})

        return {
            "rsi_14": rsi_val,
            "sma_20": sma_20,
            "sma_50": sma_50,
            "macd": macd_row.get("value"),
            "macd_signal": macd_row.get("value_secondary"),
            "macd_histogram": macd_row.get("value_tertiary"),
            "bb_upper": bb_row.get("value_secondary"),
            "bb_lower": bb_row.get("value"),
            "bb_middle": bb_row.get("value_tertiary"),
            "volume": vol_row.get("value"),
            "volume_sma_20": vol_row.get("value_secondary"),
            "obv": tech_map.get("obv", {}).get("value"),
            "support_levels": [
                {"price": s.price_level, "strength": s.strength_score}
                for s in supports
            ],
            "resistance_levels": [
                {"price": r.price_level, "strength": r.strength_score}
                for r in resistances
            ],
            "price_trend": [
                {"date": p.trade_date.isoformat(), "close": p.close}
                for p in prices[-30:]
            ],
        }

    async def _build_fundamental(self, symbol: str) -> dict[str, Any]:
        metric_names = ["pe_ratio", "pb_ratio", "debt_to_equity", "current_ratio",
                        "profit_margin", "revenue_growth", "eps_growth", "roe",
                        "roa", "dividend_yield", "market_cap"]
        rows = await self.session.execute(
            select(FundamentalMetric).where(
                FundamentalMetric.symbol == symbol,
                FundamentalMetric.metric_name.in_(metric_names),
            ).order_by(desc(FundamentalMetric.fiscal_year), desc(FundamentalMetric.fiscal_period))
        )
        fm = rows.scalars().all()
        if not fm:
            return {"available": False}

        data: dict[str, Any] = {"available": True}
        for row in fm:
            if row.metric_name not in data:
                data[row.metric_name] = row.value
        return data

    async def _build_news(self, symbol: str, today: date) -> dict[str, Any]:
        start = today - timedelta(days=7)
        news = await self.session.execute(
            select(NewsArticle).where(
                NewsArticle.symbol == symbol,
                NewsArticle.published_at >= start,
            ).order_by(desc(NewsArticle.published_at)).limit(20)
        )
        articles = news.scalars().all()

        sentiment_scores = []
        for article in articles:
            nlp = await self.session.execute(
                select(NewsNLPAnalysis).where(
                    NewsNLPAnalysis.article_id == article.id,
                ).limit(1)
            )
            nlp_row = nlp.scalar_one_or_none()
            if nlp_row and nlp_row.sentiment_positive is not None:
                sentiment_scores.append(nlp_row.sentiment_positive)

        avg_sentiment = None
        if sentiment_scores:
            avg_sentiment = round(sum(sentiment_scores) / len(sentiment_scores), 4)

        news_items = []
        for a in articles[:10]:
            nlp = await self.session.execute(
                select(NewsNLPAnalysis).where(
                    NewsNLPAnalysis.article_id == a.id,
                ).limit(1)
            )
            nlp_row = nlp.scalar_one_or_none()
            news_items.append({
                "title": a.title,
                "published_at": a.published_at.isoformat() if a.published_at else None,
                "source": a.source,
                "sentiment_positive": nlp_row.sentiment_positive if nlp_row else None,
                "sentiment_negative": nlp_row.sentiment_negative if nlp_row else None,
                "sentiment_neutral": nlp_row.sentiment_neutral if nlp_row else None,
            })

        return {
            "total_articles": len(articles),
            "avg_sentiment_positive": avg_sentiment,
            "articles": news_items,
        }

    async def _build_risk(self, symbol: str, today: date) -> dict[str, Any]:
        risk = await self.session.execute(
            select(RiskMetrics).where(
                RiskMetrics.symbol == symbol,
            ).order_by(desc(RiskMetrics.as_of_date)).limit(1)
        )
        rm = risk.scalar_one_or_none()

        liq = await self._get_latest_liquidity(symbol)
        regime = await self._get_latest_regime(symbol)

        risk_dict: dict[str, Any] = {
            "composite_risk_score": rm.composite_risk_score if rm else None,
            "volatility_score": rm.volatility_20d if rm else None,
            "liquidity_score": liq.liquidity_score if liq else None,
            "liquidity_rating": liq.liquidity_rating if liq else None,
            "trend_regime": regime.trend_regime if regime else None,
            "volatility_regime": regime.volatility_regime if regime else None,
        }
        # map actual RiskMetrics fields to friendlier keys
        if rm:
            risk_dict["max_drawdown_1m"] = rm.max_drawdown_1m
            risk_dict["max_drawdown_3m"] = rm.max_drawdown_3m
            risk_dict["max_drawdown_6m"] = rm.max_drawdown_6m
            risk_dict["volatility_20d"] = rm.volatility_20d
            risk_dict["volatility_60d"] = rm.volatility_60d
            risk_dict["event_risk_score"] = rm.event_risk_score

        return risk_dict

    async def _build_prediction(
        self, symbol: str, today: date, prices: list[DailyPrice], direction: str,
    ) -> dict[str, Any]:
        if not prices:
            return {"available": False}

        current_price = prices[-1].close
        closes = [p.close for p in prices]

        regime = await self._get_latest_regime(symbol)

        lookback = today - timedelta(days=5)
        tech_rows = await self.session.execute(
            select(TechnicalIndicator).where(
                TechnicalIndicator.symbol == symbol,
                TechnicalIndicator.trade_date >= lookback,
                TechnicalIndicator.trade_date <= today,
                TechnicalIndicator.indicator.in_(["rsi", "atr"]),
            ).order_by(TechnicalIndicator.indicator, desc(TechnicalIndicator.trade_date))
        )
        tech_map: dict[str, Any] = {}
        for row in tech_rows.scalars().all():
            if row.indicator not in tech_map:
                tech_map[row.indicator] = row.value

        rsi_val = tech_map.get("rsi") or self._rsi(closes, 14)
        atr_val = tech_map.get("atr")

        if atr_val is None:
            atr_values = self._atr(prices, 14)
            atr_val = atr_values[-1] if atr_values else None

        momentum = None
        if len(closes) >= 10:
            momentum = round(
                (closes[-1] - closes[-10]) / closes[-10] * 100, 2,
            )

        vol_20d = None
        if len(closes) >= 20:
            returns = [
                (closes[i] - closes[i - 1]) / closes[i - 1]
                for i in range(-19, 0)
            ]
            vol_20d = round(self._std(returns) * math.sqrt(252), 4)

        if direction == "bullish":
            target_1_pct = max(3.0, (atr_val or 0) / current_price * 100 * 1.5)
            target_2_pct = target_1_pct * 2.0
            target_3_pct = target_1_pct * 3.5
        else:
            target_1_pct = -max(3.0, (atr_val or 0) / current_price * 100 * 1.5)
            target_2_pct = target_1_pct * 2.0
            target_3_pct = target_1_pct * 3.5

        return {
            "available": True,
            "current_price": current_price,
            "direction": direction,
            "rsi_14": rsi_val,
            "atr_14": atr_val,
            "momentum_10d_pct": momentum,
            "volatility_20d": vol_20d,
            "trend_regime": regime.trend_regime if regime else None,
            "target_1_price": round(current_price * (1 + target_1_pct / 100), 2),
            "target_1_pct": round(target_1_pct, 2),
            "target_2_price": round(current_price * (1 + target_2_pct / 100), 2),
            "target_2_pct": round(target_2_pct, 2),
            "target_3_price": round(current_price * (1 + target_3_pct / 100), 2),
            "target_3_pct": round(target_3_pct, 2),
            "expected_holding_days": 20 if direction == "bullish" else 15,
        }

    # ---- HTML builder ----

    def _build_html(
        self, symbol: str, trade_date: date, direction: str, current_price: float,
        summary: dict, technical: dict, fundamental: dict,
        news_data: dict, risk: dict, prediction: dict,
    ) -> str:
        company_name = summary.get("company_name") or symbol

        price_chg = summary.get("price_change_1d_pct")
        price_chg_str = f"{price_chg:+.2f}%" if price_chg is not None else "N/A"
        price_chg_cls = "green" if price_chg is not None and price_chg >= 0 else "red"

        trend_html = self._svg_trend_chart(technical.get("price_trend", []))

        risk_score = risk.get("composite_risk_score")
        gauge_html = self._svg_risk_gauge(risk_score)

        sentiment = news_data.get("avg_sentiment_positive")
        sentiment_html = self._svg_sentiment_bar(sentiment)

        radar_html = self._svg_fundamental_radar(fundamental)

        sr_html = self._build_sr_table(technical)

        news_table = self._build_news_table(news_data)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Professional Report - {company_name} ({symbol})</title>
<style>
@page {{ margin: 20mm 15mm; size: A4; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #1a1a2e; background: #f0f2f5; line-height: 1.6; }}
.container {{ max-width: 1100px; margin: 0 auto; padding: 20px; }}
.header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: #fff; padding: 30px; border-radius: 12px; margin-bottom: 24px; }}
.header h1 {{ font-size: 26px; margin-bottom: 6px; }}
.header .subtitle {{ font-size: 14px; color: #a0aec0; }}
.header .meta {{ display: flex; gap: 24px; margin-top: 14px; font-size: 13px; }}
.header .meta span {{ background: rgba(255,255,255,0.1); padding: 4px 12px; border-radius: 6px; }}
.price-row {{ display: flex; gap: 20px; margin-top: 16px; }}
.price-box {{ background: rgba(255,255,255,0.08); padding: 12px 20px; border-radius: 8px; text-align: center; }}
.price-box .label {{ font-size: 11px; text-transform: uppercase; color: #a0aec0; }}
.price-box .value {{ font-size: 22px; font-weight: 700; }}
.price-box .value.green {{ color: #48bb78; }}
.price-box .value.red {{ color: #f56565; }}
.section {{ background: #fff; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
.section h2 {{ font-size: 18px; color: #1a1a2e; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; margin-bottom: 16px; }}
.section h2 span {{ color: #667eea; }}
.grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
.grid-3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }}
.metric-card {{ background: #f7fafc; padding: 14px; border-radius: 8px; border-left: 3px solid #667eea; }}
.metric-card .label {{ font-size: 11px; color: #718096; text-transform: uppercase; }}
.metric-card .value {{ font-size: 18px; font-weight: 700; color: #1a1a2e; }}
table.report-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
table.report-table th {{ background: #edf2f7; padding: 8px 12px; text-align: left; font-weight: 600; color: #4a5568; border-bottom: 2px solid #e2e8f0; }}
table.report-table td {{ padding: 8px 12px; border-bottom: 1px solid #e2e8f0; }}
table.report-table tr:hover {{ background: #f7fafc; }}
.chart-container {{ text-align: center; margin: 10px 0; }}
.badge {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }}
.badge-green {{ background: #c6f6d5; color: #22543d; }}
.badge-red {{ background: #fed7d7; color: #9b2c2c; }}
.badge-yellow {{ background: #fefcbf; color: #744210; }}
.footer {{ text-align: center; font-size: 12px; color: #a0aec0; padding: 20px; }}
@media print {{
    body {{ background: #fff; }}
    .container {{ max-width: 100%; padding: 0; }}
    .section {{ box-shadow: none; border: 1px solid #e2e8f0; break-inside: avoid; }}
    .header {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    .badge-green, .badge-red, .badge-yellow {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
}}
</style>
</head>
<body>
<div class="container">

<div class="header">
<h1>{company_name} ({symbol})</h1>
<div class="subtitle">Professional Research Report &mdash; {trade_date.isoformat()}</div>
<div class="meta">
    <span>Direction: {direction.upper()}</span>
    <span>Sector: {summary.get('sector') or 'N/A'}</span>
    <span>Industry: {summary.get('industry') or 'N/A'}</span>
    <span>Liquidity: {summary.get('liquidity_rating') or 'N/A'}</span>
</div>
<div class="price-row">
    <div class="price-box">
        <div class="label">Current Price</div>
        <div class="value">${current_price:,.2f}</div>
    </div>
    <div class="price-box">
        <div class="label">1D Change</div>
        <div class="value {price_chg_cls}">{price_chg_str}</div>
    </div>
    <div class="price-box">
        <div class="label">5D Change</div>
        <div class="value {'green' if (summary.get('price_change_5d_pct') or 0) >= 0 else 'red'}">{summary.get('price_change_5d_pct') or 'N/A'}{'%' if summary.get('price_change_5d_pct') is not None else ''}</div>
    </div>
    <div class="price-box">
        <div class="label">20D Change</div>
        <div class="value {'green' if (summary.get('price_change_20d_pct') or 0) >= 0 else 'red'}">{summary.get('price_change_20d_pct') or 'N/A'}{'%' if summary.get('price_change_20d_pct') is not None else ''}</div>
    </div>
    <div class="price-box">
        <div class="label">Regime</div>
        <div class="value" style="font-size:16px">{summary.get('trend_regime') or 'N/A'}</div>
    </div>
</div>
</div>

<div class="section">
<h2><span>01</span> Technical Analysis</h2>
<div class="grid-3">
    <div class="metric-card"><div class="label">RSI (14)</div><div class="value">{self._fmt(technical.get('rsi_14'))}{' — ' + self._rsi_label(technical.get('rsi_14')) if technical.get('rsi_14') is not None else ''}</div></div>
    <div class="metric-card"><div class="label">SMA (20)</div><div class="value">${self._fmt(technical.get('sma_20'))}</div></div>
    <div class="metric-card"><div class="label">SMA (50)</div><div class="value">${self._fmt(technical.get('sma_50'))}</div></div>
    <div class="metric-card"><div class="label">MACD</div><div class="value">{self._fmt(technical.get('macd'))}</div></div>
    <div class="metric-card"><div class="label">MACD Signal</div><div class="value">{self._fmt(technical.get('macd_signal'))}</div></div>
    <div class="metric-card"><div class="label">MACD Histogram</div><div class="value">{self._fmt(technical.get('macd_histogram'))}</div></div>
</div>
{sr_html}
<div class="chart-container">
<h3 style="margin:16px 0 8px;font-size:14px;color:#4a5568;">Price Trend (Last 30 Days)</h3>
{trend_html}
</div>
</div>

<div class="section">
<h2><span>02</span> Fundamental Analysis</h2>
{self._build_fundamental_html(fundamental, radar_html)}
</div>

<div class="section">
<h2><span>03</span> News & Sentiment</h2>
<div class="grid-2">
    <div class="metric-card"><div class="label">Articles (7d)</div><div class="value">{news_data.get('total_articles', 0)}</div></div>
    <div class="metric-card"><div class="label">Avg Sentiment</div><div class="value">{self._fmt(sentiment * 100 if sentiment is not None else None) + '%' if sentiment is not None else 'N/A'}</div></div>
</div>
{sentiment_html}
{news_table}
</div>

<div class="section">
<h2><span>04</span> Risk Assessment</h2>
<div class="grid-3">
    <div class="metric-card"><div class="label">Composite Risk</div><div class="value">{self._fmt(risk.get('composite_risk_score'))}</div></div>
    <div class="metric-card"><div class="label">Max DD (1M)</div><div class="value">{self._fmt(risk.get('max_drawdown_1m')) + '%' if risk.get('max_drawdown_1m') is not None else 'N/A'}</div></div>
    <div class="metric-card"><div class="label">Max DD (3M)</div><div class="value">{self._fmt(risk.get('max_drawdown_3m')) + '%' if risk.get('max_drawdown_3m') is not None else 'N/A'}</div></div>
    <div class="metric-card"><div class="label">Volatility (20D)</div><div class="value">{self._fmt(risk.get('volatility_20d'))}</div></div>
    <div class="metric-card"><div class="label">Volatility (60D)</div><div class="value">{self._fmt(risk.get('volatility_60d'))}</div></div>
    <div class="metric-card"><div class="label">Event Risk</div><div class="value">{self._fmt(risk.get('event_risk_score'))}</div></div>
</div>
<div class="grid-2" style="margin-top:16px;">
    <div class="metric-card">
        <div class="label">Liquidity Score</div>
        <div class="value">{self._fmt(risk.get('liquidity_score'))} / 100</div>
    </div>
    <div class="metric-card">
        <div class="label">Liquidity Rating</div>
        <div class="value">{risk.get('liquidity_rating') or 'N/A'}</div>
    </div>
</div>
<div class="chart-container">
{gauge_html}
</div>
</div>

<div class="section">
<h2><span>05</span> Price Prediction</h2>
{self._build_prediction_html(prediction)}
</div>

<div class="footer">
<p>Generated by TitanX Research Platform &mdash; {trade_date.isoformat()}</p>
<p>This report is for informational purposes only. Not investment advice.</p>
</div>

</div>
</body>
</html>"""

    # ---- SVG chart helpers ----

    def _svg_trend_chart(self, trend_data: list[dict]) -> str:
        if not trend_data:
            return "<p style='color:#a0aec0;font-size:13px;'>No price data available</p>"
        w, h = 700, 260
        pad = {"t": 20, "r": 20, "b": 30, "l": 50}
        cw, ch = w - pad["l"] - pad["r"], h - pad["t"] - pad["b"]

        prices = [p["close"] for p in trend_data]
        if not prices:
            return ""
        mn, mx = min(prices), max(prices)
        rng = mx - mn or 1

        pts = []
        for i, p in enumerate(prices):
            x = pad["l"] + cw * i / (len(prices) - 1)
            y = pad["t"] + ch - ch * (p - mn) / rng
            pts.append(f"{x:.1f},{y:.1f}")

        polyline = " ".join(pts)
        fill_pts = f"{pts[0].split(',')[0]},{pad['t'] + ch} {polyline} {pts[-1].split(',')[0]},{pad['t'] + ch}"

        labels = []
        step = max(1, len(prices) // 6)
        for i in range(0, len(prices), step):
            x = pad["l"] + cw * i / (len(prices) - 1)
            lbl = trend_data[i].get("date", "")[-5:] if trend_data[i].get("date") else ""
            labels.append(
                f'<text x="{x:.1f}" y="{pad["t"] + ch + 16}" text-anchor="middle" font-size="10" fill="#718096">{lbl}</text>'
            )

        y_ticks = 4
        ylabels = []
        for i in range(y_ticks + 1):
            val = mn + rng * i / y_ticks
            y = pad["t"] + ch - ch * i / y_ticks
            ylabels.append(
                f'<text x="{pad["l"] - 8}" y="{y + 4}" text-anchor="end" font-size="10" fill="#718096">${val:.2f}</text>'
                f'<line x1="{pad["l"]}" y1="{y}" x2="{w - pad["r"]}" y2="{y}" stroke="#e2e8f0" stroke-width="0.5"/>'
            )

        color = "#48bb78" if prices[-1] >= prices[0] else "#f56565"
        return f"""<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="max-width:100%;height:auto;">
{''.join(ylabels)}
{''.join(labels)}
<polygon points="{fill_pts}" fill="{color}15" />
<polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>
<circle cx="{pts[-1].split(',')[0]}" cy="{pts[-1].split(',')[1]}" r="4" fill="{color}"/>
</svg>"""

    def _svg_risk_gauge(self, risk_score: float | None) -> str:
        if risk_score is None:
            return "<p style='color:#a0aec0;font-size:13px;'>Risk data not available</p>"
        score = max(0, min(100, risk_score))
        angle = 180 * (1 - score / 100)
        rad = math.radians(angle)
        cx, cy, r = 200, 180, 140
        ex = cx + r * math.cos(rad)
        ey = cy - r * math.sin(rad)

        color = "#48bb78" if score < 30 else "#ecc94b" if score < 60 else "#f56565"

        segments = [
            (180, 120, "#48bb78"), (120, 60, "#ecc94b"), (60, 0, "#f56565"),
        ]

        seg_paths = ""
        for start_angle, end_angle, seg_color in segments:
            for a in range(start_angle - 1, end_angle - 1, -2):
                a2 = max(end_angle, a - 2)
                r1 = math.radians(a)
                r2 = math.radians(a2)
                x1 = cx + r * math.cos(r1)
                y1 = cy - r * math.sin(r1)
                x2 = cx + r * math.cos(r2)
                y2 = cy - r * math.sin(r2)
                seg_paths += f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{seg_color}" stroke-width="6" stroke-linecap="round"/>\n'

        return f"""<svg width="400" height="220" viewBox="0 0 400 220" style="max-width:100%;height:auto;">
{seg_paths}
<line x1="{cx - r - 10}" y1="{cy}" x2="{cx + r + 10}" y2="{cy}" stroke="#e2e8f0" stroke-width="2"/>
<circle cx="{ex:.1f}" cy="{ey:.1f}" r="6" fill="{color}" stroke="#fff" stroke-width="2"/>
<line x1="{cx}" y1="{cy}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="{color}" stroke-width="2"/>
<circle cx="{cx}" cy="{cy}" r="4" fill="#1a1a2e"/>
<text x="{cx}" y="{cy - 50}" text-anchor="middle" font-size="32" font-weight="700" fill="#1a1a2e">{score:.0f}</text>
<text x="{cx}" y="{cy - 28}" text-anchor="middle" font-size="12" fill="#718096">Risk Score</text>
<text x="{cx - r - 10}" y="{cy + 18}" text-anchor="start" font-size="11" fill="#48bb78">Low</text>
<text x="{cx + r + 10}" y="{cy + 18}" text-anchor="end" font-size="11" fill="#f56565">High</text>
</svg>"""

    def _svg_sentiment_bar(self, sentiment: float | None) -> str:
        if sentiment is None:
            return ""
        pct = max(0, min(100, sentiment * 100))
        color = "#48bb78" if pct >= 50 else "#ecc94b" if pct >= 30 else "#f56565"
        return f"""<svg width="400" height="50" viewBox="0 0 400 50" style="max-width:100%;height:auto;margin-top:10px;">
<rect x="0" y="16" width="400" height="18" rx="9" fill="#edf2f7"/>
<rect x="0" y="16" width="{4 * pct:.1f}" height="18" rx="9" fill="{color}"/>
<text x="{4 * pct + 8:.1f}" y="29" font-size="13" font-weight="600" fill="{color}">{pct:.1f}% Positive</text>
</svg>"""

    def _svg_fundamental_radar(self, fundamental: dict) -> str:
        if not fundamental.get("available"):
            return ""
        dims = [
            ("P/E", fundamental.get("pe_ratio"), 50),
            ("D/E", fundamental.get("debt_to_equity"), 2),
            ("Profit Margin", fundamental.get("profit_margin"), 0.2),
            ("Revenue Growth", fundamental.get("revenue_growth"), 0.3),
            ("ROE", fundamental.get("roe"), 0.3),
            ("Current Ratio", fundamental.get("current_ratio"), 3),
        ]
        cx, cy, r = 200, 180, 130
        n = len(dims)
        pts = []
        labels = []
        for i, (name, val, max_val) in enumerate(dims):
            if val is None:
                return ""
            angle = math.radians(90 - 360 * i / n)
            norm = min(1.0, abs(val) / max_val if max_val else 0)
            x = cx + r * norm * math.cos(angle)
            y = cy - r * norm * math.sin(angle)
            pts.append(f"{x:.1f},{y:.1f}")
            lx = cx + (r + 20) * math.cos(angle)
            ly = cy - (r + 20) * math.sin(angle)
            anchor = "middle" if abs(lx - cx) < 10 else ("start" if lx > cx else "end")
            labels.append(
                f'<text x="{lx:.1f}" y="{ly + 4}" text-anchor="{anchor}" font-size="11" fill="#4a5568">{name}</text>'
            )

        grid = ""
        for level in range(1, 5):
            lr = r * level / 4
            gp = " ".join(
                f"{cx + lr * math.cos(math.radians(90 - 360 * i / n)):.1f},{cy - lr * math.sin(math.radians(90 - 360 * i / n)):.1f}"
                for i in range(n + 1)
            )
            grid += f'<polygon points="{gp}" fill="none" stroke="#e2e8f0" stroke-width="0.5"/>\n'

        return f"""<svg width="400" height="360" viewBox="0 0 400 360" style="max-width:100%;height:auto;">
{grid}
{''.join(labels)}
<polygon points="{' '.join(pts)}" fill="#667eea30" stroke="#667eea" stroke-width="2"/>
<circle cx="{pts[-1].split(',')[0]}" cy="{pts[-1].split(',')[1]}" r="3" fill="#667eea"/>
</svg>"""

    # ---- HTML fragment builders ----

    def _build_sr_table(self, technical: dict) -> str:
        supports = technical.get("support_levels", [])
        resistances = technical.get("resistance_levels", [])
        if not supports and not resistances:
            return ""

        rows = ""
        for s in supports:
            rows += f"<tr><td><span class='badge badge-green'>S</span> Support</td><td>${s['price']:,.2f}</td><td>{s.get('strength', 0):.0f}</td></tr>"
        for r in resistances:
            rows += f"<tr><td><span class='badge badge-red'>R</span> Resistance</td><td>${r['price']:,.2f}</td><td>{r.get('strength', 0):.0f}</td></tr>"

        return f"""<h3 style="margin:16px 0 8px;font-size:14px;color:#4a5568;">Support & Resistance Levels</h3>
<table class="report-table">
<thead><tr><th>Type</th><th>Price</th><th>Strength</th></tr></thead>
<tbody>{rows}</tbody>
</table>"""

    def _build_news_table(self, news_data: dict) -> str:
        articles = news_data.get("articles", [])
        if not articles:
            return "<p style='color:#a0aec0;font-size:13px;margin-top:12px;'>No recent news articles found</p>"

        rows = ""
        for a in articles:
            sent = a.get("sentiment_positive")
            badge = "badge-green" if sent and sent >= 0.5 else "badge-yellow" if sent and sent >= 0.3 else "badge-red"
            rows += f"""<tr>
<td>{a.get('title', '')[:60]}{'...' if len(a.get('title', '')) > 60 else ''}</td>
<td>{a.get('published_at', '')[:10]}</td>
<td>{a.get('source', '')}</td>
<td><span class="badge {badge}">{f'{sent*100:.0f}%' if sent is not None else 'N/A'}</span></td>
</tr>"""

        return f"""<table class="report-table" style="margin-top:12px;">
<thead><tr><th>Title</th><th>Date</th><th>Source</th><th>Sentiment</th></tr></thead>
<tbody>{rows}</tbody>
</table>"""

    def _build_fundamental_html(self, fundamental: dict, radar_html: str) -> str:
        if not fundamental.get("available"):
            return "<p style='color:#a0aec0;font-size:13px;'>No fundamental data available</p>"

        def card(label: str, val, suffix: str = "") -> str:
            v = f"{val:.2f}{suffix}" if val is not None else "N/A"
            return f'<div class="metric-card"><div class="label">{label}</div><div class="value">{v}</div></div>'

        grid = f"""<div class="grid-3">
{card('P/E Ratio', fundamental.get('pe_ratio'))}
{card('P/B Ratio', fundamental.get('pb_ratio'))}
{card('Debt/Equity', fundamental.get('debt_to_equity'))}
{card('Current Ratio', fundamental.get('current_ratio'))}
{card('Profit Margin', fundamental.get('profit_margin'), '%')}
{card('Revenue Growth', fundamental.get('revenue_growth'), '%')}
{card('EPS Growth', fundamental.get('eps_growth'), '%')}
{card('ROE', fundamental.get('roe'), '%')}
{card('ROA', fundamental.get('roa'), '%')}
</div>"""

        extra = ""
        div_yield = fundamental.get("dividend_yield")
        mc = fundamental.get("market_cap")
        if div_yield is not None:
            extra += f"""<div class="grid-2" style="margin-top:12px;">
{card('Dividend Yield', div_yield, '%')}
{card('Market Cap', mc) if mc is not None else ''}
</div>"""

        return grid + extra + f"""<div class="chart-container">{radar_html}</div>"""

    def _build_prediction_html(self, prediction: dict) -> str:
        if not prediction.get("available"):
            return "<p style='color:#a0aec0;font-size:13px;'>Insufficient data for prediction</p>"

        direction = prediction.get("direction", "bullish")
        targets = []
        for i in range(1, 4):
            price = prediction.get(f"target_{i}_price")
            pct = prediction.get(f"target_{i}_pct")
            if price is not None:
                cls = "green" if (pct or 0) >= 0 else "red"
                targets.append(
                    f'<div class="metric-card"><div class="label">Target {i}</div>'
                    f'<div class="value {cls}">${price:,.2f} <span style="font-size:14px;font-weight:400;">({pct:+.2f}%)</span></div></div>'
                )

        holding_days = prediction.get("expected_holding_days")
        return f"""<div class="grid-3">
{''.join(targets)}
</div>
<div class="grid-3" style="margin-top:12px;">
<div class="metric-card"><div class="label">Current Price</div><div class="value">${prediction.get('current_price', 0):,.2f}</div></div>
<div class="metric-card"><div class="label">Expected Holding Days</div><div class="value">{holding_days or 'N/A'}</div></div>
<div class="metric-card"><div class="label">Direction</div><div class="value">{direction.title()}</div></div>
</div>
<div class="grid-3" style="margin-top:12px;">
<div class="metric-card"><div class="label">RSI (14)</div><div class="value">{self._fmt(prediction.get('rsi_14'))}</div></div>
<div class="metric-card"><div class="label">Momentum (10D)</div><div class="value {'green' if (prediction.get('momentum_10d_pct') or 0) >= 0 else 'red'}">{self._fmt(prediction.get('momentum_10d_pct')) + '%' if prediction.get('momentum_10d_pct') is not None else 'N/A'}</div></div>
<div class="metric-card"><div class="label">Volatility (20D)</div><div class="value">{self._fmt(prediction.get('volatility_20d'))}</div></div>
</div>"""

    # ---- Private helpers ----

    def _fmt(self, val: float | None) -> str:
        if val is None:
            return "N/A"
        if isinstance(val, float):
            return f"{val:.2f}"
        return str(val)

    def _rsi_label(self, val: float | None) -> str:
        if val is None:
            return ""
        if val >= 70:
            return "Overbought"
        if val <= 30:
            return "Oversold"
        return "Neutral"

    async def _load_prices(
        self, symbol: str, as_of_date: date, lookback: int = 400,
    ) -> list[DailyPrice]:
        start = as_of_date - timedelta(days=lookback)
        r = await self.session.execute(
            select(DailyPrice).where(
                DailyPrice.symbol == symbol,
                DailyPrice.trade_date <= as_of_date,
                DailyPrice.trade_date >= start,
            ).order_by(DailyPrice.trade_date)
        )
        return list(r.scalars().all())

    async def _get_latest_regime(self, symbol: str) -> MarketRegime | None:
        r = await self.session.execute(
            select(MarketRegime).where(MarketRegime.symbol == symbol)
            .order_by(desc(MarketRegime.as_of_date)).limit(1)
        )
        return r.scalar_one_or_none()

    async def _get_latest_liquidity(self, symbol: str) -> MarketMicrostructure | None:
        r = await self.session.execute(
            select(MarketMicrostructure).where(MarketMicrostructure.symbol == symbol)
            .order_by(desc(MarketMicrostructure.as_of_date)).limit(1)
        )
        return r.scalar_one_or_none()

    def _sma(self, values: list[float], period: int) -> float | None:
        if len(values) < period:
            return None
        return round(sum(values[-period:]) / period, 2)

    def _rsi(self, closes: list[float], period: int = 14) -> float | None:
        if len(closes) < period + 1:
            return None
        gains, losses = 0.0, 0.0
        for i in range(-period, 0):
            diff = closes[i] - closes[i - 1]
            if diff > 0:
                gains += diff
            else:
                losses -= diff
        avg_gain = gains / period
        avg_loss = losses / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100 - 100 / (1 + rs), 2)

    def _atr(self, prices: list[DailyPrice], period: int = 14) -> list[float | None]:
        if len(prices) < 2:
            return []
        tr_values = []
        for i in range(1, len(prices)):
            hl = prices[i].high - prices[i].low
            hc = abs(prices[i].high - prices[i - 1].close)
            lc = abs(prices[i].low - prices[i - 1].close)
            tr_values.append(max(hl, hc, lc))
        if len(tr_values) < period:
            return [None] * len(tr_values)
        atr_list: list[float | None] = [None] * (period - 1)
        atr_list.append(sum(tr_values[:period]) / period)
        for i in range(period, len(tr_values)):
            atr_list.append((atr_list[-1] * (period - 1) + tr_values[i]) / period)
        return atr_list

    def _std(self, values: list[float]) -> float:
        if len(values) < 2:
            return 0
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return math.sqrt(variance)
