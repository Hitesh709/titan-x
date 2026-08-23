from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class SignalConfidence:
    action: str
    confidence: float
    label: str
    factors: dict[str, float]
    risk_reward: float | None
    rationale: list[str]


class SignalConfidenceEngine:
    """Explainable 0-100 confidence scoring for trading signals."""

    WEIGHTS = {
        "technical": 20.0,
        "trend": 20.0,
        "momentum": 15.0,
        "volatility": 10.0,
        "regime": 15.0,
        "risk_reward": 20.0,
    }

    def score(self, inputs: Mapping[str, Any]) -> dict[str, Any]:
        action = str(inputs.get("action", "HOLD")).upper()
        if action not in {"BUY", "SELL", "HOLD"}:
            raise ValueError("action must be BUY, SELL, or HOLD")

        factors = {name: self._bounded(inputs.get(name, 0)) for name in self.WEIGHTS}
        weighted = sum(factors[name] * weight / 100.0 for name, weight in self.WEIGHTS.items())
        rr = inputs.get("risk_reward")
        risk_reward = None if rr is None else float(rr)

        # HOLD is deliberately conservative: confidence reflects signal quality,
        # while BUY/SELL requires positive directional evidence from the caller.
        confidence = round(max(0.0, min(100.0, weighted)), 2)
        label = "STRONG" if confidence >= 75 else "MODERATE" if confidence >= 55 else "WEAK"
        rationale = [
            f"{name.replace('_', ' ').title()}: {value:.1f}/100"
            for name, value in factors.items()
            if value > 0
        ]
        if risk_reward is not None:
            rationale.append(f"Risk/reward: {risk_reward:.2f}")

        return asdict(SignalConfidence(action, confidence, label, factors, risk_reward, rationale))

    @staticmethod
    def _bounded(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError("confidence factors must be numeric")
        return max(0.0, min(100.0, number))
