from datetime import date

from titan_x.models.backtest import BacktestTrade


def test_trade_model_contains_trade_analysis_fields() -> None:
    columns = {column.name for column in BacktestTrade.__table__.columns}
    assert {
        "trade_number",
        "symbol",
        "side",
        "status",
        "entry_date",
        "entry_price",
        "exit_date",
        "exit_price",
        "quantity",
        "commission",
        "slippage",
        "pnl",
        "pnl_pct",
        "holding_days",
    }.issubset(columns)


def test_closed_trade_pnl_percentage_is_well_defined() -> None:
    entry_price = 100.0
    exit_price = 110.0
    quantity = 10.0
    pnl = (exit_price - entry_price) * quantity
    pnl_pct = (pnl / (entry_price * quantity)) * 100
    holding_days = (date(2026, 8, 10) - date(2026, 8, 1)).days

    assert pnl == 100.0
    assert pnl_pct == 10.0
    assert holding_days == 9
