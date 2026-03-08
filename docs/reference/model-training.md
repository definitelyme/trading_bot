# Model Training

## Model

**XGBoostRegressor** — predicts continuous price change percentages.

Not XGBoostClassifier — see [FreqAI Errors](../debugging/freqai-errors.md) for why we switched.

## Training Pipeline

1. Download 30 days of OHLCV data for each pair (1h and 4h timeframes)
2. Compute features (~290-434 features per pair depending on correlation pairs)
3. Split: 67% train, 33% test (`random_state=42`)
4. Train XGBoost with 800 estimators, `learning_rate=0.02`, `max_depth=8`
5. DI (Dissimilarity Index) rejects outlier predictions (`DI_threshold=0.9`)
6. ~20-25 seconds per pair, ~4-5 minutes total for 11 pairs

## Retrain Cycle

Every 4 hours (`live_retrain_hours: 4`), using the latest 30 days of data.

## When to Delete Models

Model directory: `user_data/models/ai_crypto_v1/`

Delete command: `rm -rf user_data/models/ai_crypto_v1/`

**MUST delete when:**
- Changed the target variable (e.g., classifier → regressor)
- Changed features (added/removed indicators)
- Changed model type

**Do NOT delete when** (FreqAI handles automatically):
- Added new trading pairs (trains new models, keeps existing)
- Changed entry/exit thresholds (strategy logic, not model)
- Changed config values (retrain hours, max trades, etc.)

## Tuning Parameters

| Parameter | Current Value | Effect |
|---|---|---|
| `n_estimators` | 800 | More trees = slower training, potentially better accuracy |
| `learning_rate` | 0.02 | Lower = more conservative learning, needs more estimators |
| `max_depth` | 8 | Deeper trees = more complex patterns, risk of overfitting |
| `train_period_days` | 30 | Longer = more data, but older data may be less relevant |
| `label_period_candles` | 24 | Prediction horizon — 24 candles = 24 hours at 1h timeframe |
| `indicator_periods_candles` | [10, 20, 50] | Lookback windows for technical indicators |

## Training Log Indicators

**Healthy training output:**
- `Starting training BTC/USDT` — training begins for a pair
- `Training model on N features` — feature count
- `Training model on N data points` — sample count
- `Done training BTC/USDT (20s)` — completed successfully
- `Total time spent training pairlist Ns` — all pairs done

**Warning signs:**
- `dropped N% of training data due to NaNs` — 18% is normal (indicator warmup), >30% investigate
- `DI tossed N predictions for being too far from training data` — normal, means outlier rejection is working
