from collections.abc import Sequence
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
        max_dd = 0.0
        max_dd_pct = 0.0
        max_peak_date = None
        max_trough_date = None
        max_recovery_date = None
        current_start = None
        in_drawdown_days = 0

        for point in points:
            equity = float(point["equity"])
            current_date = point["date"]

            if equity >= peak_equity:
                if current_start is not None:
                    current_start = None
                peak_equity = equity
                peak_date = current_date
                continue

            if current_start is None:
                current_start = peak_date

            in_drawdown_days += 1
            dd = peak_equity - equity
            dd_pct = (dd / peak_equity * 100) if peak_equity > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
                max_dd_pct = dd_pct
                max_peak_date = peak_date
                max_trough_date = current_date
                max_recovery_date = None

        if max_peak_date is not None and max_trough_date is not None:
            for point in points:
                current_date = point["date"]
                if current_date <= max_trough_date:
                    continue
                if float(point["equity"]) >= next(
                    float(p["equity"])
                    for p in points
                    if p["date"] == max_peak_date
                ):
                    max_recovery_date = current_date
                    break

        if current_start is not None:
            duration_days = (points[-1]["date"] - current_start).days
        elif max_peak_date is not None and max_recovery_date is not None:
            duration_days = (max_recovery_date - max_peak_date).days
        else:
            duration_days = 0

        recovery_days = None
        if max_trough_date is not None and max_recovery_date is not None:
            recovery_days = (max_recovery_date - max_trough_date).days

        return {
            "max_drawdown": max_dd,
            "max_drawdown_pct": max_dd_pct,
            "peak_date": max_peak_date if max_dd > 0 else None,
            "trough_date": max_trough_date,
            "recovery_date": max_recovery_date,
            "duration_days": duration_days,
            "recovery_days": recovery_days,
            "in_drawdown_days": in_drawdown_days,
        }
