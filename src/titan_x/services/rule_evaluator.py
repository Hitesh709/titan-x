import math
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass
class BarData:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Indicators:
    sma_fast: float | None = None
    sma_slow: float | None = None
    rsi: float | None = None
    bb_upper: float | None = None
    bb_lower: float | None = None
    bb_middle: float | None = None
    atr: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    stoch_k: float | None = None
    stoch_d: float | None = None


def _get_field_value(field: str, bar: BarData, ind: Indicators | None = None) -> float | None:
    field_map: dict[str, Any] = {
        "price": bar.close,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
    }
    if ind is not None:
        field_map.update({
            "sma_fast": ind.sma_fast,
            "sma_slow": ind.sma_slow,
            "rsi": ind.rsi,
            "bb_upper": ind.bb_upper,
            "bb_lower": ind.bb_lower,
            "bb_middle": ind.bb_middle,
            "atr": ind.atr,
            "macd": ind.macd,
            "macd_signal": ind.macd_signal,
            "stoch_k": ind.stoch_k,
            "stoch_d": ind.stoch_d,
        })
    return field_map.get(field)


def _compare(value: float, operator: str, threshold: float) -> bool:
    if operator == "gt":
        return value > threshold
    elif operator == "gte":
        return value >= threshold
    elif operator == "lt":
        return value < threshold
    elif operator == "lte":
        return value <= threshold
    elif operator == "eq":
        return abs(value - threshold) < 0.0001
    return False


def _crosses_above(curr_value: float, prev_value: float, threshold: float) -> bool:
    return prev_value <= threshold and curr_value > threshold


def _crosses_below(curr_value: float, prev_value: float, threshold: float) -> bool:
    return prev_value >= threshold and curr_value < threshold


def evaluate_indicator_rule(
    rule: dict[str, Any],
    bar: BarData,
    prev_bar: BarData | None,
    ind: Indicators,
    prev_ind: Indicators | None = None,
) -> bool:
    field = rule.get("field", "")
    operator = rule.get("operator", "gt")
    value = rule.get("value", 0)

    field_value = _get_field_value(field, bar, ind)
    if field_value is None:
        return False

    if operator == "crosses_above":
        if prev_bar is None or prev_ind is None:
            return False
        prev_value = _get_field_value(field, prev_bar, prev_ind)
        if prev_value is None:
            return False
        return _crosses_above(field_value, prev_value, value)

    elif operator == "crosses_below":
        if prev_bar is None or prev_ind is None:
            return False
        prev_value = _get_field_value(field, prev_bar, prev_ind)
        if prev_value is None:
            return False
        return _crosses_below(field_value, prev_value, value)

    elif operator == "between":
        low = rule.get("low", 0)
        high = rule.get("high", 100)
        return low <= field_value <= high

    return _compare(field_value, operator, float(value))


def evaluate_fundamental_rule(rule: dict[str, Any], fundamentals: dict[str, Any] | None) -> bool:
    if fundamentals is None:
        return False
    field = rule.get("field", "")
    operator = rule.get("operator", "gt")
    value = rule.get("value", 0)

    field_value = fundamentals.get(field)
    if field_value is None:
        return False

    if operator == "between":
        low = rule.get("low", 0)
        high = rule.get("high", 100)
        return low <= float(field_value) <= high

    return _compare(float(field_value), operator, float(value))


def evaluate_risk_rule(rule: dict[str, Any], portfolio_state: dict[str, Any] | None) -> bool:
    if portfolio_state is None:
        return True
    field = rule.get("field", "")
    operator = rule.get("operator", "lte")
    value = rule.get("value", 0)

    field_value = portfolio_state.get(field)
    if field_value is None:
        return True

    return _compare(float(field_value), operator, float(value))


def calculate_position_size(
    rule: dict[str, Any],
    capital: float,
    bar: BarData,
    ind: Indicators | None = None,
) -> float:
    sizing_type = rule.get("type", "fixed_pct")
    value = rule.get("value", 95)

    if sizing_type == "fixed_pct":
        return capital * (float(value) / 100.0)
    elif sizing_type == "fixed_value":
        return min(float(value), capital)
    elif sizing_type == "risk_based":
        risk_pct = rule.get("risk_per_trade_pct", 1.0) / 100.0
        atr = ind.atr if ind else None
        if atr and atr > 0:
            stop_distance = rule.get("stop_distance_atr", 2.0) * atr
            risk_amount = capital * risk_pct
            position_value = risk_amount / (stop_distance / bar.close) if stop_distance > 0 else capital * 0.95
            return min(position_value, capital)
        return capital * (float(value) / 100.0)
    elif sizing_type == "kelly":
        win_rate = rule.get("kelly_win_rate", 0.5)
        avg_win = rule.get("kelly_avg_win", 1.0)
        avg_loss = rule.get("kelly_avg_loss", 1.0)
        if avg_loss == 0:
            return capital * 0.95
        b = avg_win / avg_loss
        p = win_rate
        q = 1.0 - p
        kelly_pct = max(0, (b * p - q) / b)
        kelly_pct = min(kelly_pct, rule.get("kelly_max_pct", 0.25))
        return capital * kelly_pct

    return capital * 0.95


def get_exit_params(exit_rules: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "stop_loss_pct": None,
        "take_profit_pct": None,
        "trailing_stop_pct": None,
        "max_holding_days": None,
    }
    for rule in exit_rules:
        rule_type = rule.get("type", "indicator")
        field = rule.get("field", "")
        operator = rule.get("operator", "")
        value = rule.get("value", 0)

        if rule_type == "stop_loss":
            result["stop_loss_pct"] = abs(float(value))
        elif rule_type == "take_profit":
            result["take_profit_pct"] = abs(float(value))
        elif rule_type == "trailing_stop":
            result["trailing_stop_pct"] = abs(float(value))
        elif rule_type == "max_holding_days":
            result["max_holding_days"] = int(value)

    return result


def evaluate_exit_rule(
    rule: dict[str, Any],
    bar: BarData,
    prev_bar: BarData | None,
    ind: Indicators,
    prev_ind: Indicators | None = None,
) -> bool:
    rule_type = rule.get("type", "indicator")
    if rule_type in ("stop_loss", "take_profit", "trailing_stop", "max_holding_days"):
        return False

    return evaluate_indicator_rule(rule, bar, prev_bar, ind, prev_ind)


def evaluate_entry_rules(
    entry_criteria: list[dict[str, Any]],
    bar: BarData,
    prev_bar: BarData | None,
    ind: Indicators,
    prev_ind: Indicators | None = None,
    fundamentals: dict[str, Any] | None = None,
    portfolio_state: dict[str, Any] | None = None,
) -> bool:
    if not entry_criteria:
        return False

    for group in entry_criteria:
        logic = group.get("logic", "and")
        rules = group.get("rules", [])
        results: list[bool] = []
        for rule in rules:
            rule_type = rule.get("type", "indicator")
            if rule_type == "indicator":
                results.append(evaluate_indicator_rule(rule, bar, prev_bar, ind, prev_ind))
            elif rule_type == "fundamental":
                results.append(evaluate_fundamental_rule(rule, fundamentals))
            elif rule_type == "risk":
                results.append(evaluate_risk_rule(rule, portfolio_state))

        if not results:
            continue

        if logic == "and":
            if all(results):
                return True
        else:
            if any(results):
                return True

    return False
