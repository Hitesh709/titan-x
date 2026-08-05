"""Demo seed logic for the TITAN X database.

Idempotent: re-running replaces the seeded rows (companies, prices, sector
performance, market breadth) and resets the demo user's watchlists, AI scores,
news and monitor events. The demo user's paper account is created once and is
never reset, so paper-trading history placed via the Trading tab survives.
"""
import random
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from titan_x.core.security import hash_password
from titan_x.models.company import Company
from titan_x.models.dynamic_ai_score import DynamicAIScore
from titan_x.models.market_breadth import MarketBreadth
from titan_x.models.news import NewsArticle, NewsArticleCategory, NewsCategory
from titan_x.models.paper_trading import PaperAccount
from titan_x.models.price import DailyPrice
from titan_x.models.sector import SectorPerformance
from titan_x.models.user import User
from titan_x.models.watchlist import Watchlist, WatchlistItem, WatchlistMonitorEvent

DEMO_EMAIL = "demo@titanx.app"
DEMO_PASSWORD = "Demo1234!"
DEMO_NAME = "Demo User"

# (symbol, name, sector, industry, exchange, base_price, drift_pct, volatility_pct)
COMPANIES = [
    ("RELIANCE", "Reliance Industries Ltd", "Energy", "Oil & Gas", "NSE", 1300.0, 0.0012, 0.013),
    ("TCS", "Tata Consultancy Services Ltd", "Technology", "IT Services", "NSE", 2460.0, 0.0010, 0.012),
    ("HDFCBANK", "HDFC Bank Ltd", "Financials", "Banks", "NSE", 1750.0, 0.0011, 0.011),
    ("INFY", "Infosys Ltd", "Technology", "IT Services", "NSE", 1520.0, 0.0009, 0.014),
    ("ICICIBANK", "ICICI Bank Ltd", "Financials", "Banks", "NSE", 1250.0, 0.0013, 0.012),
    ("BHARTIARTL", "Bharti Airtel Ltd", "Communication Services", "Telecom", "NSE", 1450.0, 0.0014, 0.012),
    ("SBIN", "State Bank of India", "Financials", "Banks", "NSE", 790.0, 0.0010, 0.014),
    ("ITC", "ITC Ltd", "Consumer Staples", "Tobacco & FMCG", "NSE", 460.0, 0.0007, 0.010),
    ("LT", "Larsen & Toubro Ltd", "Industrials", "Engineering & Construction", "NSE", 3750.0, 0.0011, 0.013),
    ("HINDUNILVR", "Hindustan Unilever Ltd", "Consumer Staples", "FMCG", "NSE", 2450.0, 0.0004, 0.009),
    ("KOTAKBANK", "Kotak Mahindra Bank Ltd", "Financials", "Banks", "NSE", 1950.0, 0.0008, 0.011),
    ("BAJFINANCE", "Bajaj Finance Ltd", "Financials", "Financial Services", "NSE", 7200.0, 0.0012, 0.015),
    ("AXISBANK", "Axis Bank Ltd", "Financials", "Banks", "NSE", 1130.0, 0.0010, 0.013),
    ("MARUTI", "Maruti Suzuki India Ltd", "Consumer Discretionary", "Automobiles", "NSE", 12400.0, 0.0008, 0.012),
    ("TITAN", "Titan Company Ltd", "Consumer Discretionary", "Retail", "NSE", 3400.0, 0.0011, 0.014),
    ("SUNPHARMA", "Sun Pharmaceutical Industries Ltd", "Health Care", "Pharmaceuticals", "NSE", 1580.0, 0.0009, 0.011),
    ("ADANIENT", "Adani Enterprises Ltd", "Industrials", "Infrastructure", "NSE", 2400.0, 0.0016, 0.018),
    ("WIPRO", "Wipro Ltd", "Technology", "IT Services", "NSE", 520.0, 0.0005, 0.012),
    ("ONGC", "Oil & Natural Gas Corporation Ltd", "Energy", "Oil & Gas", "NSE", 260.0, 0.0007, 0.012),
    ("NTPC", "NTPC Ltd", "Utilities", "Power", "NSE", 340.0, 0.0008, 0.010),
    ("POWERGRID", "Power Grid Corporation of India Ltd", "Utilities", "Power", "NSE", 300.0, 0.0007, 0.010),
    ("ASIANPAINT", "Asian Paints Ltd", "Materials", "Chemicals", "NSE", 2800.0, 0.0003, 0.011),
    ("ULTRACEMCO", "UltraTech Cement Ltd", "Materials", "Cement", "NSE", 10800.0, 0.0006, 0.012),
    ("HCLTECH", "HCL Technologies Ltd", "Technology", "IT Services", "NSE", 1750.0, 0.0008, 0.012),
    ("TATAMOTORS", "Tata Motors Ltd", "Consumer Discretionary", "Automobiles", "NSE", 1050.0, 0.0013, 0.016),
    ("JSWSTEEL", "JSW Steel Ltd", "Materials", "Steel", "NSE", 950.0, 0.0009, 0.015),
]

SECTOR_HEADERS = [
    "Semiconductors rally on AI demand", "Fed signals cautious rate path ahead",
    "Earnings beat drives sector rotation", "Treasury yields ease, growth stocks climb",
    "Oil prices firm on supply concerns", "Tech leads as Nasdaq hits fresh high",
    "Consumer staples pressured by inflation data", "Banking sector resilient despite headwinds",
    "Renewables get policy boost", "Chipmakers surge on data-center orders",
]


def _isin(index: int) -> str:
    return f"INE{1000000 + index:06d}00A"


def _trading_days(days: int) -> list[date]:
    out: list[date] = []
    d = date.today()
    while len(out) < days:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    out.reverse()
    return out


def _sector_of(symbol: str) -> str:
    for comp in COMPANIES:
        if comp[0] == symbol:
            return comp[2]
    return "Other"


async def seed_market_data(session_factory: async_sessionmaker) -> None:
    async with session_factory() as session:
        async with session.begin():
            await session.execute(delete(DailyPrice))
            await session.execute(delete(SectorPerformance))
            await session.execute(delete(MarketBreadth))
            await session.execute(delete(Company))

            days = _trading_days(260)
            symbols_by_sector: dict[str, list[str]] = {}

            for index, (symbol, name, sector, industry, exchange, base, drift, vol) in enumerate(COMPANIES):
                session.add(Company(
                    symbol=symbol, company_name=name, isin=_isin(index),
                    sector=sector, industry=industry, exchange=exchange,
                    market_cap=int(base * 1_000_000),
                    listing_date=date(2000, 1, 1), status="active",
                    description=f"{name} demo company", website=f"https://example.com/{symbol}",
                ))
                symbols_by_sector.setdefault(sector, []).append(symbol)

            await session.flush()

            # Real daily history from Yahoo Finance per company; falls back to a
            # synthetic random walk when the upstream is unreachable.
            real: dict[str, dict[date, tuple[float, float, float, float, int]]] = {}
            provider = None
            try:
                from titan_x.infrastructure.market_data_providers import YahooFinanceProvider
                provider = YahooFinanceProvider()
                for symbol, *_ in COMPANIES:
                    points = await provider.get_historical_prices(symbol)
                    real[symbol] = {p.trade_date: (p.open, p.high, p.low, p.close, p.volume) for p in points}
            except Exception:
                real = {}
            finally:
                if provider is not None:
                    await provider.close()

            if real:
                days = sorted({d for m in real.values() for d in m})
            else:
                days = _trading_days(260)

            closes: dict[str, list[float]] = {symbol: [] for symbol, *_ in COMPANIES}
            for d in days:
                for symbol, _name, _sector, _ind, _exch, base, drift, vol in COMPANIES:
                    row = real.get(symbol, {}).get(d)
                    if row is not None:
                        o, h, l, c, v = row
                        closes[symbol].append(c)
                        session.add(DailyPrice(
                            symbol=symbol, trade_date=d, open=round(o, 2),
                            high=round(h, 2), low=round(l, 2), close=round(c, 2),
                            volume=int(v or 0),
                        ))
                        continue
                    shock = random.gauss(0, 1)
                    close = base if not closes[symbol] else max(1.0, closes[symbol][-1] * (1 + drift + shock * vol))
                    closes[symbol].append(close)
                    opn = closes[symbol][-2] if len(closes[symbol]) > 1 else close * (1 - drift)
                    high = max(opn, close) * (1 + abs(random.gauss(0, vol * 0.5)))
                    low = min(opn, close) * (1 - abs(random.gauss(0, vol * 0.5)))
                    session.add(DailyPrice(
                        symbol=symbol, trade_date=d, open=round(opn, 2),
                        high=round(high, 2), low=round(low, 2), close=round(close, 2),
                        volume=int(random.uniform(1e6, 6e7)),
                    ))

            await session.flush()

            # Sector performance per period label (computed from generated closes)
            period_days = {"1W": 7, "1M": 30, "3M": 90, "6M": 180, "1Y": 260}
            for period, back in period_days.items():
                for sector, syms in symbols_by_sector.items():
                    rets = []
                    for s in syms:
                        closes_list = closes[s]
                        end = closes_list[-1]
                        start = closes_list[-1 - back] if back < len(closes_list) else closes_list[0]
                        if start > 0:
                            rets.append((end - start) / start * 100)
                    avg = sum(rets) / len(rets) if rets else 0.0
                    session.add(SectorPerformance(
                        sector=sector, as_of_date=date.today(), period_label=period,
                        return_pct=round(avg, 2),
                        momentum_score=round(50 + avg * 2.5, 2),
                        relative_strength=round(avg - sum(rets) / max(1, len(rets)) + 50, 2),
                        rank=1, constituent_count=len(syms),
                    ))

            # Market breadth for today
            session.add(MarketBreadth(
                trade_date=date.today(),
                advancing=420, declining=310, unchanged=45, total_stocks=775,
                advancing_volume=420_000_000, declining_volume=310_000_000,
                unchanged_volume=45_000_000, total_volume=775_000_000,
                new_highs=86, new_lows=31,
                advance_decline_ratio=1.35, breadth_oscillator=14.5, index_strength_score=62.0,
            ))

    print(f"Seeded {len(COMPANIES)} companies, {len(days)} trading days, sector performance, market breadth")


async def seed_demo_user(session_factory: async_sessionmaker) -> User:
    async with session_factory() as session:
        async with session.begin():
            user = (await session.execute(select(User).where(User.email == DEMO_EMAIL))).scalar_one_or_none()
            if user is None:
                user = User(email=DEMO_EMAIL, hashed_password=hash_password(DEMO_PASSWORD))
                session.add(user)
                await session.flush()
                print(f"Created demo user {DEMO_EMAIL} / {DEMO_PASSWORD}")

            # Reset user-scoped data so the script is idempotent
            await session.execute(delete(WatchlistMonitorEvent).where(WatchlistMonitorEvent.user_id == user.id))
            await session.execute(delete(DynamicAIScore))  # demo scores keyed by symbol only
            await session.execute(delete(NewsArticleCategory))
            await session.execute(delete(NewsArticle))
            await session.execute(delete(NewsCategory))

            await session.execute(
                delete(WatchlistItem).where(WatchlistItem.watchlist_id.in_(
                    select(Watchlist.id).where(Watchlist.user_id == user.id)
                ))
            )
            await session.execute(delete(Watchlist).where(Watchlist.user_id == user.id))
            await session.flush()

            # Paper account — created only if missing, never wiped on restart so
            # real paper-trading history (Trading tab orders) is preserved.
            account = (await session.execute(
                select(PaperAccount).where(PaperAccount.user_id == user.id)
            )).scalar_one_or_none()
            if account is None:
                account = PaperAccount(
                    user_id=user.id, initial_capital=10_000_000.00,
                    cash_balance=10_000_000.00, currency="INR", is_active=True,
                )
                session.add(account)
                await session.flush()

            # Watchlists
            wl1 = Watchlist(user_id=user.id, name="Tech & AI", description="Core growth names", is_default=True)
            wl2 = Watchlist(user_id=user.id, name="Dividend Income", description="Blue-chip income names", is_default=False)
            session.add_all([wl1, wl2])
            await session.flush()

            wl1_symbols = ["TCS", "INFY", "WIPRO", "HCLTECH", "BHARTIARTL", "RELIANCE", "TITAN", "ADANIENT"]
            wl2_symbols = ["ITC", "HINDUNILVR", "SBIN", "ONGC", "NTPC", "POWERGRID", "KOTAKBANK", "AXISBANK"]
            for s in wl1_symbols:
                session.add(WatchlistItem(watchlist_id=wl1.id, symbol=s, sort_order=0))
            for s in wl2_symbols:
                session.add(WatchlistItem(watchlist_id=wl2.id, symbol=s, sort_order=0))
            await session.flush()

            # AI scores for watchlisted symbols
            signals = [
                ("RELIANCE", "buy", 0.80), ("TCS", "buy", 0.77), ("HDFCBANK", "buy", 0.74),
                ("INFY", "strong_buy", 0.85), ("ICICIBANK", "buy", 0.79), ("BHARTIARTL", "strong_buy", 0.86),
                ("SBIN", "buy", 0.73), ("ITC", "hold", 0.58),
                ("LT", "buy", 0.76), ("HINDUNILVR", "hold", 0.52), ("KOTAKBANK", "buy", 0.72),
                ("AXISBANK", "hold", 0.61), ("WIPRO", "buy", 0.68), ("TITAN", "buy", 0.70),
                ("NTPC", "hold", 0.55), ("ONGC", "buy", 0.66),
            ]
            for symbol, signal, conf in signals:
                session.add(DynamicAIScore(
                    symbol=symbol, as_of_date=date.today(),
                    technical_score=round(random.uniform(40, 85), 1), technical_signal=signal, technical_confidence=conf,
                    fundamental_score=round(random.uniform(45, 88), 1), fundamental_signal=signal, fundamental_confidence=conf,
                    news_score=round(random.uniform(40, 80), 1), news_signal="neutral", news_confidence=0.6,
                    macro_score=round(random.uniform(45, 82), 1), macro_signal="neutral", macro_confidence=0.6,
                    liquidity_score=round(random.uniform(50, 90), 1), liquidity_signal="positive", liquidity_confidence=0.7,
                    risk_score=round(random.uniform(40, 75), 1), risk_signal="neutral", risk_confidence=0.6,
                    market_regime_score=round(random.uniform(45, 80), 1), market_regime_signal="neutral", market_regime_confidence=0.6,
                    combined_score=round(55 + conf * 35, 1), combined_signal=signal, combined_confidence=conf,
                ))

            # News articles (watchlist symbols, last 3 days)
            tech_cat = NewsCategory(name="Markets", description="Market-moving news")
            session.add(tech_cat)
            await session.flush()
            now = datetime.now(timezone.utc)
            for idx, symbol in enumerate(wl1_symbols[:6] + wl2_symbols[:4]):
                header = SECTOR_HEADERS[idx % len(SECTOR_HEADERS)]
                session.add(NewsArticle(
                    title=f"{symbol}: {header}",
                    summary=f"Demo market update for {symbol}. Analysts weigh the latest catalysts.",
                    content=f"Full demo article content for {symbol}.",
                    source="TITAN X Wire", source_id=f"demo-{symbol}-{idx}",
                    url=f"https://example.com/news/{idx}",
                    url_hash=f"demo{idx}{symbol}", symbol=symbol, author="Research Desk",
                    published_at=now - timedelta(hours=idx * 5), language="en", is_cleaned=True,
                    categories=[tech_cat],
                ))

            # Monitor events (recent alerts)
            event_titles = {
                "price_above": "Price above alert threshold",
                "volatility": "Volatility spike detected",
                "volume": "Unusual volume surge",
                "trend": "Trend change detected",
            }
            event_types = list(event_titles.keys())
            for idx in range(8):
                symbol = (wl1_symbols + wl2_symbols)[idx]
                etype = event_types[idx % len(event_types)]
                session.add(WatchlistMonitorEvent(
                    user_id=user.id, symbol=symbol, event_type=etype,
                    severity="critical" if idx % 5 == 0 else "warning" if idx % 2 else "info",
                    title=event_titles[etype], message=f"{symbol} triggered a {etype} event in the demo feed.",
                    previous_value=f"{random.uniform(100, 400):.2f}", current_value=f"{random.uniform(100, 400):.2f}",
                    change_pct=round(random.uniform(-5, 8), 2),
                    is_read=(idx >= 4), triggered_at=now - timedelta(minutes=idx * 7),
                ))

            print(f"Seeded demo user (id={user.id}), paper account, watchlists, AI scores, news, alerts")
            return user


async def seed_all(session_factory: async_sessionmaker) -> None:
    random.seed(42)
    await seed_market_data(session_factory)
    from titan_x.services.index_service import IndexService

    async with session_factory() as session:
        async with session.begin():
            result = await IndexService(session).seed()
        print(f"Seeded indices: {result}")
    await seed_demo_user(session_factory)
    print("Seed complete.")
