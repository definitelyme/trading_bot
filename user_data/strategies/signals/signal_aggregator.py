from dataclasses import dataclass
from typing import List

@dataclass
class Signal:
    direction: str   # "BUY" | "SELL" | "HOLD"
    confidence: float  # 0.0–1.0
    strategy: str

@dataclass
class AggregatedSignal:
    direction: str
    confidence: float
    contributing_strategies: List[str]

class SignalAggregator:
    def __init__(self, min_confidence: float = 0.65):
        self._min_confidence = min_confidence

    def aggregate(self, signals: List[Signal]) -> AggregatedSignal:
        """
        Combines signals from all strategy modules.
        Returns HOLD if no consensus or confidence below threshold.
        """
        if not signals:
            return AggregatedSignal("HOLD", 0.0, [])

        buys = [s for s in signals if s.direction == "BUY"]
        sells = [s for s in signals if s.direction == "SELL"]

        # Conflicting strong signals → HOLD
        if buys and sells:
            return AggregatedSignal("HOLD", 0.0, [s.strategy for s in signals])

        dominant = buys if buys else sells
        direction = "BUY" if buys else "SELL"

        avg_confidence = sum(s.confidence for s in dominant) / len(dominant)

        if avg_confidence < self._min_confidence:
            return AggregatedSignal("HOLD", avg_confidence, [s.strategy for s in dominant])

        return AggregatedSignal(
            direction=direction,
            confidence=round(avg_confidence, 4),
            contributing_strategies=[s.strategy for s in dominant],
        )
