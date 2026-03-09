import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from user_data.strategies.AICryptoStrategy import AICryptoStrategy
from user_data.strategies.risk.pair_allocator import PairAllocator
from user_data.strategies.signals.signal_aggregator import SignalAggregator


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
        strategy._get_model_confidence = MagicMock(return_value=0.7)
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

    def test_returns_zero_when_risk_cap_is_zero(self):
        """When risk manager returns 0 (low confidence), custom_stake_amount
        should return 0 instead of bypassing the cap."""
        strategy = _make_strategy_with_mocks()
        strategy._pair_allocator._weights = {
            "BTC/USDT": 0.40, "ETH/USDT": 0.35, "SOL/USDT": 0.25
        }
        strategy._pair_allocator._last_refresh = datetime.utcnow()
        # Low confidence → risk_cap = 0
        strategy._get_model_confidence = MagicMock(return_value=0.3)
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
        assert stake == 0


class TestModelConfidence:
    """Tests for the percentile-rank confidence normalization."""

    def test_returns_zero_for_empty_dataframe(self):
        strategy = _make_strategy_with_mocks()
        strategy.dp.get_pair_dataframe.return_value = pd.DataFrame()
        assert strategy._get_model_confidence("BTC/USDT") == 0.0

    def test_returns_zero_for_missing_column(self):
        strategy = _make_strategy_with_mocks()
        strategy.dp.get_pair_dataframe.return_value = pd.DataFrame({"close": [1, 2]})
        assert strategy._get_model_confidence("BTC/USDT") == 0.0

    def test_returns_zero_for_insufficient_predictions(self):
        strategy = _make_strategy_with_mocks()
        strategy.dp.get_pair_dataframe.return_value = pd.DataFrame({
            "&-price_change": [0.01] * 5  # only 5, need at least 10
        })
        assert strategy._get_model_confidence("BTC/USDT") == 0.0

    def test_percentile_rank_high_prediction(self):
        """A prediction at the extreme should have high confidence."""
        strategy = _make_strategy_with_mocks()
        preds = [0.001] * 99 + [0.05]  # last one is an outlier
        strategy.dp.get_pair_dataframe.return_value = pd.DataFrame({
            "&-price_change": preds
        })
        confidence = strategy._get_model_confidence("BTC/USDT")
        assert confidence >= 0.9

    def test_percentile_rank_median_prediction(self):
        """A prediction near the median should have ~0.5 confidence."""
        strategy = _make_strategy_with_mocks()
        # Place a mid-range value at the end (iloc[-1])
        base = list(np.linspace(0.001, 0.05, 99))
        median_val = np.median(np.abs(base))
        preds = base + [median_val]
        strategy.dp.get_pair_dataframe.return_value = pd.DataFrame({
            "&-price_change": preds
        })
        confidence = strategy._get_model_confidence("BTC/USDT")
        assert 0.4 <= confidence <= 0.6

    def test_negative_prediction_uses_absolute_value(self):
        """Negative predictions should use abs() for ranking."""
        strategy = _make_strategy_with_mocks()
        preds = [0.001] * 99 + [-0.05]  # large negative prediction
        strategy.dp.get_pair_dataframe.return_value = pd.DataFrame({
            "&-price_change": preds
        })
        confidence = strategy._get_model_confidence("BTC/USDT")
        assert confidence >= 0.9

    def test_confidence_returns_value_between_0_and_1(self):
        """Confidence should always be in [0, 1] range."""
        strategy = _make_strategy_with_mocks()
        preds = list(np.random.uniform(-0.05, 0.05, 200))
        strategy.dp.get_pair_dataframe.return_value = pd.DataFrame({
            "&-price_change": preds
        })
        confidence = strategy._get_model_confidence("BTC/USDT")
        assert 0.0 <= confidence <= 1.0


class TestIntegrationConfidenceToStake:
    """Integration tests: full pipeline from prediction → confidence → risk → stake."""

    def test_high_prediction_produces_nonzero_stake(self):
        """Strong prediction → high confidence → risk cap > 0 → positive stake."""
        strategy = _make_strategy_with_mocks()
        strategy._pair_allocator._weights = {
            "BTC/USDT": 0.40, "ETH/USDT": 0.35, "SOL/USDT": 0.25
        }
        strategy._pair_allocator._last_refresh = datetime.utcnow()

        # Simulate predictions where last one is extreme (high confidence)
        preds = [0.001] * 99 + [0.04]
        strategy.dp.get_pair_dataframe.return_value = pd.DataFrame({
            "&-price_change": preds,
            "close": [50000.0] * 100,
            "%-atr-period_10_1h": [500.0] * 100,  # 1% ATR
        })

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
        assert stake > 0
        assert stake <= 500.0

    def test_weak_prediction_produces_zero_stake(self):
        """Weak prediction → low confidence → risk cap = 0 → stake = 0."""
        strategy = _make_strategy_with_mocks()
        strategy._pair_allocator._weights = {
            "BTC/USDT": 0.40, "ETH/USDT": 0.35, "SOL/USDT": 0.25
        }
        strategy._pair_allocator._last_refresh = datetime.utcnow()

        # All predictions identical → current is at 0th percentile
        preds = [0.01] * 100
        strategy.dp.get_pair_dataframe.return_value = pd.DataFrame({
            "&-price_change": preds,
            "close": [50000.0] * 100,
            "%-atr-period_10_1h": [500.0] * 100,
        })

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
        assert stake == 0

    def test_risk_cap_bounds_weight_based_allocation(self):
        """Risk cap from quarter-Kelly should be tighter than weight-based."""
        strategy = _make_strategy_with_mocks()
        strategy._pair_allocator._weights = {
            "BTC/USDT": 0.90, "ETH/USDT": 0.05, "SOL/USDT": 0.05
        }
        strategy._pair_allocator._last_refresh = datetime.utcnow()

        # Moderate prediction → moderate confidence → smaller risk cap
        preds = list(np.linspace(0.001, 0.05, 99)) + [0.03]
        strategy.dp.get_pair_dataframe.return_value = pd.DataFrame({
            "&-price_change": preds,
            "close": [50000.0] * 100,
            "%-atr-period_10_1h": [500.0] * 100,
        })

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
        # Weight-based: 900 * 0.90 = 810, but risk cap should be lower
        assert stake > 0
        weight_based = 900 * 0.90
        assert stake < weight_based

    def test_circuit_breaker_blocks_entire_pipeline(self):
        """Circuit breaker active → risk_cap = 0 → stake = 0."""
        strategy = _make_strategy_with_mocks()
        strategy._pair_allocator._weights = {
            "BTC/USDT": 0.40, "ETH/USDT": 0.35, "SOL/USDT": 0.25
        }
        strategy._pair_allocator._last_refresh = datetime.utcnow()
        # Trigger circuit breaker
        strategy._risk_manager.record_drawdown(
            amount=150.0, portfolio_value=1000.0, window="24h"
        )

        preds = [0.001] * 99 + [0.04]
        strategy.dp.get_pair_dataframe.return_value = pd.DataFrame({
            "&-price_change": preds,
            "close": [50000.0] * 100,
            "%-atr-period_10_1h": [500.0] * 100,
        })

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
        assert stake == 0  # circuit breaker blocks everything


class TestEntrySignals:
    """Tests for populate_entry_trend thresholds and filters."""

    def _make_entry_df(self, price_change, do_predict=1, volume=1000):
        """Build a minimal dataframe for entry signal testing."""
        if not isinstance(price_change, list):
            price_change = [price_change]
        n = len(price_change)
        if not isinstance(do_predict, list):
            do_predict = [do_predict] * n
        if not isinstance(volume, list):
            volume = [volume] * n
        return pd.DataFrame({
            "&-price_change": price_change,
            "do_predict": do_predict,
            "volume": volume,
        })

    def test_entry_requires_1_5_pct_threshold(self):
        """Predictions below 1.5% should NOT trigger entry."""
        strategy = _make_strategy_with_mocks()
        df = self._make_entry_df(
            price_change=[0.005, 0.010, 0.014],
            do_predict=[1, 1, 1],
        )
        result = strategy.populate_entry_trend(df, {"pair": "BTC/USDT"})
        assert result["enter_long"].sum() == 0

    def test_entry_triggers_above_1_5_pct(self):
        """Predictions above 1.5% with do_predict=1 should trigger entry."""
        strategy = _make_strategy_with_mocks()
        df = self._make_entry_df(
            price_change=[0.005, 0.020, 0.030],
            do_predict=[1, 1, 1],
        )
        result = strategy.populate_entry_trend(df, {"pair": "BTC/USDT"})
        assert result["enter_long"].sum() == 2

    def test_entry_blocked_by_di_filter(self):
        """do_predict=0 (DI outlier) should block entry even with strong prediction."""
        strategy = _make_strategy_with_mocks()
        df = self._make_entry_df(
            price_change=[0.050],
            do_predict=[0],
        )
        result = strategy.populate_entry_trend(df, {"pair": "BTC/USDT"})
        assert result["enter_long"].sum() == 0

    def test_entry_blocked_by_circuit_breaker(self):
        """Circuit breaker should block all entries."""
        strategy = _make_strategy_with_mocks()
        strategy._risk_manager._circuit_breaker_active = True
        df = self._make_entry_df(
            price_change=[0.050],
            do_predict=[1],
        )
        result = strategy.populate_entry_trend(df, {"pair": "BTC/USDT"})
        assert result["enter_long"].sum() == 0

    def test_entry_blocked_by_zero_volume(self):
        """Zero volume candles should not trigger entry."""
        strategy = _make_strategy_with_mocks()
        df = self._make_entry_df(
            price_change=[0.030],
            do_predict=[1],
            volume=[0],
        )
        result = strategy.populate_entry_trend(df, {"pair": "BTC/USDT"})
        assert result["enter_long"].sum() == 0


class TestConfirmTradeEntry:
    """Tests for confirm_trade_entry with signal aggregation."""

    def _make_strategy_with_real_aggregator(self):
        """Strategy with real aggregator (not mocked) for signal tests."""
        strategy = _make_strategy_with_mocks()
        # Replace mocked aggregator with real one
        strategy._aggregator = SignalAggregator(min_confidence=0.55)
        return strategy

    def test_high_confidence_ml_approves_entry(self):
        """ML-only: high confidence should approve entry."""
        strategy = self._make_strategy_with_real_aggregator()
        strategy._bot_start_time = datetime.utcnow() - timedelta(hours=5)
        preds = [0.001] * 99 + [0.04]
        strategy.dp.get_pair_dataframe.return_value = pd.DataFrame({
            "&-price_change": preds,
        })
        with patch("user_data.strategies.AICryptoStrategy.Trade") as MockTrade:
            MockTrade.get_trades_proxy.return_value = []
            result = strategy.confirm_trade_entry(
                pair="BTC/USDT", order_type="limit", amount=0.01,
                rate=50000.0, time_in_force="GTC",
                current_time=datetime.utcnow(), entry_tag=None, side="long",
            )
        assert result is True

    def test_low_confidence_ml_blocks_entry(self):
        """ML-only: low confidence (below aggregator threshold) should block."""
        strategy = self._make_strategy_with_real_aggregator()
        strategy._bot_start_time = datetime.utcnow() - timedelta(hours=5)
        preds = [0.01] * 100
        strategy.dp.get_pair_dataframe.return_value = pd.DataFrame({
            "&-price_change": preds,
        })
        with patch("user_data.strategies.AICryptoStrategy.Trade") as MockTrade:
            MockTrade.get_trades_proxy.return_value = []
            result = strategy.confirm_trade_entry(
                pair="BTC/USDT", order_type="limit", amount=0.01,
                rate=50000.0, time_in_force="GTC",
                current_time=datetime.utcnow(), entry_tag=None, side="long",
            )
        assert result is False

    def test_dormant_signals_dont_interfere(self):
        """When external signals are disabled, only ML signal is used."""
        strategy = self._make_strategy_with_real_aggregator()
        strategy._bot_start_time = datetime.utcnow() - timedelta(hours=5)
        assert strategy._fear_greed.get_signal() is None
        assert strategy._news_sentiment.get_signal("BTC/USDT") is None

        preds = [0.001] * 99 + [0.04]
        strategy.dp.get_pair_dataframe.return_value = pd.DataFrame({
            "&-price_change": preds,
        })
        with patch("user_data.strategies.AICryptoStrategy.Trade") as MockTrade:
            MockTrade.get_trades_proxy.return_value = []
            result = strategy.confirm_trade_entry(
                pair="BTC/USDT", order_type="limit", amount=0.01,
                rate=50000.0, time_in_force="GTC",
                current_time=datetime.utcnow(), entry_tag=None, side="long",
            )
        assert result is True


class TestRateLimiting:
    """Tests for entry rate limiting and startup cooldown."""

    def _make_strategy_with_real_aggregator(self):
        strategy = _make_strategy_with_mocks()
        strategy._aggregator = SignalAggregator(min_confidence=0.55)
        return strategy

    def test_startup_cooldown_limits_entries(self):
        """During startup cooldown, max 3 entries allowed."""
        strategy = self._make_strategy_with_real_aggregator()
        strategy._bot_start_time = None

        preds = [0.001] * 99 + [0.04]
        strategy.dp.get_pair_dataframe.return_value = pd.DataFrame({
            "&-price_change": preds,
        })

        mock_trade = MagicMock()
        mock_trade.open_date = datetime.utcnow()

        with patch("user_data.strategies.AICryptoStrategy.Trade") as MockTrade:
            MockTrade.get_trades_proxy.return_value = [mock_trade] * 3
            result = strategy.confirm_trade_entry(
                pair="SOL/USDT", order_type="limit", amount=0.01,
                rate=80.0, time_in_force="GTC",
                current_time=datetime.utcnow(), entry_tag=None, side="long",
            )
        assert result is False

    def test_rate_limit_blocks_4th_entry_in_hour(self):
        """Max 3 entries per hour."""
        strategy = self._make_strategy_with_real_aggregator()
        strategy._bot_start_time = datetime.utcnow() - timedelta(hours=5)

        preds = [0.001] * 99 + [0.04]
        strategy.dp.get_pair_dataframe.return_value = pd.DataFrame({
            "&-price_change": preds,
        })

        now = datetime.utcnow()
        recent_trades = []
        for i in range(3):
            t = MagicMock()
            t.open_date = now - timedelta(minutes=10 * i)
            recent_trades.append(t)

        with patch("user_data.strategies.AICryptoStrategy.Trade") as MockTrade:
            MockTrade.get_trades_proxy.return_value = recent_trades
            result = strategy.confirm_trade_entry(
                pair="ETH/USDT", order_type="limit", amount=0.01,
                rate=2000.0, time_in_force="GTC",
                current_time=now, entry_tag=None, side="long",
            )
        assert result is False

    def test_allows_entry_when_under_rate_limit(self):
        """Should allow entry when fewer than 3 trades in last hour."""
        strategy = self._make_strategy_with_real_aggregator()
        strategy._bot_start_time = datetime.utcnow() - timedelta(hours=5)

        preds = [0.001] * 99 + [0.04]
        strategy.dp.get_pair_dataframe.return_value = pd.DataFrame({
            "&-price_change": preds,
        })

        now = datetime.utcnow()
        old_trade = MagicMock()
        old_trade.open_date = now - timedelta(minutes=30)

        with patch("user_data.strategies.AICryptoStrategy.Trade") as MockTrade:
            MockTrade.get_trades_proxy.return_value = [old_trade]
            result = strategy.confirm_trade_entry(
                pair="BTC/USDT", order_type="limit", amount=0.01,
                rate=50000.0, time_in_force="GTC",
                current_time=now, entry_tag=None, side="long",
            )
        assert result is True

    def test_allows_entry_after_cooldown_expires(self):
        """After startup cooldown, normal rate limiting applies."""
        strategy = self._make_strategy_with_real_aggregator()
        strategy._bot_start_time = datetime.utcnow() - timedelta(hours=3)

        preds = [0.001] * 99 + [0.04]
        strategy.dp.get_pair_dataframe.return_value = pd.DataFrame({
            "&-price_change": preds,
        })

        with patch("user_data.strategies.AICryptoStrategy.Trade") as MockTrade:
            MockTrade.get_trades_proxy.return_value = []
            result = strategy.confirm_trade_entry(
                pair="BTC/USDT", order_type="limit", amount=0.01,
                rate=50000.0, time_in_force="GTC",
                current_time=datetime.utcnow(), entry_tag=None, side="long",
            )
        assert result is True
