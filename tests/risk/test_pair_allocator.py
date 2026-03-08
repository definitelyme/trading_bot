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
