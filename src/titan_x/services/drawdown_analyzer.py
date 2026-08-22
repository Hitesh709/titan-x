from collections.abc import Sequence
from datetime import date
from typing import Any


class DrawdownAnalyzer:
    """Detailed drawdown analysis for a mark-to-market equity curve."""

    def analyze(self, equity_curve: Sequence[dict[str, Any]]) -> dict[str, Any]:
        if not equity_curve:
            return {
                "max_drawdown": 0.0,
                "max_drawdown_pct": 0.0,
                "peak_date": None,
                "trough_date": None,
                "recovery_date": None,
                "duration_days": 0,
                "recovery_days": None,
                "in_drawdown_days": 0,
            }

        points = sorted(equity_curve, key=lambda p: p["date"])
        peak_equity = float(points[0]["equity"])
        peak_date = points[0]["date"]
        trough_date = None
        recovery_date = None
        max_dd = 0.0
        max_dd_pct = 0.0
        current_start = None
        current_trough = None
        current_trough_equity = peak_equity
        in_drawdown_days = 0
        best_duration = 0
        best_recovery = None

        for point in points:
            equity = float(point["equity"])
            current_date = point["date"]

            if equity >= peak_equity:
                if current_start is not None:
                    recovery_days = (current_date - current_start).days
                    if recovery_days > best_duration:
                        best_duration = recovery_days
                    if recovery_days == (points[-1]["date"] - points[0]["date"]).days and best_recovery is None:
                        best_recovery = current_date
                peak_equity = equity
                peak_date = current_date
                current_start = None
                current_trough = None
                current_trough_equity = equity
                continue

            if current_start is None:
                current_start = peak_date
                current_trough = current_date
                current_trough_equity = equity
            elif equity < current_trough_equity:
                current_trough = current_date
                current_trough_equity = equity

            in_drawdown_days += 1
            dd = peak_equity - equity
            dd_pct = (dd / peak_equity * 100) if peak_equity > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
                max_dd_pct = dd_pct
                trough_date = current_date

        if current_start is not None:
            duration_days = (points[-1]["date"] - current_start).days
            recovery_date = None
        else:
            duration_days = best_duration
            recovery_date = best_recovery

        if trough_date is None and max_dd == 0:
            peak_date = None

        recovery_days = None
        if trough_date is not None and recovery_date is not None and recovery_date >= trough_date:
            recovery_days = (recovery_date - trough_date).days

        return {
            "max_drawdown": max_dd,
            "max_drawdown_pct": max_dd_pct,
            "peak_date": peak_date,
            "trough_date": trough_date,
            "recovery_date": recovery_date,
            "duration_days": duration_days,
            "recovery_days": recovery_days,
            "in_drawdown_days": in_drawdown_days,
        }
