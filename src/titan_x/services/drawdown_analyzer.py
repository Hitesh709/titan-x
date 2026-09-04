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
        max_duration_days = 0
        max_recovery_days = None

        drawdown_start = None
        trough_date = None
        trough_equity = peak_equity
        in_drawdown_days = 0

        for point in points:
            equity = float(point["equity"])
            current_date = point["date"]

            if equity >= peak_equity:
                if drawdown_start is not None:
                    duration_days = (current_date - drawdown_start).days
                    if duration_days > max_duration_days:
                        max_duration_days = duration_days

                    if trough_date == max_trough_date and max_trough_date is not None:
                        max_recovery_date = current_date
                        max_recovery_days = (current_date - max_trough_date).days

                peak_equity = equity
                peak_date = current_date
                drawdown_start = None
                trough_date = None
                trough_equity = equity
                continue

            if drawdown_start is None:
                drawdown_start = peak_date
                trough_date = current_date
                trough_equity = equity
            elif equity < trough_equity:
                trough_date = current_date
                trough_equity = equity

            in_drawdown_days += 1
            dd = peak_equity - equity
            dd_pct = (dd / peak_equity * 100) if peak_equity > 0 else 0.0

            if dd > max_dd:
                max_dd = dd
                max_dd_pct = dd_pct
                max_peak_date = peak_date
                max_trough_date = current_date
                max_recovery_date = None
                max_recovery_days = None
                max_duration_days = 0

        if drawdown_start is not None:
            current_duration = (points[-1]["date"] - drawdown_start).days
            duration_days = max(max_duration_days, current_duration)
            recovery_date = None
            recovery_days = None
        else:
            duration_days = max_duration_days
            recovery_date = max_recovery_date
            recovery_days = max_recovery_days

        return {
            "max_drawdown": max_dd,
            "max_drawdown_pct": max_dd_pct,
            "peak_date": max_peak_date if max_dd > 0 else None,
            "trough_date": max_trough_date,
            "recovery_date": recovery_date,
            "duration_days": duration_days,
            "recovery_days": recovery_days,
            "in_drawdown_days": in_drawdown_days,
        }
