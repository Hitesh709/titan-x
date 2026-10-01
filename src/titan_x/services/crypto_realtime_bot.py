"""Event-driven crypto paper bot runner.

Consumes the shared Binance WebSocket market cache. It never calls REST in the
hot path and only writes a database row when a real paper position transition
occurs.
"""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from titan_x.models.crypto_bot import CryptoPaperBotState
from titan_x.models.crypto_paper import CryptoPaperAccount, CryptoPaperPosition, CryptoPaperTrade
from titan_x.services.crypto_realtime_market import MARKET, TIMEFRAMES

D = Decimal


def _ema(values: list[float], n: int) -> list[float]:
    if not values:
        return []
    k = 2 / (n + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append(out[-1] + (value - out[-1]) * k)
    return out


def _signal(candles: list[dict[str, float]]) -> tuple[str, float, float]:
    if len(candles) < 60:
        return "HOLD", 0.0, 0.0
    close = [x["close"] for x in candles]
    e9, e20, e50 = _ema(close, 9)[-1], _ema(close, 20)[-1], _ema(close, 50)[-1]
    gains, losses = [], []
    for a, b in zip(close[-15:-1], close[-14:]):
        d = b - a
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_loss = max(sum(losses) / 14, 1e-12)
    rsi = 100 - 100 / (1 + (sum(gains) / 14) / avg_loss)
    m12, m26 = _ema(close, 12), _ema(close, 26)
    mac = [a - b for a, b in zip(m12, m26)]
    mac_signal = _ema(mac, 9)[-1]
    volumes = [x["volume"] for x in candles]
    volume_ok = volumes[-1] >= sum(volumes[-20:]) / min(20, len(volumes))
    bull = e9 > e20 > e50 and close[-1] > e20 and rsi > 52 and mac[-1] > mac_signal
    bear = e9 < e20 < e50 and close[-1] < e20 and rsi < 48 and mac[-1] < mac_signal
    if bull and volume_ok:
        return "BUY", close[-1], rsi
    if bear and volume_ok:
        return "SELL", close[-1], rsi
    return "HOLD", close[-1], rsi


def _mtf(snapshot: dict[str, Any]) -> tuple[str, float, str]:
    decisions = []
    price = float(snapshot.get("price") or 0)
    for tf in TIMEFRAMES:
        decision, tf_price, _ = _signal(snapshot["candles"].get(tf, []))
        decisions.append(decision)
        price = tf_price or price
    final = "BUY" if decisions == ["BUY", "BUY", "BUY"] else "SELL" if decisions == ["SELL", "SELL", "SELL"] else "HOLD"
    return final, price, "/".join(decisions)


class CryptoRealtimeBotRunner:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self.last_cycle_ms = 0
        self.cycles = 0
        self.trades = 0
        self.enabled_users = 0
        self._last_config_refresh = 0.0
        self._enabled_by_symbol: dict[str, list[tuple[int, float, float]]] = {}

    async def start(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        if self._task and not self._task.done():
            return
        await MARKET.start()
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(session_factory), name="crypto-realtime-bot")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await MARKET.stop()

    async def _refresh_config(self, session: AsyncSession) -> None:
        rows = (
            await session.execute(
                select(CryptoPaperBotState).where(CryptoPaperBotState.enabled.is_(True))
            )
        ).scalars().all()
        self._enabled_by_symbol = {}
        for row in rows:
            self._enabled_by_symbol.setdefault(row.symbol.upper(), []).append(
                (row.user_id, float(row.risk_per_trade), float(row.max_position_pct))
            )
        self.enabled_users = sum(len(v) for v in self._enabled_by_symbol.values())

    async def _loop(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        while not self._stop.is_set():
            started = time.perf_counter()
            try:
                changed = MARKET.consume_changed_symbols()
                now = time.monotonic()
                if now - self._last_config_refresh >= 2.0:
                    async with session_factory() as session:
                        await self._refresh_config(session)
                    self._last_config_refresh = now

                for symbol in changed:
                    if symbol not in self._enabled_by_symbol:
                        continue
                    snapshot = MARKET.snapshot(symbol)
                    action, price, details = _mtf(snapshot)
                    if not price or action == "HOLD":
                        continue
                    for user_id, _, max_position_pct in self._enabled_by_symbol[symbol]:
                        async with session_factory() as session:
                            await self._execute(session, user_id, symbol, action, price, details, max_position_pct)
                            await session.commit()
                self.cycles += 1
                self.last_cycle_ms = int((time.perf_counter() - started) * 1000)
            except asyncio.CancelledError:
                raise
            except Exception:
                # One bad user/order must not stop the market engine.
                continue
            await asyncio.sleep(0.001)

    async def _execute(
        self,
        session: AsyncSession,
        user_id: int,
        symbol: str,
        action: str,
        price: float,
        details: str,
        max_position_pct: float,
    ) -> None:
        account = (
            await session.execute(
                select(CryptoPaperAccount).where(CryptoPaperAccount.user_id == user_id)
            )
        ).scalar_one_or_none()
        if not account:
            return

        position = (
            await session.execute(
                select(CryptoPaperPosition).where(
                    CryptoPaperPosition.account_id == account.id,
                    CryptoPaperPosition.symbol == symbol,
                )
            )
        ).scalar_one_or_none()

        px = D(str(price))
        if action == "BUY" and position is None:
            notional = min(
                account.cash_balance,
                account.initial_capital * D(str(max_position_pct)) / D("100"),
            )
            qty = (notional / px).quantize(D("0.00000001"))
            if qty <= 0:
                return
            account.cash_balance -= qty * px
            position = CryptoPaperPosition(
                account_id=account.id,
                user_id=user_id,
                symbol=symbol,
                quantity=qty,
                average_price=px,
                current_price=px,
            )
            session.add(position)
            session.add(
                CryptoPaperTrade(
                    account_id=account.id,
                    user_id=user_id,
                    symbol=symbol,
                    side="BUY",
                    quantity=qty,
                    price=px,
                    realized_pnl=D("0"),
                    reason=f"REALTIME MTF {details}",
                )
            )
            self.trades += 1
        elif action == "SELL" and position is not None and position.quantity > 0:
            qty = position.quantity
            pnl = (px - position.average_price) * qty
            account.cash_balance += qty * px
            position.realized_pnl += pnl
            session.add(
                CryptoPaperTrade(
                    account_id=account.id,
                    user_id=user_id,
                    symbol=symbol,
                    side="SELL",
                    quantity=qty,
                    price=px,
                    realized_pnl=pnl,
                    reason=f"REALTIME MTF {details}",
                )
            )
            position.quantity = D("0")
            self.trades += 1


RUNNER = CryptoRealtimeBotRunner()
