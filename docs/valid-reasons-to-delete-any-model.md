# Valid Reasons to Delete FreqAI Models

> **Model directory**: `user_data/models/ai_crypto_v1/`
> **Delete command**: `rm -rf user_data/models/ai_crypto_v1/`
> **Archive command**: `cp -r user_data/models/ai_crypto_v1/ user_data/models/archive/ai_crypto_v1_$(date +%Y%m%d_%H%M%S)/`
>
> **ALWAYS archive before deleting. Never delete cold.**

---

## How FreqAI Model Compatibility Works

FreqAI saves the exact list of feature names used during training inside each model's metadata file (e.g. `cb_btc_<timestamp>_metadata.json`, field `training_features_list`). When the bot loads a model, it compares the incoming features with that saved list. If there is **any mismatch in feature names, count, or order**, the model is considered incompatible and will crash or produce garbage predictions.

Feature names in this project are structured like:
```
%-rsi-period_10_1h_10_BTC/USDT_1h
%-rsi-period_10_1h_10_shift-1_BTC/USDT_1h
%-rsi-period_10_1h_10_BTC/USDT_4h
```

The name encodes: **indicator** + **period** + **base timeframe** + **period** + **correlation pair** + **data timeframe**. This means even renaming a pair (e.g. `BTC/USDT` → `BTC/USD`) breaks all models.

---

## ❌ MUST DELETE — Breaking Changes

These changes make existing models 100% incompatible. The bot will crash or silently malfunction if you don't delete.

### 1. Adding or Removing Any Technical Indicator

**Affected code**: `AICryptoStrategy.py` → `feature_engineering_expand_all()`, `feature_engineering_expand_basic()`, `feature_engineering_standard()`

**Current indicators** (adding or removing ANY of these = delete all models):
| Function | Indicators |
|---|---|
| `expand_all` (period-dependent) | RSI, MFI, ADX, CCI, ATR, BB Width |
| `expand_basic` (fixed) | pct_change, volume_mean_ratio, high_low_pct, MACD, MACD signal, MACD histogram |
| `standard` (fixed) | day_of_week, hour_of_day |

**Examples of breaking changes**:
- Adding `ta.STOCH()` (Stochastic)
- Adding `ta.OBV()` (On-Balance Volume)
- Removing `%-mfi` (Money Flow Index)
- Renaming any column (e.g. `%-bb_width` → `%-bollinger_width`)

> **Why**: Each indicator becomes one or more feature columns. The model was trained expecting an exact column count and names. A mismatch means the feature matrix is a different shape.

---

### 2. Changing `indicator_periods_candles` in config.json

**Affected config**: `freqai.feature_parameters.indicator_periods_candles`
**Current value**: `[10, 20]`

Feature names include the period number: `%-rsi-period_10_...`, `%-rsi-period_20_...`

**Examples of breaking changes**:
- `[10, 20]` → `[10, 20, 50]` — adds 50-period features → incompatible
- `[10, 20]` → `[14, 21]` — changes feature names → incompatible
- `[10, 20]` → `[20]` — removes 10-period features → incompatible

---

### 3. Changing `include_timeframes` in config.json

**Affected config**: `freqai.feature_parameters.include_timeframes`
**Current value**: `["1h", "4h"]`

Feature names include the timeframe: `%-rsi-period_10_1h_..._BTC/USDT_4h`

**Examples of breaking changes**:
- Adding `"15m"` timeframe — adds new feature columns → incompatible
- Removing `"4h"` — removes hundreds of feature columns → incompatible
- Changing `"1h"` → `"30m"` — renames all features → incompatible

---

### 4. Changing `include_corr_pairlist` in config.json

**Affected config**: `freqai.feature_parameters.include_corr_pairlist`
**Current value**: `["BTC/USDT", "ETH/USDT"]`

Each correlation pair generates features for ALL indicators × ALL periods × ALL timeframes. The pair name is baked into every feature name.

**Examples of breaking changes**:
- Adding `"SOL/USDT"` as a correlation pair → massive feature expansion → incompatible
- Removing `"ETH/USDT"` → removes ~50% of features → incompatible
- Changing `"BTC/USDT"` → `"BTC/USD"` → renames all BTC features → incompatible

> **Note**: Adding new *trading pairs* to the whitelist is safe (FreqAI trains new models for them). Adding pairs to *corr_pairlist* is NOT safe.

---

### 5. Changing `include_shifted_candles` in config.json

**Affected config**: `freqai.feature_parameters.include_shifted_candles`
**Current value**: `1`

Shifted candles duplicate all features with a `shift-1` suffix. Changing this multiplies or reduces the feature count.

**Examples of breaking changes**:
- `1` → `2` — doubles shifted features → incompatible
- `1` → `0` — removes all shifted features → incompatible

---

### 6. Changing the Target Variable

**Affected code**: `AICryptoStrategy.py` → `set_freqai_targets()`
**Current target**: `&-price_change = (close[+12] - close) / close`

The target column name (`&-price_change`) and formula are baked into the model's label pipeline.

**Examples of breaking changes**:
- Renaming `&-price_change` to `&-return` → incompatible (label name mismatch)
- Changing the formula (e.g. log returns instead of raw returns) → incompatible
- Adding a second target column (multi-target regression) → incompatible
- Switching from regression to classification (adding `&-direction` as binary target) → incompatible

---

### 7. Changing `label_period_candles` in config.json

**Affected config**: `freqai.feature_parameters.label_period_candles`
**Current value**: `12` (predicts 12 hours ahead on 1h candles)

This changes `shift(-label_period)` in `set_freqai_targets()`, which changes the actual numerical distribution of the target variable. A model trained to predict 12h returns cannot predict 24h returns.

**Examples of breaking changes**:
- `12` → `24` — changes prediction horizon from 12h to 24h → models are incompatible

> While the feature names don't change, the labels the model learned map to a completely different distribution. **Always delete models when changing this value.**

---

### 8. Changing the Model Type

**Affected config**: `freqai.freqaimodel`
**Current value**: `XGBoostRegressor`

Each FreqAI model class serializes and deserializes model files differently. An XGBoost `.joblib` file cannot be loaded by a LightGBM or CatBoost model class.

**Examples of breaking changes**:
- `XGBoostRegressor` → `LightGBMRegressor` → incompatible
- `XGBoostRegressor` → `XGBoostClassifier` → incompatible (different output format)
- `XGBoostRegressor` → `CatboostRegressor` → incompatible

---

### 9. Major FreqAI / FreqTrade / XGBoost Version Upgrade

FreqAI's model serialization format can change between major versions. XGBoost's `.joblib` format can also break between major versions (e.g. xgboost 1.x → 2.x).

**How to check**: After upgrading, if the bot starts and immediately retrains all pairs, the old models are incompatible.

**Current versions** (from Dockerfile — `freqtradeorg/freqtrade:stable`):
- Track the FreqTrade release notes for any breaking changes in model format

---

### 10. Corrupted Model Files

If `historic_predictions.pkl`, `pair_dictionary.json`, `global_metadata.json`, or any `cb_<pair>_<ts>_model.joblib` file is corrupted (e.g. disk error, interrupted write during a VPS restart), the bot will crash on load.

**Signs of corruption**:
- `EOFError: Ran out of input` in logs
- `_pickle.UnpicklingError` in logs
- Bot restarting in a crash loop immediately after startup

**Fix**: Delete only the corrupted pair's `sub-train-<PAIR>_<ts>/` directory, or the entire model directory if `historic_predictions.pkl` is the corrupt file.

---

## ✅ DO NOT DELETE — Safe Changes

These changes do NOT require model deletion. FreqAI handles them automatically:

| Change | Why It's Safe |
|---|---|
| Adding new trading pairs to `config.pairs.json` | FreqAI trains new models for new pairs; existing models untouched |
| Changing `n_estimators`, `learning_rate`, `max_depth` | Hyperparameters only; next scheduled retrain uses new params |
| Changing `train_period_days` | FreqAI downloads more/less data for next retrain; old models still valid until then |
| Changing `live_retrain_hours` | Changes retrain frequency, not model structure |
| Changing `ENTRY_THRESHOLD` | Strategy-level logic, doesn't touch the model |
| Changing `stoploss`, `minimal_roi`, `trailing_stop` | Trade management logic, not model |
| Changing `max_open_trades`, `stake_amount` | Portfolio management, not model |
| Changing `DI_threshold` | Inference-time filtering only; model unchanged |
| Changing `purge_old_models` | Just controls how many old models to keep on disk |
| Changing Telegram/API settings | Notification config, not model |
| Changing `weight_factor` | Affects how data is weighted during next retrain, not current models |
| Removing trading pairs | Old pair models are ignored; no crash |
| Updating entry/exit signal code | Strategy logic, not feature engineering |
| Changing `startup_cooldown_hours`, `max_entries_per_hour` | Strategy rate-limiting, not model |

---

## ⚠️ AMBIGUOUS — Requires Testing

| Change | Risk |
|---|---|
| Enabling `principal_component_analysis: true` | **High** — PCA changes the parameter space; FreqAI docs explicitly flag this |
| Enabling `use_SVM_to_remove_outliers: true` | **Medium** — changes training data distribution; existing models may degrade |
| Adding new external data sources (e.g., LunarCrush, Glassnode) as features | **High** — adds new feature columns; all existing models incompatible |
| Changing `reg_alpha` or `reg_lambda` | **Low** — regularization params; safe at next retrain |
| Minor FreqTrade patch version update (e.g. 2024.5 → 2024.6) | **Low** — usually backward compatible; monitor logs after upgrade |

---

## Model Preservation Strategy — Avoid Losing Training Knowledge

> The raw market data (OHLCV from Bybit) can always be re-downloaded. What you lose when deleting models is the **trained model weights** — the accumulated pattern learning from weeks of 4-hourly retrains.

### Tier 1: Before Any Potentially Breaking Change

```bash
# Archive current models with timestamp
cp -r user_data/models/ai_crypto_v1/ \
  user_data/models/archive/ai_crypto_v1_$(date +%Y%m%d_%H%M%S)/

# Also back up historic predictions (contains recent prediction history)
cp user_data/models/ai_crypto_v1/historic_predictions.pkl \
  user_data/models/archive/historic_predictions_$(date +%Y%m%d_%H%M%S).pkl
```

### Tier 2: Use a New Identifier Instead of Deleting

Instead of deleting `ai_crypto_v1`, change the `identifier` in config.json to `ai_crypto_v2`. FreqAI creates a fresh model directory while `ai_crypto_v1/` remains intact. If the new version has issues, you can roll back by reverting the identifier.

```json
"freqai": {
    "identifier": "ai_crypto_v2"
}
```

### Tier 3: VPS Backup Schedule (Once on VPS)

Set up a daily cron job on the VPS to sync models to a cheap object storage bucket (e.g. Hetzner Object Storage at €0.019/GB, or Cloudflare R2 free tier up to 10GB).

```bash
# Daily model backup cron (add to crontab)
0 3 * * * rclone sync /freqtrade/user_data/models/ \
  r2:your-bucket/models/$(date +%Y-%m-%d)/ >> /logs/model-backup.log 2>&1
```

### Tier 4: Feature Lock File

To prevent accidental feature changes, maintain a `FEATURE_LOCK.json` at the project root that documents the exact feature fingerprint of the current production model. Before any feature change, verify you understand the implications:

```json
{
  "identifier": "ai_crypto_v1",
  "timeframes": ["1h", "4h"],
  "corr_pairs": ["BTC/USDT", "ETH/USDT"],
  "indicator_periods": [10, 20],
  "shifted_candles": 1,
  "label_period_candles": 12,
  "target_column": "&-price_change",
  "model_type": "XGBoostRegressor",
  "feature_count_per_pair": 72,
  "locked_at": "2026-03-14",
  "note": "Changing ANY value above requires deleting models. Change identifier first."
}
```

---

## Quick Reference Decision Tree

```
Is the change in feature_engineering_*() functions?  → DELETE
Is the change to indicator_periods_candles?            → DELETE
Is the change to include_timeframes?                   → DELETE
Is the change to include_corr_pairlist?                → DELETE
Is the change to include_shifted_candles?              → DELETE
Is the change to set_freqai_targets()?                 → DELETE
Is the change to label_period_candles?                 → DELETE
Is the change to freqaimodel type?                     → DELETE
Is it a major version upgrade of FreqTrade/XGBoost?   → TEST FIRST, likely DELETE
Is the change to hyperparameters only?                 → SAFE (next retrain picks up)
Is the change adding new trading pairs?                → SAFE
Is the change to strategy entry/exit logic?            → SAFE
Everything else?                                       → SAFE (but monitor logs)
```

---

*Last updated: 2026-03-14 | Model ID: ai_crypto_v1 | FreqAI: XGBoostRegressor*
