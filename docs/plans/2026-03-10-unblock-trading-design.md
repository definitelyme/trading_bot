# Design: Unblock Trading — Confidence Gate Fix

**Date**: 2026-03-10
**Status**: Approved

## Problem

After 13+ hours of live running (2026-03-09 03:00–16:00 UTC), zero trades were executed despite the model training and inferring correctly. Two blockers identified:

### Blocker 1: `_get_model_confidence()` always returns `0.0000`

`_get_model_confidence()` uses `dp.get_pair_dataframe()["&-price_change"].dropna()` to compute a percentile rank. In FreqAI live mode, this column only contains predictions for candles since startup — not historical training predictions. With `process_only_new_candles = True`, only 1 prediction exists per candle close, so `dropna()` returns < 10 values, triggering the early return of `0.0`.

This breaks the full trade chain:
- `custom_stake_amount()` → `RiskManager.calculate_position_size(confidence=0.0)` → returns `0` (below `min_confidence=0.55`) → logs "Skipping: risk_cap=$0" every 5s
- `confirm_trade_entry()` is never reached (stake=0)
- 15,000+ redundant log lines per window

### Blocker 2: Entry threshold too high for current market

Since the 10:00 UTC retrain, all 11 pairs show zero entry signals. The 1.5% threshold requires the model to predict a move of 0.47 std deviations (labels_std ≈ 3.16%). During calm market periods, no predictions exceed this.

## Root Cause: Confidence Gate Designed for Multi-Source Operation

The confidence gate (RiskManager + SignalAggregator) was designed assuming 3 live signal sources: ML, Fear & Greed, and News Sentiment. Both non-ML sources are currently dormant (disabled via env vars, return `None`). The ML signal alone must clear thresholds calibrated for multi-source consensus — which it cannot do with a broken confidence function.

## Decision: Simplify for Now (YAGNI)

The confidence gate will be bypassed until Fear & Greed and News Sentiment signals go live. The ML entry threshold (1.0%) serves as the quality gate. Confidence-based sizing will be restored when all three signal sources are active.

## Design

### Change 1: Entry threshold

**File**: `user_data/strategies/AICryptoStrategy.py`, `populate_entry_trend()`

```python
# Before
(dataframe["&-price_change"] > 0.015)

# After
(dataframe["&-price_change"] > 0.010)
```

Lowers the minimum predicted price change from 1.5% to 1.0%. At labels_std=3.16%, this corresponds to 0.32 std deviations vs 0.47 — meaningful conviction without excessive noise.

### Change 2: Position sizing — remove confidence gate

**File**: `user_data/strategies/AICryptoStrategy.py`, `custom_stake_amount()`

Replace Kelly/confidence-based sizing with ATR-only volatility scalar:

```python
# Before (broken — always returns 0)
confidence = self._get_model_confidence(pair)
atr_pct = self._get_current_atr_pct(pair)
risk_cap = self._risk_manager.calculate_position_size(
    portfolio_value=total_portfolio, confidence=confidence, atr_pct=atr_pct
)
if risk_cap > 0:
    base_stake = min(base_stake, risk_cap)
else:
    logger.info("Skipping %s: risk_cap=$0 (low confidence=%.4f)", pair, confidence)
    return 0

# After
atr_pct = self._get_current_atr_pct(pair)
volatility_scalar = min(1.0, 0.02 / max(atr_pct, 0.001))
base_stake = base_stake * volatility_scalar
```

Expected stake at $1000 portfolio (11 pairs, equal weight ≈ 9.1%, ATR 3-5%): ~$40–50 per trade.

Also fix the log line to remove the `risk_cap` reference.

### Change 3: Signal aggregator — fix ML signal confidence

**File**: `user_data/strategies/AICryptoStrategy.py`, `confirm_trade_entry()`

```python
# Before (broken — confidence=0.0 causes aggregator to return HOLD)
confidence = self._get_model_confidence(pair)
ml_signal = Signal(direction="BUY", confidence=confidence, strategy="freqai_ml")

# After
# TODO: restore _get_model_confidence() when F&G/News signals go live
ml_signal = Signal(direction="BUY", confidence=0.75, strategy="freqai_ml")
```

The entry threshold (1.0%) already validates prediction quality. A fixed confidence of 0.75 passes both `RiskManager.min_confidence=0.55` and `SignalAggregator.min_confidence=0.55`. Fear & Greed and News Sentiment are unchanged — already dormant via env vars.

## What Does Not Change

- Exit threshold: `-0.005` (-0.5%) — already conservative, no change
- `RiskManager` circuit breaker — still active (drawdown protection)
- `_get_model_confidence()` function body — kept, no longer called, tagged with TODO
- Pair allocator weights — still drives base position sizing
- Rate limiting + startup cooldown — unchanged
- Fear & Greed + News Sentiment infrastructure — unchanged (dormant, return None)

## Expected Outcome After Deploy

- Entry signals generated when model predicts ≥ 1.0% price change
- `custom_stake_amount()` returns ~$40–50 per trade (ATR-scaled)
- `confirm_trade_entry()` approves entries with fixed ML confidence=0.75
- First trades expected within 1–2 candles (1–2 hours) of deploy
- Risk management still active: circuit breaker, rate limiting, pair weights

## Future Work

When Fear & Greed and News Sentiment signals go live:
1. Restore `_get_model_confidence()` call in both `custom_stake_amount()` and `confirm_trade_entry()`
2. Fix `_get_model_confidence()` to use accumulated prediction history (instance variable updated in `populate_entry_trend()`)
3. Raise `SignalAggregator.min_confidence` back to multi-source calibrated value (0.60–0.65)
4. Re-evaluate entry threshold based on live trading performance
