import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TradeResult:
    profit_abs: float
    close_date: datetime


class PairAllocator:
    def __init__(
        self,
        pairs: list[str],
        window_days: int = 30,
        min_trades: int = 5,
        exploration_pct: float = 0.10,
        pf_threshold: float = 0.7,
        pf_cap: float = 5.0,
        min_stake: float = 10.0,
        refresh_hours: int = 4,
    ):
        self.pairs = pairs
        self.window_days = window_days
        self.min_trades = min_trades
        self.exploration_pct = exploration_pct
        self.pf_threshold = pf_threshold
        self.pf_cap = pf_cap
        self.min_stake = min_stake
        self.refresh_hours = refresh_hours
        self._weights: dict[str, float] = {}
        self._last_refresh: datetime | None = None

    def _compute_profit_factor(self, trades: list[TradeResult]) -> float:
        if not trades:
            return 0.0
        gross_wins = sum(t.profit_abs for t in trades if t.profit_abs > 0)
        gross_losses = abs(sum(t.profit_abs for t in trades if t.profit_abs < 0))
        if gross_losses == 0:
            return self.pf_cap if gross_wins > 0 else 0.0
        return min(gross_wins / gross_losses, self.pf_cap)

    def refresh_weights(self, trades_by_pair: dict[str, list[TradeResult]]) -> None:
        performance_pairs: dict[str, float] = {}  # pair → profit_factor
        exploration_pairs: list[str] = []

        for pair in self.pairs:
            trades = trades_by_pair.get(pair, [])
            if len(trades) >= self.min_trades:
                pf = self._compute_profit_factor(trades)
                if pf >= self.pf_threshold:
                    performance_pairs[pair] = pf
                # else: pair has enough trades but PF too low → gets nothing
            else:
                exploration_pairs.append(pair)

        self._weights = {}

        # If no performance pairs, everything goes to exploration
        if not performance_pairs:
            perf_budget = 0.0
            explore_budget = 1.0
        else:
            perf_budget = 1.0 - self.exploration_pct if exploration_pairs else 1.0
            explore_budget = self.exploration_pct if exploration_pairs else 0.0

        # Performance pool: weighted by profit factor
        total_pf = sum(performance_pairs.values())
        if total_pf > 0:
            for pair, pf in performance_pairs.items():
                self._weights[pair] = (pf / total_pf) * perf_budget

        # Exploration pool: equal split
        if exploration_pairs:
            per_explore = explore_budget / len(exploration_pairs)
            for pair in exploration_pairs:
                self._weights[pair] = per_explore

        # Pairs not in either pool get 0
        for pair in self.pairs:
            if pair not in self._weights:
                self._weights[pair] = 0.0

        self._last_refresh = datetime.utcnow()
        logger.info(
            "PairAllocator refreshed: %s (%d in exploration)",
            ", ".join(f"{p}={w:.3f}" for p, w in sorted(self._weights.items()) if w > 0),
            len(exploration_pairs),
        )

    def get_weight(self, pair: str) -> float:
        return self._weights.get(pair, 0.0)
