# Strategy

Technical reference for `AICryptoStrategy` (`user_data/strategies/AICryptoStrategy.py`).

## Feature Engineering

Features are computed at three levels:

### `feature_engineering_expand_all()`
Computed for each period in `indicator_periods_candles` (10, 20, 50):
- **RSI** — Relative Strength Index
- **MFI** — Money Flow Index
- **ADX** — Average Directional Index
- **CCI** — Commodity Channel Index
- **ATR** — Average True Range
- **Bollinger Band width** — volatility measure

### `feature_engineering_expand_basic()`
Computed once per candle:
- **pct_change** — percentage price change
- **volume_mean_ratio** — current volume vs rolling mean
- **high_low_pct** — high-low range as percentage
- **MACD** — macd, macdsignal, macdhist

### `feature_engineering_standard()`
Time-based features:
- **day_of_week** (0-6)
- **hour_of_day** (0-23)

## Target Variable

```
&-price_change = percentage price change over next label_period_candles (24) candles
```

This is a continuous value, not binary. The model predicts how much the price will move, not just up/down.

## Entry Logic

Enter long when:
- `&-price_change > 0.005` (predicted >0.5% price increase)
- Volume > 0
- Circuit breaker is NOT active

## Exit Logic

Exit long when:
- `&-price_change < 0` (predicted price decrease)

## Why XGBoostRegressor (Not Classifier)

XGBoostClassifier crashed with `"y contains previously unseen labels"` when training data only contained one class (e.g., all prices went down). The LabelEncoder saw only one class during training, then encountered the other class during prediction, causing `inverse_transform` to fail.

XGBoostRegressor predicts continuous values, avoiding the label encoding issue entirely. See [FreqAI Errors](../debugging/freqai-errors.md) for the full diagnosis.

## Strategy Parameters

| Parameter | Value |
|---|---|
| `minimal_roi` | 10% at 0min, 5% at 30min, 2% at 120min, 0% at 360min |
| `stoploss` | -5% |
| `trailing_stop` | enabled |
| `process_only_new_candles` | True |
| `startup_candle_count` | 50 |
