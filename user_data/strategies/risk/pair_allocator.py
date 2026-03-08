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
