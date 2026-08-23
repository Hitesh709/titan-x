import pytest

from titan_x.services.paper_trading_engine import PaperTradingEngine


def test_buy_sell_and_equity() -> None:
    engine = PaperTradingEngine(10000, commission_rate=0.001, slippage_bps=10)
    buy = engine.execute("ABC", "BUY", 10, 100)
    assert buy["execution_price"] == pytest.approx(100.1)
    assert engine.positions["ABC"].quantity == 10
    engine.execute("ABC", "SELL", 10, 110)
    assert not engine.positions
    assert engine.cash > 10000


def test_rejects_insufficient_cash_or_position() -> None:
    engine = PaperTradingEngine(1000)
    with pytest.raises(ValueError, match="insufficient paper cash"):
        engine.execute("ABC", "BUY", 11, 100)
    with pytest.raises(ValueError, match="insufficient paper position"):
        engine.execute("ABC", "SELL", 1, 100)


def test_snapshot_marks_open_position_to_market() -> None:
    engine = PaperTradingEngine(1000)
    engine.execute("ABC", "BUY", 5, 100)
    snapshot = engine.snapshot({"ABC": 110})
    assert snapshot["equity"] == pytest.approx(1050)
    assert snapshot["unrealized_pnl"] == pytest.approx(50)
