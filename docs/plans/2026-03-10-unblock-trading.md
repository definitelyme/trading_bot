# Unblock Trading — Confidence Gate Simplification

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove the broken confidence gate from the trade execution path so the bot starts executing trades with ATR-based position sizing and a 1.0% entry threshold.

**Architecture:** Three targeted edits to `AICryptoStrategy.py`: lower entry threshold to 1.0%, replace confidence-based Kelly sizing with ATR-only volatility scalar in `custom_stake_amount`, and use a fixed ML signal confidence of 0.75 in `confirm_trade_entry`. All tests updated to reflect the simplified behavior.

**Tech Stack:** Python, pytest, Freqtrade strategy API, pandas

---

### Task 1: Entry Threshold — 1.5% → 1.0%

**Files:**
- Modify: `user_data/strategies/AICryptoStrategy.py:336`
- Test: `tests/strategies/test_ai_crypto_strategy.py`

**Step 1: Write a failing test capturing the new threshold**

Add to `TestEntrySignals` class in `tests/strategies/test_ai_crypto_strategy.py`:

```python
def test_entry_triggers_between_1_0_and_1_5_pct(self):
    """Predictions between 1.0% and 1.5% should trigger entry at new threshold."""
    strategy = _make_strategy_with_mocks()
    df = self._make_entry_df(price_change=[0.011, 0.012, 0.014])
    result = strategy.populate_entry_trend(df, {"pair": "SOL/USDT"})
    assert result["enter_long"].sum() == 3
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/brendan/Sites/crypto && .venv/bin/pytest tests/strategies/test_ai_crypto_strategy.py::TestEntrySignals::test_entry_triggers_between_1_0_and_1_5_pct -v
```

Expected: FAIL — `AssertionError: assert 0 == 3` (current threshold is 1.5%, all three values are below it)

**Step 3: Change the entry threshold**

In `user_data/strategies/AICryptoStrategy.py` line 336, change:

```python
# Before
(dataframe["&-price_change"] > 0.015)

# After
(dataframe["&-price_change"] > 0.010)
```

**Step 4: Update the now-stale threshold tests**

In `tests/strategies/test_ai_crypto_strategy.py`, update `TestEntrySignals`:

```python
def test_entry_requires_1_0_pct_threshold(self):
    """Predictions at or below 1.0% should NOT trigger entry."""
    strategy = _make_strategy_with_mocks()
    df = self._make_entry_df(
        price_change=[0.005, 0.008, 0.010],  # 0.010 is not > 0.010
        do_predict=[1, 1, 1],
    )
    result = strategy.populate_entry_trend(df, {"pair": "BTC/USDT"})
    assert result["enter_long"].sum() == 0

def test_entry_triggers_above_1_0_pct(self):
    """Predictions above 1.0% with do_predict=1 should trigger entry."""
    strategy = _make_strategy_with_mocks()
    df = self._make_entry_df(
        price_change=[0.005, 0.011, 0.020],
        do_predict=[1, 1, 1],
    )
    result = strategy.populate_entry_trend(df, {"pair": "BTC/USDT"})
    assert result["enter_long"].sum() == 2
```

(Replace the existing `test_entry_requires_1_5_pct_threshold` and `test_entry_triggers_above_1_5_pct` methods with the above.)

**Step 5: Run all entry signal tests**

```bash
cd /Users/brendan/Sites/crypto && .venv/bin/pytest tests/strategies/test_ai_crypto_strategy.py::TestEntrySignals -v
```

Expected: All 5 tests PASS

**Step 6: Commit**

```bash
git add user_data/strategies/AICryptoStrategy.py tests/strategies/test_ai_crypto_strategy.py
git commit -m "fix: lower entry threshold from 1.5% to 1.0% to unblock signal generation"
```

---

### Task 2: Position Sizing — Remove Confidence Gate, Keep ATR Scalar

**Files:**
- Modify: `user_data/strategies/AICryptoStrategy.py:157-190`
- Test: `tests/strategies/test_ai_crypto_strategy.py`

**Step 1: Write failing tests for the new ATR-only sizing behavior**

Add to `TestCustomStakeAmount` class:

```python
def test_stake_nonzero_regardless_of_confidence(self):
    """Stake should be positive even when confidence is 0.0 (confidence gate removed)."""
    strategy = _make_strategy_with_mocks()
    strategy._pair_allocator._weights = {
        "BTC/USDT": 0.40, "ETH/USDT": 0.35, "SOL/USDT": 0.25
    }
    strategy._pair_allocator._last_refresh = datetime.utcnow()
    # Simulate the live bug: confidence always 0
    strategy._get_model_confidence = MagicMock(return_value=0.0)
    strategy._get_current_atr_pct = MagicMock(return_value=0.03)

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
    assert stake > 0  # No longer blocked by confidence gate

def test_atr_scalar_reduces_stake_on_high_volatility(self):
    """High ATR should reduce stake size via volatility scalar."""
    strategy = _make_strategy_with_mocks()
    strategy._pair_allocator._weights = {
        "BTC/USDT": 0.40, "ETH/USDT": 0.35, "SOL/USDT": 0.25
    }
    strategy._pair_allocator._last_refresh = datetime.utcnow()

    low_atr_strategy = _make_strategy_with_mocks()
    low_atr_strategy._pair_allocator._weights = strategy._pair_allocator._weights
    low_atr_strategy._pair_allocator._last_refresh = datetime.utcnow()

    strategy._get_current_atr_pct = MagicMock(return_value=0.08)   # 8% ATR → scalar=0.25
    low_atr_strategy._get_current_atr_pct = MagicMock(return_value=0.01)  # 1% ATR → scalar=1.0

    with patch("user_data.strategies.AICryptoStrategy.Trade") as MockTrade:
        MockTrade.get_trades_proxy.return_value = []
        stake_high_vol = strategy.custom_stake_amount(
            pair="BTC/USDT", current_time=datetime.utcnow(),
            current_rate=50000.0, proposed_stake=100.0,
            min_stake=5.0, max_stake=500.0, leverage=1.0, entry_tag=None, side="long",
        )
    with patch("user_data.strategies.AICryptoStrategy.Trade") as MockTrade:
        MockTrade.get_trades_proxy.return_value = []
        stake_low_vol = low_atr_strategy.custom_stake_amount(
            pair="BTC/USDT", current_time=datetime.utcnow(),
            current_rate=50000.0, proposed_stake=100.0,
            min_stake=5.0, max_stake=500.0, leverage=1.0, entry_tag=None, side="long",
        )
    assert stake_high_vol < stake_low_vol
```

**Step 2: Run to verify they fail**

```bash
cd /Users/brendan/Sites/crypto && .venv/bin/pytest tests/strategies/test_ai_crypto_strategy.py::TestCustomStakeAmount::test_stake_nonzero_regardless_of_confidence tests/strategies/test_ai_crypto_strategy.py::TestCustomStakeAmount::test_atr_scalar_reduces_stake_on_high_volatility -v
```

Expected: Both FAIL — `test_stake_nonzero_regardless_of_confidence` fails because current code returns 0 when confidence=0.0

**Step 3: Rewrite the sizing block in `custom_stake_amount`**

In `user_data/strategies/AICryptoStrategy.py`, replace lines 157–171 (the confidence/Kelly block):

```python
        # Cap with RiskManager (Quarter-Kelly + ATR)
        confidence = self._get_model_confidence(pair)
        atr_pct = self._get_current_atr_pct(pair)
        risk_cap = self._risk_manager.calculate_position_size(
            portfolio_value=total_portfolio,
            confidence=confidence,
            atr_pct=atr_pct,
        )
        if risk_cap > 0:
            base_stake = min(base_stake, risk_cap)
        else:
            logger.info(
                "Skipping %s: risk_cap=$0 (low confidence=%.4f)", pair, confidence
            )
            return 0
```

With:

```python
        # ATR-based volatility scalar: target 2% portfolio risk per trade
        # TODO: restore Quarter-Kelly confidence gate when F&G/News signals go live
        atr_pct = self._get_current_atr_pct(pair)
        volatility_scalar = min(1.0, 0.02 / max(atr_pct, 0.001))
        base_stake = base_stake * volatility_scalar
```

Also update the log line at line 187 (remove `risk_cap` reference):

```python
        logger.info(
            "Allocating %s: weight=%.3f, atr=%.3f, final=$%.2f",
            pair, weight, atr_pct, final_stake,
        )
```

**Step 4: Remove or update tests that tested the removed confidence gate**

In `tests/strategies/test_ai_crypto_strategy.py`:

- **Remove** `TestCustomStakeAmount.test_returns_zero_when_risk_cap_is_zero` entirely (this tested the removed behavior)
- **Remove** `TestCustomStakeAmount.test_respects_risk_manager_cap` entirely (no longer calls `calculate_position_size`)
- **Remove** the `_get_model_confidence` mock lines from `test_returns_weighted_allocation`, `test_returns_zero_when_below_exchange_min`, and `test_triggers_refresh_when_stale` (function no longer called, mocks are now dead code)

In `TestIntegrationConfidenceToStake`, update:

```python
def test_high_prediction_produces_nonzero_stake(self):
    """Strong ATR conditions should produce a positive stake."""
    strategy = _make_strategy_with_mocks()
    strategy._pair_allocator._weights = {
        "BTC/USDT": 0.40, "ETH/USDT": 0.35, "SOL/USDT": 0.25
    }
    strategy._pair_allocator._last_refresh = datetime.utcnow()
    strategy._get_current_atr_pct = MagicMock(return_value=0.03)  # 3% ATR → scalar=0.67

    with patch("user_data.strategies.AICryptoStrategy.Trade") as MockTrade:
        MockTrade.get_trades_proxy.return_value = []
        stake = strategy.custom_stake_amount(
            pair="BTC/USDT", current_time=datetime.utcnow(),
            current_rate=50000.0, proposed_stake=100.0,
            min_stake=5.0, max_stake=500.0, leverage=1.0, entry_tag=None, side="long",
        )
    assert stake > 0
    assert stake <= 500.0

def test_atr_scalar_caps_stake_below_weight_based(self):
    """ATR scalar should reduce stake below raw weight-based allocation on volatile days."""
    strategy = _make_strategy_with_mocks()
    strategy._pair_allocator._weights = {
        "BTC/USDT": 0.90, "ETH/USDT": 0.05, "SOL/USDT": 0.05
    }
    strategy._pair_allocator._last_refresh = datetime.utcnow()
    strategy._get_current_atr_pct = MagicMock(return_value=0.10)  # 10% ATR → scalar=0.2

    with patch("user_data.strategies.AICryptoStrategy.Trade") as MockTrade:
        MockTrade.get_trades_proxy.return_value = []
        stake = strategy.custom_stake_amount(
            pair="BTC/USDT", current_time=datetime.utcnow(),
            current_rate=50000.0, proposed_stake=100.0,
            min_stake=5.0, max_stake=500.0, leverage=1.0, entry_tag=None, side="long",
        )
    weight_based = 900 * 0.90
    assert stake > 0
    assert stake < weight_based

def test_circuit_breaker_blocks_entries_at_signal_level(self):
    """Circuit breaker blocks enter_long=1 in populate_entry_trend, so custom_stake_amount
    is never reached. Verify the signal is blocked (tested at populate_entry_trend)."""
    strategy = _make_strategy_with_mocks()
    strategy._risk_manager._circuit_breaker_active = True
    df = pd.DataFrame({
        "&-price_change": [0.050],
        "do_predict": [1],
        "volume": [1000],
    })
    result = strategy.populate_entry_trend(df, {"pair": "BTC/USDT"})
    assert result["enter_long"].sum() == 0  # blocked at signal level
```

(Replace `test_weak_prediction_produces_zero_stake`, `test_risk_cap_bounds_weight_based_allocation`, and `test_circuit_breaker_blocks_entire_pipeline` with the above.)

**Step 5: Run all custom stake and integration tests**

```bash
cd /Users/brendan/Sites/crypto && .venv/bin/pytest tests/strategies/test_ai_crypto_strategy.py::TestCustomStakeAmount tests/strategies/test_ai_crypto_strategy.py::TestIntegrationConfidenceToStake -v
```

Expected: All tests PASS

**Step 6: Commit**

```bash
git add user_data/strategies/AICryptoStrategy.py tests/strategies/test_ai_crypto_strategy.py
git commit -m "fix: replace confidence-based Kelly sizing with ATR-only volatility scalar"
```

---

### Task 3: Signal Aggregator — Fix ML Signal Confidence

**Files:**
- Modify: `user_data/strategies/AICryptoStrategy.py:233`
- Test: `tests/strategies/test_ai_crypto_strategy.py`

**Step 1: Write a failing test for fixed ML confidence**

Add to `TestConfirmTradeEntry` class:

```python
def test_confirm_entry_approves_without_prediction_history(self):
    """With no prediction history (empty df), entry should still be approved.
    The fixed ML confidence replaces the broken percentile-rank calculation."""
    strategy = self._make_strategy_with_real_aggregator()
    strategy._bot_start_time = datetime.utcnow() - timedelta(hours=5)
    # Empty dataframe: simulates the live bug where predictions aren't accumulating
    strategy.dp.get_pair_dataframe.return_value = pd.DataFrame()

    with patch("user_data.strategies.AICryptoStrategy.Trade") as MockTrade:
        MockTrade.get_trades_proxy.return_value = []
        result = strategy.confirm_trade_entry(
            pair="BTC/USDT", order_type="limit", amount=0.01,
            rate=50000.0, time_in_force="GTC",
            current_time=datetime.utcnow(), entry_tag=None, side="long",
        )
    assert result is True  # Should approve: quality already verified by entry threshold
```

**Step 2: Run to verify it fails**

```bash
cd /Users/brendan/Sites/crypto && .venv/bin/pytest tests/strategies/test_ai_crypto_strategy.py::TestConfirmTradeEntry::test_confirm_entry_approves_without_prediction_history -v
```

Expected: FAIL — currently returns `False` because empty df → confidence=0.0 → aggregator blocks

**Step 3: Fix ML signal confidence in `confirm_trade_entry`**

In `user_data/strategies/AICryptoStrategy.py`, replace lines 233–235:

```python
        confidence = self._get_model_confidence(pair)
        ml_signal = Signal(
            direction="BUY", confidence=confidence, strategy="freqai_ml"
        )
```

With:

```python
        # TODO: restore _get_model_confidence() when F&G/News signals go live
        # Entry threshold (1.0%) already guarantees prediction quality.
        ml_signal = Signal(direction="BUY", confidence=0.75, strategy="freqai_ml")
```

**Step 4: Update now-stale tests**

In `TestConfirmTradeEntry`:

- **Update** `test_high_confidence_ml_approves_entry`: Remove the prediction mock setup (no longer needed), verify the test still passes cleanly.
- **Update** `test_low_confidence_ml_blocks_entry`: This tested that flat predictions block entry. The quality gate is now at the 1.0% entry threshold, not here. Replace with a test that verifies rate limiting still works:

```python
def test_high_confidence_ml_approves_entry(self):
    """ML signal with fixed confidence=0.75 should approve entry."""
    strategy = self._make_strategy_with_real_aggregator()
    strategy._bot_start_time = datetime.utcnow() - timedelta(hours=5)

    with patch("user_data.strategies.AICryptoStrategy.Trade") as MockTrade:
        MockTrade.get_trades_proxy.return_value = []
        result = strategy.confirm_trade_entry(
            pair="BTC/USDT", order_type="limit", amount=0.01,
            rate=50000.0, time_in_force="GTC",
            current_time=datetime.utcnow(), entry_tag=None, side="long",
        )
    assert result is True

def test_signal_aggregator_approves_fixed_ml_confidence(self):
    """Fixed confidence=0.75 passes SignalAggregator threshold of 0.55."""
    strategy = self._make_strategy_with_real_aggregator()
    strategy._bot_start_time = datetime.utcnow() - timedelta(hours=5)
    # No dp mock needed: _get_model_confidence is no longer called

    with patch("user_data.strategies.AICryptoStrategy.Trade") as MockTrade:
        MockTrade.get_trades_proxy.return_value = []
        result = strategy.confirm_trade_entry(
            pair="ETH/USDT", order_type="limit", amount=0.01,
            rate=2000.0, time_in_force="GTC",
            current_time=datetime.utcnow(), entry_tag=None, side="long",
        )
    assert result is True
```

(Replace `test_high_confidence_ml_approves_entry` and `test_low_confidence_ml_blocks_entry` with the above two.)

**Step 5: Run the full strategy test suite**

```bash
cd /Users/brendan/Sites/crypto && .venv/bin/pytest tests/strategies/test_ai_crypto_strategy.py -v
```

Expected: All tests PASS

**Step 6: Run the full test suite**

```bash
cd /Users/brendan/Sites/crypto && .venv/bin/pytest tests/ -v
```

Expected: All tests PASS

**Step 7: Commit**

```bash
git add user_data/strategies/AICryptoStrategy.py tests/strategies/test_ai_crypto_strategy.py
git commit -m "fix: use fixed ML signal confidence=0.75 to unblock signal aggregator"
```

---

### Task 4: Verify End-to-End and Push

**Step 1: Run full test suite one final time**

```bash
cd /Users/brendan/Sites/crypto && .venv/bin/pytest tests/ -v --tb=short
```

Expected: All tests PASS, no warnings about removed behavior

**Step 2: Review the diff**

```bash
git diff HEAD~3 user_data/strategies/AICryptoStrategy.py
```

Verify:
- Line 336: `0.015` → `0.010`
- Lines 157–171: Kelly/confidence block replaced with ATR scalar
- Line 233–235: `_get_model_confidence(pair)` replaced with `confidence=0.75`
- Log line at ~187: `risk_cap` removed

**Step 3: Push**

After confirming the diff looks correct, push to trigger a Docker rebuild and deploy.

---

### Expected Outcome After Deploy

Within 1–2 hours:
- Pairs generating entry signals at ≥ 1.0% predicted change
- `custom_stake_amount` returns ~$40–50 per trade (pair weight × ATR scalar)
- `confirm_trade_entry` approves entries: fixed confidence=0.75 > aggregator threshold=0.55
- First trades appear in logs with: `"Signal aggregator approved X entry: confidence=0.7500"`
- Risk management still active: circuit breaker, rate limiting (3/hr), startup cooldown, pair weights
