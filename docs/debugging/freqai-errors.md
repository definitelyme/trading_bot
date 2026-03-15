# FreqAI Errors

## "y contains previously unseen labels: [1]"

**Symptom**: Every pair fails with `ValueError` on every candle cycle.

**Cause**: XGBoostClassifier was trained on data where only one price direction existed (all down or all up). `LabelEncoder` only saw one class. During prediction, encountering the other class crashes `inverse_transform`.

**Fix**: Switch from XGBoostClassifier to XGBoostRegressor:
- `config.json`: change `freqaimodel` to `XGBoostRegressor`
- `config.live.json`: same change
- `docker-compose.yml`: update `--freqaimodel` flag
- `AICryptoStrategy.py`: change target from binary (0/1) to continuous (% price change), update entry/exit logic to use percentage thresholds instead of class probabilities

**Prevention**: Use XGBoostRegressor for price prediction tasks. Classifiers are fragile when training data can be heavily skewed.

---

## "dropped N% of training data due to NaNs"

**Symptom**: Warning during training: `"18 percent of training data dropped due to NaNs"`.

**Cause**: Technical indicators need warmup candles (e.g., 50-period RSI needs 50 candles). Early rows have NaN values that get dropped.

**Fix**: This is normal up to ~20%. If >30%, check indicator periods vs available data.

**Prevention**: Ensure `train_period_days` provides enough data for the longest indicator period.

---

## "DI tossed N predictions for being too far from training data"

**Symptom**: Info message during prediction.

**Cause**: Dissimilarity Index detected predictions on data points that are too different from training data. These get marked as low confidence.

**Fix**: Normal behavior. `DI_threshold=0.9` is the cutoff.

**Prevention**: N/A — this is a safety feature.

---

## When to Delete Models

**Path**: `user_data/models/ai_crypto_v1/`

**Delete command**: `rm -rf user_data/models/ai_crypto_v1/`

**MUST delete when**:
- Target variable changed
- Features changed (added/removed indicators)
- Model type changed

**Do NOT delete when**:
- New pairs added
- Thresholds changed
- Config values changed

---

## TypeError: can't subtract offset-naive and offset-aware datetimes

**Symptom**: `strategy_wrapper - ERROR - Unexpected error TypeError("can't subtract offset-naive and offset-aware datetimes") calling confirm_trade_entry`

**Cause**: In Freqtrade 2026.2+, `current_time` passed to strategy hooks is a **timezone-aware** UTC datetime. `Trade.open_date` is also timezone-aware. The original fix (2026-03-11) only stripped tzinfo from `t.open_date` but left `current_time` aware — so the subtraction still failed when `current_time` was aware.

**Fix** (updated 2026-03-15 in `AICryptoStrategy.py`):
- Normalise `current_time` to naive UTC at the top of `confirm_trade_entry` via `ct_naive = current_time.replace(tzinfo=None)`, then use `ct_naive` for all arithmetic.
- This handles both aware and naive inputs (`.replace(tzinfo=None)` is a no-op on already-naive datetimes).

**Impact if unpatched**: `confirm_trade_entry` crashes whenever there are open trades. Freqtrade's `strategy_wrapper` catches the exception and **defaults to True (allow entry)** — so the trade still opens, but ALL safety gates (startup cooldown, rate limit, signal aggregation) are silently bypassed.

---

## ATR stake sizing always returns fallback value ($36.36)

**Symptom**: All allocations show `atr=0.050` regardless of pair. Every stake is identical at $36.36.

**Cause**: `_get_current_atr_pct` searched `dp.get_pair_dataframe()` for `%-atr-*` columns, but those columns are created inside FreqAI's internal training pipeline and are **not** present in the dataprovider's main dataframe. The column-not-found branch always returned the 0.05 fallback.

**Fix** (applied 2026-03-11 in `AICryptoStrategy.py`):
Replaced column-lookup with a direct `ta.ATR(df, timeperiod=10)` call on the raw OHLCV dataframe — which is always available from `dp.get_pair_dataframe()`.

**After fix**: Stakes will vary by actual pair volatility — BTC ~$90 (low ATR%), WIF ~$22 (high ATR%).
