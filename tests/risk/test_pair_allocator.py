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
