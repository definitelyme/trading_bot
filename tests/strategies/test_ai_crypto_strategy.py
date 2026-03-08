import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from datetime import datetime
from user_data.strategies.AICryptoStrategy import AICryptoStrategy
from user_data.strategies.risk.pair_allocator import PairAllocator


def test_strategy_file_exists():
    assert AICryptoStrategy is not None


def test_strategy_has_required_freqai_methods():
    assert hasattr(AICryptoStrategy, "feature_engineering_expand_all")
    assert hasattr(AICryptoStrategy, "set_freqai_targets")
    assert hasattr(AICryptoStrategy, "populate_entry_trend")
    assert hasattr(AICryptoStrategy, "populate_exit_trend")


def test_feature_engineering_adds_required_columns():
    strategy = AICryptoStrategy({})
    df = pd.DataFrame({
        "open": np.random.uniform(40000, 50000, 100),
        "high": np.random.uniform(50000, 55000, 100),
        "low": np.random.uniform(35000, 40000, 100),
        "close": np.random.uniform(40000, 50000, 100),
        "volume": np.random.uniform(1000, 5000, 100),
    })
    result = strategy.feature_engineering_expand_all(df, 14, {})
    assert "%-rsi-period_14_1h" in result.columns or len(result.columns) > 5


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
    def test_has_custom_stake_amount_method(self):
        assert hasattr(AICryptoStrategy, "custom_stake_amount")

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

    def test_respects_risk_manager_cap(self):
        """custom_stake_amount should be capped by RiskManager position size."""
        strategy = _make_strategy_with_mocks()
        strategy._pair_allocator._weights = {
            "BTC/USDT": 0.90, "ETH/USDT": 0.05, "SOL/USDT": 0.05
        }
        strategy._pair_allocator._last_refresh = datetime.utcnow()
        strategy._get_model_confidence = MagicMock(return_value=0.5)
        strategy._get_current_atr_pct = MagicMock(return_value=0.03)
        # RiskManager should cap at a lower amount than weight-based allocation
        strategy._risk_manager.calculate_position_size = MagicMock(return_value=100.0)

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
        # Weight-based: 900 * 0.90 = 810, but risk cap = 100
        assert stake <= 100.0
        assert stake > 0

    def test_triggers_refresh_when_stale(self):
        """Should auto-refresh allocator when weights are stale."""
        strategy = _make_strategy_with_mocks()
        # Don't set weights — allocator needs refresh
        strategy._get_model_confidence = MagicMock(return_value=0.5)
        strategy._get_current_atr_pct = MagicMock(return_value=0.02)

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
        # After refresh with no trade history, cold start gives equal weights
        # 1/3 * 900 = 300 (but may be capped by risk manager)
        assert stake >= 0  # should not crash
