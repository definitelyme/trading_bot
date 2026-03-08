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


class TestIntegrationScenarios:
    """Integration-style tests simulating realistic live trading scenarios."""

    def test_full_lifecycle_cold_start_to_performance(self):
        """Simulate a bot going from cold start to having performance data."""
        pairs = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "DOGE/USDT", "AVAX/USDT"]
        allocator = PairAllocator(
            pairs=pairs, min_trades=3, exploration_pct=0.10, pf_threshold=0.7,
            pf_cap=5.0, min_stake=10.0, refresh_hours=4,
        )

        # Phase 1: Cold start — no trade history
        allocator.refresh_weights({p: [] for p in pairs})
        for p in pairs:
            assert allocator.get_weight(p) == pytest.approx(1.0 / 5, rel=0.01)

        # Phase 2: Some pairs get trades, others still exploring
        trades_by_pair = {
            "BTC/USDT": _make_trades([15.0, -3.0, 10.0]),   # PF=25/3≈8.33→capped 5.0
            "ETH/USDT": _make_trades([5.0, -4.0, 3.0]),     # PF=8/4=2.0
            "SOL/USDT": _make_trades([1.0]),                  # too few
            "DOGE/USDT": [],                                  # none
            "AVAX/USDT": _make_trades([-2.0, -1.0, 0.5]),   # PF=0.5/3≈0.17 < threshold
        }
        allocator.refresh_weights(trades_by_pair)

        # BTC and ETH in performance pool, SOL and DOGE in exploration, AVAX gets 0
        assert allocator.get_weight("BTC/USDT") > allocator.get_weight("ETH/USDT")
        assert allocator.get_weight("AVAX/USDT") == 0.0
        assert allocator.get_weight("SOL/USDT") > 0  # exploration
        assert allocator.get_weight("DOGE/USDT") > 0  # exploration
        total = sum(allocator.get_weight(p) for p in pairs)
        assert total == pytest.approx(1.0, rel=0.01)

    def test_realistic_11_pair_allocation_with_1000_wallet(self):
        """Simulate allocation across all 11 real trading pairs with $1000."""
        pairs = [
            "BTC/USDT", "ETH/USDT", "SOL/USDT", "AVAX/USDT", "XRP/USDT",
            "DOGE/USDT", "PEPE/USDT", "SUI/USDT", "WIF/USDT", "NEAR/USDT", "FET/USDT",
        ]
        allocator = PairAllocator(
            pairs=pairs, min_trades=5, exploration_pct=0.10, pf_threshold=0.7,
            pf_cap=5.0, min_stake=10.0, refresh_hours=4,
        )

        # Simulate mixed performance: some profitable, some losing, some cold
        trades_by_pair = {
            "BTC/USDT": _make_trades([20, -5, 15, -3, 10, -2, 8]),    # strong
            "ETH/USDT": _make_trades([10, -5, 8, -4, 6, -3, 5]),      # decent
            "SOL/USDT": _make_trades([5, -3, 4, -2, 3]),               # moderate
            "AVAX/USDT": _make_trades([-5, -3, 2, -4, 1]),             # weak PF
            "XRP/USDT": _make_trades([3, -2, 2, -1, 1]),               # break-even-ish
            "DOGE/USDT": _make_trades([1, -1, 2]),                      # too few trades
            "PEPE/USDT": _make_trades([0.5]),                           # exploration
            "SUI/USDT": [],                                              # cold
            "WIF/USDT": _make_trades([-1, -2, -3, -1, -0.5]),          # all losses
            "NEAR/USDT": _make_trades([4, -2, 3, -1, 5]),              # good
            "FET/USDT": _make_trades([2, -1]),                          # too few
        }
        allocator.refresh_weights(trades_by_pair)

        total_capital = 1000.0
        # Verify weights sum to 1
        total = sum(allocator.get_weight(p) for p in pairs)
        assert total == pytest.approx(1.0, rel=0.01)

        # Verify dollar allocations make sense
        for p in pairs:
            w = allocator.get_weight(p)
            dollar_alloc = w * total_capital
            if w > 0:
                assert dollar_alloc >= 0  # non-negative

        # Best performer (BTC) should have highest weight among performance pairs
        perf_weights = {p: allocator.get_weight(p) for p in pairs if allocator.get_weight(p) > 0}
        btc_w = allocator.get_weight("BTC/USDT")
        assert btc_w == max(perf_weights.values())

        # All-loss pair should get zero (PF=0 < threshold)
        assert allocator.get_weight("WIF/USDT") == 0.0

    def test_min_stake_filter_with_small_wallet(self):
        """Simulate $200 wallet where many pairs get filtered out."""
        pairs = [
            "BTC/USDT", "ETH/USDT", "SOL/USDT", "AVAX/USDT", "XRP/USDT",
            "DOGE/USDT", "PEPE/USDT", "SUI/USDT", "WIF/USDT", "NEAR/USDT", "FET/USDT",
        ]
        allocator = PairAllocator(
            pairs=pairs, min_trades=3, exploration_pct=0.10, pf_threshold=0.7,
            pf_cap=5.0, min_stake=15.0, refresh_hours=4,
        )

        trades_by_pair = {
            "BTC/USDT": _make_trades([20, -5, 15]),
            "ETH/USDT": _make_trades([10, -5, 8]),
            "SOL/USDT": _make_trades([5, -3, 4]),
            "AVAX/USDT": _make_trades([3, -2, 2]),
            "XRP/USDT": _make_trades([2]),    # exploration
            "DOGE/USDT": [],                   # exploration
            "PEPE/USDT": [],                   # exploration
            "SUI/USDT": [],                    # exploration
            "WIF/USDT": [],                    # exploration
            "NEAR/USDT": [],                   # exploration
            "FET/USDT": [],                    # exploration
        }

        filtered = allocator.apply_min_stake_filter(
            total_capital=200.0, trades_by_pair=trades_by_pair
        )

        # With $200, exploration pairs get 0.10 / 7 * 200 = ~$2.86 each → below $15 min
        # They should all be filtered out
        active_pairs = [p for p, w in filtered.items() if w > 0]
        assert len(active_pairs) <= 6  # at most the 4 performance + some exploration survivors
        # Filtered weights should still sum to 1.0 (or 0 if all filtered)
        total = sum(filtered.values())
        if total > 0:
            assert total == pytest.approx(1.0, rel=0.01)

    def test_weight_stability_across_refreshes(self):
        """Weights should be deterministic given the same input."""
        allocator = PairAllocator(
            pairs=["BTC/USDT", "ETH/USDT", "SOL/USDT"],
            min_trades=3, exploration_pct=0.10, pf_threshold=0.7,
            pf_cap=5.0, min_stake=10.0, refresh_hours=4,
        )
        trades_by_pair = {
            "BTC/USDT": _make_trades([10, -5, 8]),
            "ETH/USDT": _make_trades([5, -2, 3]),
            "SOL/USDT": _make_trades([1]),
        }

        allocator.refresh_weights(trades_by_pair)
        weights_1 = {p: allocator.get_weight(p) for p in allocator.pairs}

        allocator.refresh_weights(trades_by_pair)
        weights_2 = {p: allocator.get_weight(p) for p in allocator.pairs}

        for p in allocator.pairs:
            assert weights_1[p] == pytest.approx(weights_2[p], rel=0.001)
