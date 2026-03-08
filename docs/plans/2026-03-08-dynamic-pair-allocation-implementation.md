# Dynamic Pair Allocation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable performance-weighted capital allocation across all 11 trading pairs using profit factor, exploration budget, and RiskManager integration.

**Architecture:** New `PairAllocator` module computes per-pair weights from trade history. Strategy's `custom_stake_amount()` hook applies weights, capped by existing `RiskManager` (Half-Kelly + ATR). Allocator is a pure computation module — no Freqtrade dependency — strategy handles data fetching and adaptation.

**Tech Stack:** Python 3.11+, Freqtrade IStrategy, pytest. Tests run via `.venv/bin/python -m pytest`.

**Design doc:** `docs/plans/2026-03-08-dynamic-pair-allocation-design.md`

---

### Task 1: PairAllocator — TradeResult and profit factor calculation

**Files:**
- Create: `user_data/strategies/risk/pair_allocator.py`
- Create: `tests/risk/test_pair_allocator.py`

**Step 1: Write the failing tests for profit factor**

```python
# tests/risk/test_pair_allocator.py
import pytest
from datetime import datetime, timedelta
from user_data.strategies.risk.pair_allocator import PairAllocator, TradeResult


@pytest.fixture
def allocator():
    return PairAllocator(
        pairs=["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        window_days=30,
        min_trades=5,
        exploration_pct=0.10,
        pf_threshold=0.7,
        pf_cap=5.0,
        min_stake=10.0,
        refresh_hours=4,
    )


def _make_trades(profits: list[float]) -> list[TradeResult]:
    """Helper: create TradeResult list from profit amounts."""
    now = datetime.utcnow()
    return [
        TradeResult(profit_abs=p, close_date=now - timedelta(hours=i))
        for i, p in enumerate(profits)
    ]


class TestProfitFactor:
    def test_all_wins(self, allocator):
        trades = _make_trades([10.0, 5.0, 8.0, 3.0, 12.0])
        pf = allocator._compute_profit_factor(trades)
        assert pf == 5.0  # capped at pf_cap (all wins, no losses → inf → capped)

    def test_all_losses(self, allocator):
        trades = _make_trades([-10.0, -5.0, -8.0, -3.0, -12.0])
        pf = allocator._compute_profit_factor(trades)
        assert pf == 0.0

    def test_mixed_trades(self, allocator):
        # wins: 10 + 8 = 18, losses: abs(-5) + abs(-3) = 8
        trades = _make_trades([10.0, -5.0, 8.0, -3.0, 2.0])
        pf = allocator._compute_profit_factor(trades)
        assert pf == pytest.approx(20.0 / 8.0)  # 2.5

    def test_empty_trades(self, allocator):
        pf = allocator._compute_profit_factor([])
        assert pf == 0.0

    def test_single_win(self, allocator):
        trades = _make_trades([10.0])
        pf = allocator._compute_profit_factor(trades)
        assert pf == 5.0  # capped

    def test_pf_capped_at_max(self, allocator):
        # wins far exceed losses → should cap at 5.0
        trades = _make_trades([100.0, -0.01, 50.0, 80.0, 30.0])
        pf = allocator._compute_profit_factor(trades)
        assert pf == 5.0

    def test_breakeven_trades(self, allocator):
        trades = _make_trades([10.0, -10.0, 5.0, -5.0, 1.0])
        pf = allocator._compute_profit_factor(trades)
        # wins: 16, losses: 15 → 1.067
        assert pf == pytest.approx(16.0 / 15.0, rel=0.01)
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/risk/test_pair_allocator.py::TestProfitFactor -v`
Expected: FAIL — `ImportError: cannot import name 'PairAllocator'`

**Step 3: Implement PairAllocator with TradeResult and profit factor**

```python
# user_data/strategies/risk/pair_allocator.py
import logging
from dataclasses import dataclass, field
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
```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/risk/test_pair_allocator.py::TestProfitFactor -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add user_data/strategies/risk/pair_allocator.py tests/risk/test_pair_allocator.py
git commit -m "feat: add PairAllocator with profit factor calculation"
```

---

### Task 2: PairAllocator — weight computation with performance/exploration split

**Files:**
- Modify: `user_data/strategies/risk/pair_allocator.py`
- Modify: `tests/risk/test_pair_allocator.py`

**Step 1: Write the failing tests for weight computation**

Add to `tests/risk/test_pair_allocator.py`:

```python
class TestWeightComputation:
    def test_cold_start_equal_weights(self, allocator):
        """All pairs have < min_trades → all go to exploration pool."""
        trades_by_pair = {
            "BTC/USDT": _make_trades([10.0, 5.0]),  # only 2 trades
            "ETH/USDT": _make_trades([8.0]),          # only 1 trade
            "SOL/USDT": [],                            # no trades
        }
        allocator.refresh_weights(trades_by_pair)
        # All in exploration → equal split: 1.0 / 3 = 0.333 each
        for pair in ["BTC/USDT", "ETH/USDT", "SOL/USDT"]:
            assert allocator.get_weight(pair) == pytest.approx(1.0 / 3, rel=0.01)

    def test_performance_and_exploration_split(self, allocator):
        """One pair has history, two don't → 90/10 split."""
        trades_by_pair = {
            "BTC/USDT": _make_trades([10.0, -5.0, 8.0, -3.0, 2.0]),  # 5 trades, PF=2.5
            "ETH/USDT": _make_trades([1.0]),  # too few
            "SOL/USDT": [],                    # none
        }
        allocator.refresh_weights(trades_by_pair)
        # BTC gets all of performance pool (0.90)
        assert allocator.get_weight("BTC/USDT") == pytest.approx(0.90, rel=0.01)
        # ETH and SOL split exploration pool: 0.10 / 2 = 0.05 each
        assert allocator.get_weight("ETH/USDT") == pytest.approx(0.05, rel=0.01)
        assert allocator.get_weight("SOL/USDT") == pytest.approx(0.05, rel=0.01)

    def test_pf_below_threshold_gets_zero_performance(self, allocator):
        """Pair with PF below threshold gets zero from performance pool."""
        trades_by_pair = {
            "BTC/USDT": _make_trades([10.0, -5.0, 8.0, -3.0, 2.0]),  # PF=2.5
            "ETH/USDT": _make_trades([-10.0, -5.0, -8.0, 1.0, -3.0]),  # PF=1/26≈0.04
            "SOL/USDT": _make_trades([5.0, -4.0, 3.0, -6.0, 1.0]),  # wins=9, losses=10, PF=0.9
        }
        allocator.refresh_weights(trades_by_pair)
        # BTC: PF=2.5 (above threshold) → performance pool
        # ETH: PF≈0.04 (below 0.7) → zero performance allocation
        # SOL: PF=0.9 (above 0.7) → performance pool
        # No exploration pairs (all have >= 5 trades)
        # ETH gets 0 from performance (below threshold), 0 from exploration (not eligible)
        assert allocator.get_weight("ETH/USDT") == 0.0
        # BTC and SOL share performance pool proportionally
        btc_w = allocator.get_weight("BTC/USDT")
        sol_w = allocator.get_weight("SOL/USDT")
        assert btc_w > sol_w  # BTC has higher PF
        assert btc_w + sol_w == pytest.approx(1.0, rel=0.01)

    def test_weights_sum_to_one(self, allocator):
        """All weights (including zeros) should sum to <= 1.0."""
        trades_by_pair = {
            "BTC/USDT": _make_trades([10.0, -5.0, 8.0, -3.0, 2.0]),
            "ETH/USDT": _make_trades([5.0, -2.0, 3.0, -1.0, 4.0]),
            "SOL/USDT": _make_trades([1.0, 2.0]),  # exploration
        }
        allocator.refresh_weights(trades_by_pair)
        total = sum(allocator.get_weight(p) for p in allocator.pairs)
        assert total == pytest.approx(1.0, rel=0.01)

    def test_unknown_pair_returns_zero(self, allocator):
        allocator.refresh_weights({"BTC/USDT": [], "ETH/USDT": [], "SOL/USDT": []})
        assert allocator.get_weight("DOGE/USDT") == 0.0

    def test_multiple_performance_pairs_weighted_by_pf(self, allocator):
        """Pairs with higher PF get proportionally more weight."""
        trades_by_pair = {
            "BTC/USDT": _make_trades([20.0, -5.0, 15.0, -5.0, 10.0]),  # wins=45, losses=10, PF=4.5
            "ETH/USDT": _make_trades([5.0, -5.0, 6.0, -5.0, 4.0]),    # wins=15, losses=10, PF=1.5
            "SOL/USDT": _make_trades([1.0]),  # exploration
        }
        allocator.refresh_weights(trades_by_pair)
        btc_w = allocator.get_weight("BTC/USDT")
        eth_w = allocator.get_weight("ETH/USDT")
        # BTC PF 4.5 vs ETH PF 1.5 → BTC should get 3x the weight of ETH
        assert btc_w / eth_w == pytest.approx(4.5 / 1.5, rel=0.05)
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/risk/test_pair_allocator.py::TestWeightComputation -v`
Expected: FAIL — `AttributeError: 'PairAllocator' object has no attribute 'refresh_weights'`

**Step 3: Implement refresh_weights and get_weight**

Add to `PairAllocator` class in `user_data/strategies/risk/pair_allocator.py`:

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/risk/test_pair_allocator.py::TestWeightComputation -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add user_data/strategies/risk/pair_allocator.py tests/risk/test_pair_allocator.py
git commit -m "feat: add weight computation with performance/exploration split"
```

---

### Task 3: PairAllocator — caching, min-stake filtering, and redistribution

**Files:**
- Modify: `user_data/strategies/risk/pair_allocator.py`
- Modify: `tests/risk/test_pair_allocator.py`

**Step 1: Write the failing tests**

Add to `tests/risk/test_pair_allocator.py`:

```python
from unittest.mock import patch


class TestCaching:
    def test_needs_refresh_when_never_refreshed(self, allocator):
        assert allocator.needs_refresh() is True

    def test_needs_refresh_false_after_refresh(self, allocator):
        allocator.refresh_weights({"BTC/USDT": [], "ETH/USDT": [], "SOL/USDT": []})
        assert allocator.needs_refresh() is False

    def test_needs_refresh_true_after_expiry(self, allocator):
        allocator.refresh_weights({"BTC/USDT": [], "ETH/USDT": [], "SOL/USDT": []})
        # Simulate time passing beyond refresh_hours
        allocator._last_refresh = datetime.utcnow() - timedelta(hours=5)
        assert allocator.needs_refresh() is True


class TestMinStakeRedistribution:
    def test_skip_pairs_below_min_stake(self):
        """Pairs whose allocation < min_stake get zeroed, capital redistributed."""
        allocator = PairAllocator(
            pairs=["BTC/USDT", "ETH/USDT", "SOL/USDT"],
            min_stake=100.0,  # high floor to force skipping
            min_trades=2,
            exploration_pct=0.10,
            pf_threshold=0.7,
            pf_cap=5.0,
        )
        trades_by_pair = {
            "BTC/USDT": _make_trades([10.0, -5.0, 8.0]),  # PF=2.25
            "ETH/USDT": _make_trades([5.0, -2.0, 3.0]),   # PF=4.0
            "SOL/USDT": _make_trades([1.0]),                # exploration
        }
        # With total_capital=500:
        # Before redistribution: SOL exploration gets 0.10/1 * 500 = $50 (below $100 min)
        # SOL should be skipped and its weight redistributed
        filtered = allocator.apply_min_stake_filter(
            total_capital=500.0, trades_by_pair=trades_by_pair
        )
        assert filtered["SOL/USDT"] == 0.0
        # BTC and ETH should absorb SOL's share
        assert filtered["BTC/USDT"] + filtered["ETH/USDT"] == pytest.approx(1.0, rel=0.01)

    def test_no_redistribution_when_all_above_min_stake(self, allocator):
        """All pairs above min_stake → weights unchanged."""
        trades_by_pair = {
            "BTC/USDT": _make_trades([10.0, -5.0, 8.0, -3.0, 2.0]),
            "ETH/USDT": _make_trades([5.0, -2.0, 3.0, -1.0, 4.0]),
            "SOL/USDT": _make_trades([1.0, 2.0]),  # exploration
        }
        allocator.refresh_weights(trades_by_pair)
        filtered = allocator.apply_min_stake_filter(
            total_capital=1000.0, trades_by_pair=trades_by_pair
        )
        # With $1000, even smallest weight (SOL explore ~0.10/1=0.10 → $100) > $10 min
        for pair in allocator.pairs:
            assert filtered[pair] == allocator.get_weight(pair)

    def test_all_pairs_below_min_stake(self):
        """When no pair meets min_stake, all get zero."""
        allocator = PairAllocator(
            pairs=["BTC/USDT", "ETH/USDT"],
            min_stake=600.0,  # impossibly high
            min_trades=2,
            exploration_pct=0.10,
            pf_threshold=0.7,
            pf_cap=5.0,
        )
        trades_by_pair = {
            "BTC/USDT": _make_trades([10.0, -5.0]),
            "ETH/USDT": _make_trades([5.0, -2.0]),
        }
        filtered = allocator.apply_min_stake_filter(
            total_capital=1000.0, trades_by_pair=trades_by_pair
        )
        assert all(w == 0.0 for w in filtered.values())

    def test_redistribution_logs_skipped_pairs(self, allocator, caplog):
        """Skipped pairs should be logged."""
        allocator_high = PairAllocator(
            pairs=["BTC/USDT", "ETH/USDT", "SOL/USDT"],
            min_stake=200.0,
            min_trades=2,
            exploration_pct=0.50,  # large exploration so SOL gets enough, but not huge
            pf_threshold=0.7,
            pf_cap=5.0,
        )
        trades_by_pair = {
            "BTC/USDT": _make_trades([10.0, -5.0, 8.0]),
            "ETH/USDT": _make_trades([5.0, -2.0, 3.0]),
            "SOL/USDT": _make_trades([1.0]),  # exploration, gets 0.50/1 * 500 = $250
        }
        import logging
        with caplog.at_level(logging.INFO):
            allocator_high.apply_min_stake_filter(
                total_capital=500.0, trades_by_pair=trades_by_pair
            )
        # Check that at least one pair was logged as skipped (BTC or ETH may be below $200)
        # The exact pair depends on weights — just verify logging occurs for skipped pairs
        skip_logs = [r for r in caplog.records if "Skipping" in r.message]
        # With $500 and 50% exploration: perf pool = $250 split between BTC/ETH
        # BTC and ETH each get ~$125 which is below $200 min → both skipped
        assert len(skip_logs) >= 1
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/risk/test_pair_allocator.py::TestCaching tests/risk/test_pair_allocator.py::TestMinStakeRedistribution -v`
Expected: FAIL — `AttributeError: 'PairAllocator' object has no attribute 'needs_refresh'`

**Step 3: Implement caching and min-stake filtering**

Add to `PairAllocator` class:

```python
    def needs_refresh(self) -> bool:
        if self._last_refresh is None:
            return True
        elapsed = datetime.utcnow() - self._last_refresh
        return elapsed >= timedelta(hours=self.refresh_hours)

    def apply_min_stake_filter(
        self, total_capital: float, trades_by_pair: dict[str, list[TradeResult]]
    ) -> dict[str, float]:
        """Filter out pairs below min_stake and redistribute their weight."""
        if not self._weights:
            self.refresh_weights(trades_by_pair)

        filtered = dict(self._weights)
        changed = True

        while changed:
            changed = False
            below = [p for p, w in filtered.items() if 0 < w * total_capital < self.min_stake]
            if not below:
                break
            for pair in below:
                logger.info(
                    "Skipping %s: weighted allocation $%.2f < min_stake $%.2f",
                    pair, filtered[pair] * total_capital, self.min_stake,
                )
                filtered[pair] = 0.0
                changed = True

            # Redistribute to remaining pairs proportionally
            remaining = {p: w for p, w in filtered.items() if w > 0}
            if remaining:
                total_remaining = sum(remaining.values())
                for pair in remaining:
                    filtered[pair] = remaining[pair] / total_remaining
            # Loop again in case redistribution pushed someone else below min

        return filtered
```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/risk/test_pair_allocator.py::TestCaching tests/risk/test_pair_allocator.py::TestMinStakeRedistribution -v`
Expected: All 7 tests PASS

**Step 5: Run full test suite to check for regressions**

Run: `.venv/bin/python -m pytest tests/risk/test_pair_allocator.py -v`
Expected: All tests PASS (profit factor + weights + caching + min-stake)

**Step 6: Commit**

```bash
git add user_data/strategies/risk/pair_allocator.py tests/risk/test_pair_allocator.py
git commit -m "feat: add caching and min-stake redistribution to PairAllocator"
```

---

### Task 4: Strategy integration — custom_stake_amount and helpers

**Files:**
- Modify: `user_data/strategies/AICryptoStrategy.py`
- Modify: `tests/strategies/test_ai_crypto_strategy.py`

**Step 1: Write the failing tests**

Add to `tests/strategies/test_ai_crypto_strategy.py`:

```python
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime
from user_data.strategies.risk.pair_allocator import PairAllocator


def _make_strategy_with_mocks():
    """Create strategy with mocked Freqtrade internals."""
    with patch("user_data.strategies.AICryptoStrategy.SignalAggregator"):
        strategy = AICryptoStrategy({"stake_currency": "USDT", "exchange": {
            "pair_whitelist": ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
        }})

    # Mock wallets
    strategy.wallets = MagicMock()
    strategy.wallets.get_free.return_value = 900.0  # $900 free
    strategy.wallets.get_available_stake_amount.return_value = 900.0

    # Mock dataprovider
    strategy.dp = MagicMock()

    return strategy


class TestCustomStakeAmount:
    def test_returns_weighted_allocation(self):
        strategy = _make_strategy_with_mocks()
        # Pre-set allocator weights
        strategy._pair_allocator._weights = {
            "BTC/USDT": 0.40, "ETH/USDT": 0.35, "SOL/USDT": 0.25
        }
        strategy._pair_allocator._last_refresh = datetime.utcnow()
        # Mock helpers to not cap (high confidence, low ATR)
        strategy._get_model_confidence = MagicMock(return_value=0.9)
        strategy._get_current_atr_pct = MagicMock(return_value=0.01)

        with patch("user_data.strategies.AICryptoStrategy.Trade") as MockTrade:
            MockTrade.get_trades_proxy.return_value = []
            stake = strategy.custom_stake_amount(
                pair="BTC/USDT",
                current_time=datetime.utcnow(),
                current_rate=50000.0,
                proposed_stake=100.0,
                min_stake=5.0,
                max_stake=500.0,
                leverage=1.0,
                entry_tag=None,
                side="long",
            )
        # total_portfolio = 900 free + 0 deployed = 900
        # tradable = 900 * 0.95 (default ratio)
        # BTC weight 0.40 → 900 * 0.40 = 360
        # Capped by max_stake (500) → 360
        assert stake > 0
        assert stake <= 500.0

    def test_returns_zero_for_zero_weight_pair(self):
        strategy = _make_strategy_with_mocks()
        strategy._pair_allocator._weights = {
            "BTC/USDT": 0.50, "ETH/USDT": 0.50, "SOL/USDT": 0.0
        }
        strategy._pair_allocator._last_refresh = datetime.utcnow()

        with patch("user_data.strategies.AICryptoStrategy.Trade") as MockTrade:
            MockTrade.get_trades_proxy.return_value = []
            stake = strategy.custom_stake_amount(
                pair="SOL/USDT",
                current_time=datetime.utcnow(),
                current_rate=80.0,
                proposed_stake=100.0,
                min_stake=5.0,
                max_stake=500.0,
                leverage=1.0,
                entry_tag=None,
                side="long",
            )
        assert stake == 0

    def test_returns_zero_when_below_exchange_min(self):
        strategy = _make_strategy_with_mocks()
        strategy.wallets.get_free.return_value = 50.0
        strategy._pair_allocator._weights = {
            "BTC/USDT": 0.05, "ETH/USDT": 0.05, "SOL/USDT": 0.90
        }
        strategy._pair_allocator._last_refresh = datetime.utcnow()
        strategy._get_model_confidence = MagicMock(return_value=0.9)
        strategy._get_current_atr_pct = MagicMock(return_value=0.01)

        with patch("user_data.strategies.AICryptoStrategy.Trade") as MockTrade:
            MockTrade.get_trades_proxy.return_value = []
            stake = strategy.custom_stake_amount(
                pair="BTC/USDT",
                current_time=datetime.utcnow(),
                current_rate=50000.0,
                proposed_stake=5.0,
                min_stake=10.0,  # exchange min $10
                max_stake=500.0,
                leverage=1.0,
                entry_tag=None,
                side="long",
            )
        # BTC gets 0.05 * 50 = $2.50, below min_stake of $10
        assert stake == 0

    def test_has_custom_stake_amount_method(self):
        from user_data.strategies.AICryptoStrategy import AICryptoStrategy
        assert hasattr(AICryptoStrategy, "custom_stake_amount")
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/strategies/test_ai_crypto_strategy.py::TestCustomStakeAmount -v`
Expected: FAIL — `AttributeError: 'AICryptoStrategy' object has no attribute '_pair_allocator'`

**Step 3: Implement strategy integration**

Modify `user_data/strategies/AICryptoStrategy.py`:

1. Add imports at the top (after existing imports):
```python
from datetime import datetime, timedelta
from freqtrade.persistence import Trade
from risk.pair_allocator import PairAllocator, TradeResult
```

2. In `__init__`, after the existing `_aggregator` initialization, add:
```python
        pairs = config.get("exchange", {}).get("pair_whitelist", [])
        self._pair_allocator = PairAllocator(
            pairs=pairs,
            window_days=int(os.getenv("PAIR_ALLOC_WINDOW_DAYS", "30")),
            min_trades=int(os.getenv("PAIR_ALLOC_MIN_TRADES", "5")),
            exploration_pct=float(os.getenv("PAIR_ALLOC_EXPLORATION_PCT", "0.10")),
            pf_threshold=float(os.getenv("PAIR_ALLOC_PF_THRESHOLD", "0.7")),
            pf_cap=float(os.getenv("PAIR_ALLOC_PF_CAP", "5.0")),
            min_stake=float(os.getenv("PAIR_ALLOC_MIN_STAKE", "10.0")),
            refresh_hours=int(os.getenv("PAIR_ALLOC_REFRESH_HOURS", "4")),
        )
```

3. Add the new methods after `__init__`:
```python
    def _refresh_allocator(self) -> None:
        cutoff = datetime.utcnow() - timedelta(days=self._pair_allocator.window_days)
        trades_by_pair: dict[str, list[TradeResult]] = {}
        for pair in self._pair_allocator.pairs:
            raw_trades = Trade.get_trades_proxy(pair=pair, is_open=False)
            trades_by_pair[pair] = [
                TradeResult(profit_abs=t.close_profit_abs, close_date=t.close_date)
                for t in raw_trades
                if t.close_date and t.close_date >= cutoff
            ]
        self._pair_allocator.refresh_weights(trades_by_pair)

    def _get_total_portfolio_value(self) -> float:
        free = self.wallets.get_free(self.config.get("stake_currency", "USDT"))
        deployed = sum(
            t.stake_amount for t in Trade.get_trades_proxy(is_open=True)
        )
        return free + deployed

    def _get_model_confidence(self, pair: str) -> float:
        df = self.dp.get_pair_dataframe(pair=pair, timeframe=self.timeframe)
        if df.empty or "&-price_change" not in df.columns:
            return 0.0
        val = df["&-price_change"].iloc[-1]
        return abs(val) if not pd.isna(val) else 0.0

    def _get_current_atr_pct(self, pair: str) -> float:
        df = self.dp.get_pair_dataframe(pair=pair, timeframe=self.timeframe)
        if df.empty:
            return 0.05  # conservative default
        atr_cols = [c for c in df.columns if c.startswith("%-atr-")]
        if not atr_cols:
            return 0.05
        atr_val = df[atr_cols[0]].iloc[-1]
        close_val = df["close"].iloc[-1]
        if pd.isna(atr_val) or pd.isna(close_val) or close_val == 0:
            return 0.05
        return atr_val / close_val

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: float | None,
        max_stake: float,
        leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        if self._pair_allocator.needs_refresh():
            self._refresh_allocator()

        weight = self._pair_allocator.get_weight(pair)
        if weight <= 0:
            return 0

        total_portfolio = self._get_total_portfolio_value()
        base_stake = total_portfolio * weight

        # Cap with RiskManager (Half-Kelly + ATR)
        confidence = self._get_model_confidence(pair)
        atr_pct = self._get_current_atr_pct(pair)
        risk_cap = self._risk_manager.calculate_position_size(
            portfolio_value=total_portfolio,
            confidence=confidence,
            atr_pct=atr_pct,
        )
        if risk_cap > 0:
            base_stake = min(base_stake, risk_cap)

        # Enforce exchange minimum
        effective_min = min_stake or 0
        if base_stake < effective_min:
            logger.info(
                "Skipping %s: stake $%.2f < exchange min $%.2f",
                pair, base_stake, effective_min,
            )
            return 0

        # Cap by available balance and max_stake
        available = self.wallets.get_available_stake_amount()
        final_stake = min(base_stake, available, max_stake)

        logger.info(
            "Allocating %s: weight=%.3f, base=$%.2f, risk_cap=$%.2f, final=$%.2f",
            pair, weight, total_portfolio * weight, risk_cap, final_stake,
        )
        return final_stake
```

4. Add `import pandas as pd` to the imports at the top (for `pd.isna` checks).

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/strategies/test_ai_crypto_strategy.py -v`
Expected: All tests PASS (existing + new)

**Step 5: Commit**

```bash
git add user_data/strategies/AICryptoStrategy.py tests/strategies/test_ai_crypto_strategy.py
git commit -m "feat: wire PairAllocator into strategy via custom_stake_amount"
```

---

### Task 5: Config and environment changes

**Files:**
- Modify: `user_data/config.json`
- Modify: `.env.example`

**Step 1: Update config.json — change max_open_trades from 5 to 11**

In `user_data/config.json`, change:
```json
"max_open_trades": 5,
```
to:
```json
"max_open_trades": 11,
```

**Step 2: Update .env.example — add new env vars**

Append to `.env.example` after the existing Risk Parameters section:

```bash
# Pair Allocation Parameters
PAIR_ALLOC_WINDOW_DAYS=30
PAIR_ALLOC_MIN_TRADES=5
PAIR_ALLOC_EXPLORATION_PCT=0.10
PAIR_ALLOC_PF_THRESHOLD=0.7
PAIR_ALLOC_PF_CAP=5.0
PAIR_ALLOC_MIN_STAKE=10.0
PAIR_ALLOC_REFRESH_HOURS=4
```

**Step 3: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add user_data/config.json .env.example
git commit -m "config: set max_open_trades to 11 and add pair allocation env vars"
```

---

### Task 6: Final verification — full test suite and Docker dry-run check

**Step 1: Run all tests**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: All tests PASS

**Step 2: Verify Docker build still works**

Run: `docker compose build --no-cache`
Expected: Build succeeds

**Step 3: Verify config is valid JSON**

Run: `python3 -c "import json; json.load(open('user_data/config.json'))"`
Expected: No error

**Step 4: Quick dry-run smoke test (optional)**

Run: `docker compose up -d && sleep 30 && docker compose logs --tail=50`
Expected: Bot starts, logs show PairAllocator initialization. Look for:
- `"PairAllocator refreshed:"` log line
- No import errors or crashes
- `custom_stake_amount` being called on trade entries

Run: `docker compose down` to stop after verification.
