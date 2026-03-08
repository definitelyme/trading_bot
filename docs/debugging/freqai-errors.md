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
