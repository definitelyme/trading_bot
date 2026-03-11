# Analytics & Logging Enhancement Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-candle prediction logging to the strategy, fix the broken allocation report parser, add signal pass/fail tracking to 2h reports, and create a daily SQLite database export with 7-day rolling retention.

**Architecture:** Three independent additions to the existing cron pipeline — (1) in-strategy log emission via a new `_log_predictions` method, (2) extended log parser + report generator that parses the new lines and fixes a pre-existing broken regex, (3) a new bash export script invoked by a new cron entry. No new infrastructure, no new dependencies.

**Tech Stack:** Python 3.13, pytest, talib, pandas, Docker CLI (`docker cp`), cron

**Spec:** `docs/superpowers/specs/2026-03-11-analytics-logging-design.md`

**Run tests with:** `.venv/bin/python -m pytest tests/ -v`

---

## Chunk 1: Strategy — ENTRY_THRESHOLD + _log_predictions

**Files:**
- Modify: `user_data/strategies/AICryptoStrategy.py`
- Test: `tests/strategies/test_ai_crypto_strategy.py`

---

### Task 1: Add ENTRY_THRESHOLD class constant

Replace the hardcoded `0.010` literal in `populate_entry_trend` with a class-level constant so `_log_predictions` can reference it without duplication.

- [ ] **Step 1: Write a failing test verifying the constant exists and equals 0.010**

Add to `tests/strategies/test_ai_crypto_strategy.py` after the `test_strategy_file_exists` test:

```python
def test_entry_threshold_constant_defined():
    """ENTRY_THRESHOLD class constant must exist and equal 0.010."""
    assert hasattr(AICryptoStrategy, "ENTRY_THRESHOLD")
    assert AICryptoStrategy.ENTRY_THRESHOLD == 0.010
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
.venv/bin/python -m pytest tests/strategies/test_ai_crypto_strategy.py::test_entry_threshold_constant_defined -v
```

Expected: `FAILED — AttributeError: type object 'AICryptoStrategy' has no attribute 'ENTRY_THRESHOLD'`

- [ ] **Step 3: Add ENTRY_THRESHOLD to AICryptoStrategy**

In `user_data/strategies/AICryptoStrategy.py`, add the constant inside the class body, after `startup_candle_count = 50` (line 49):

```python
    # Entry threshold: minimum predicted price change to trigger a signal
    ENTRY_THRESHOLD: float = 0.010
```

Then update `populate_entry_trend` to use it. Replace line 329:

```python
                (dataframe["&-price_change"] > 0.010)
```

with:

```python
                (dataframe["&-price_change"] > self.ENTRY_THRESHOLD)
```

- [ ] **Step 4: Run test and all strategy tests to confirm they pass**

```bash
.venv/bin/python -m pytest tests/strategies/test_ai_crypto_strategy.py -v
```

Expected: all tests pass, including `test_entry_threshold_constant_defined`.

- [ ] **Step 5: Commit**

```bash
git add user_data/strategies/AICryptoStrategy.py tests/strategies/test_ai_crypto_strategy.py
git commit -m "feat: add ENTRY_THRESHOLD class constant to AICryptoStrategy"
```

---

### Task 2: Add _log_predictions method

Add a private method that logs one structured line per candle cycle for any pair, before the circuit breaker early return so predictions are always captured.

- [ ] **Step 1: Write failing tests for _log_predictions**

Add a new class `TestLogPredictions` to `tests/strategies/test_ai_crypto_strategy.py`:

```python
import logging

class TestLogPredictions:
    """Tests for _log_predictions per-candle logging."""

    def _make_df(self, pred, close=50000.0, do_predict=1):
        return pd.DataFrame({
            "&-price_change": [pred],
            "do_predict": [do_predict],
            "close": [close],
        })

    def test_logs_above_when_pred_exceeds_threshold(self, caplog):
        strategy = _make_strategy_with_mocks()
        df = self._make_df(pred=0.015)
        with caplog.at_level(logging.INFO, logger="AICryptoStrategy"):
            strategy._log_predictions(df, {"pair": "BTC/USDT"})
        assert "PREDICTION BTC/USDT" in caplog.text
        assert "ABOVE" in caplog.text

    def test_logs_below_when_pred_under_threshold(self, caplog):
        strategy = _make_strategy_with_mocks()
        df = self._make_df(pred=0.005)
        with caplog.at_level(logging.INFO, logger="AICryptoStrategy"):
            strategy._log_predictions(df, {"pair": "ETH/USDT"})
        assert "PREDICTION ETH/USDT" in caplog.text
        assert "BELOW" in caplog.text

    def test_skips_when_price_change_column_missing(self, caplog):
        strategy = _make_strategy_with_mocks()
        df = pd.DataFrame({"do_predict": [1], "close": [100.0]})
        with caplog.at_level(logging.INFO, logger="AICryptoStrategy"):
            strategy._log_predictions(df, {"pair": "SOL/USDT"})
        assert "PREDICTION" not in caplog.text

    def test_skips_when_do_predict_column_missing(self, caplog):
        strategy = _make_strategy_with_mocks()
        df = pd.DataFrame({"&-price_change": [0.02], "close": [100.0]})
        with caplog.at_level(logging.INFO, logger="AICryptoStrategy"):
            strategy._log_predictions(df, {"pair": "SOL/USDT"})
        assert "PREDICTION" not in caplog.text

    def test_skips_when_dataframe_empty(self, caplog):
        strategy = _make_strategy_with_mocks()
        df = pd.DataFrame()
        with caplog.at_level(logging.INFO, logger="AICryptoStrategy"):
            strategy._log_predictions(df, {"pair": "BTC/USDT"})
        assert "PREDICTION" not in caplog.text

    def test_skips_when_prediction_is_nan(self, caplog):
        strategy = _make_strategy_with_mocks()
        df = self._make_df(pred=float("nan"))
        with caplog.at_level(logging.INFO, logger="AICryptoStrategy"):
            strategy._log_predictions(df, {"pair": "BTC/USDT"})
        assert "PREDICTION" not in caplog.text

    def test_log_contains_pred_and_close(self, caplog):
        strategy = _make_strategy_with_mocks()
        df = self._make_df(pred=0.0143, close=84253.50)
        with caplog.at_level(logging.INFO, logger="AICryptoStrategy"):
            strategy._log_predictions(df, {"pair": "DOGE/USDT"})
        assert "PREDICTION DOGE/USDT" in caplog.text
        assert "1.43%" in caplog.text

    def test_works_without_close_column(self, caplog):
        """close column is optional — should not crash if absent."""
        strategy = _make_strategy_with_mocks()
        df = pd.DataFrame({"&-price_change": [0.015], "do_predict": [1]})
        with caplog.at_level(logging.INFO, logger="AICryptoStrategy"):
            strategy._log_predictions(df, {"pair": "WIF/USDT"})
        assert "PREDICTION WIF/USDT" in caplog.text

    def test_populate_entry_trend_calls_log_predictions(self, caplog):
        """_log_predictions fires from populate_entry_trend even when circuit
        breaker is active (placed before the early return)."""
        strategy = _make_strategy_with_mocks()
        strategy._risk_manager._circuit_breaker_active = True
        df = pd.DataFrame({
            "&-price_change": [0.020],
            "do_predict": [1],
            "close": [50000.0],
            "volume": [1000],
        })
        with caplog.at_level(logging.INFO, logger="AICryptoStrategy"):
            strategy.populate_entry_trend(df, {"pair": "BTC/USDT"})
        assert "PREDICTION BTC/USDT" in caplog.text
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/strategies/test_ai_crypto_strategy.py::TestLogPredictions -v
```

Expected: `FAILED — AttributeError: 'AICryptoStrategy' object has no attribute '_log_predictions'`

- [ ] **Step 3: Implement _log_predictions**

Add after `_get_current_atr_pct` in `user_data/strategies/AICryptoStrategy.py` (before `custom_stake_amount`):

```python
    def _log_predictions(self, dataframe: DataFrame, metadata: dict) -> None:
        """Emit one structured log line per candle for observability.

        Fires for every pair every candle regardless of circuit breaker state.
        Captured by log_parser.py for the 2h report Prediction & Signal Summary.
        """
        pair = metadata.get("pair", "?")
        if dataframe.empty:
            return
        if "&-price_change" not in dataframe.columns or "do_predict" not in dataframe.columns:
            return
        pred = dataframe["&-price_change"].iloc[-1]
        if pd.isna(pred):
            return
        close = dataframe["close"].iloc[-1] if "close" in dataframe.columns else 0.0
        do_predict = int(dataframe["do_predict"].iloc[-1])
        above_below = "ABOVE" if pred > self.ENTRY_THRESHOLD else "BELOW"
        logger.info(
            "PREDICTION %s: pred=%+.4f (%.2f%%), threshold=%.2f%%, %s, close=%.5f, do_predict=%d",
            pair, pred, pred * 100, self.ENTRY_THRESHOLD * 100,
            above_below, close, do_predict,
        )
```

- [ ] **Step 4: Call _log_predictions from populate_entry_trend, before circuit breaker**

In `user_data/strategies/AICryptoStrategy.py`, update `populate_entry_trend` so the call is the **first** thing in the method body (before the circuit breaker check):

```python
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry signal: predicted price change exceeds threshold."""
        # Always log predictions for observability (before any gating)
        self._log_predictions(dataframe, metadata)

        if self._risk_manager.is_circuit_breaker_active():
            logger.warning("Circuit breaker active — no entries allowed")
            dataframe["enter_long"] = 0
            return dataframe

        dataframe.loc[
            (
                (dataframe["&-price_change"] > self.ENTRY_THRESHOLD)
                & (dataframe["do_predict"] == 1)
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1

        return dataframe
```

- [ ] **Step 5: Run all strategy tests to confirm they pass**

```bash
.venv/bin/python -m pytest tests/strategies/test_ai_crypto_strategy.py -v
```

Expected: all tests pass including the 9 new `TestLogPredictions` tests.

- [ ] **Step 6: Commit**

```bash
git add user_data/strategies/AICryptoStrategy.py tests/strategies/test_ai_crypto_strategy.py
git commit -m "feat: add _log_predictions per-candle observability logging"
```

---

## Chunk 2: Report pipeline — parser + generator

**Files:**
- Modify: `scripts/report/log_parser.py`
- Modify: `scripts/report/generator.py`
- Test: `tests/scripts/test_log_parser.py`
- Test: `tests/scripts/test_generator.py`

---

### Task 3: Fix _parse_allocations — update test first, then fix regex

The existing `_parse_allocations` regex matches `base=$..., risk_cap=$...` which never existed in the live log. Fix it to match the real format: `weight=..., atr=..., final=...`.

- [ ] **Step 1: Update the test to use the real log format (makes it fail against current code)**

In `tests/scripts/test_log_parser.py`, update the `SAMPLE_SIGNALS_LOG` constant — replace the two `Allocating` lines:

```python
SAMPLE_SIGNALS_LOG = """\
2026-03-08 22:00:07,650 - AICryptoStrategy - INFO - Allocating BTC/USDT: weight=0.091, atr=0.050, final=$90.91
2026-03-08 22:00:07,651 - freqtrade.freqtradebot - INFO - Long signal found: about create a new trade for BTC/USDT with stake_amount: 90.91 and price: 66939.5 ...
2026-03-08 22:00:08,676 - freqtrade.freqtradebot - INFO - Order dry_run_buy_BTC/USDT_1773007207.65213 was created for BTC/USDT and status is closed.
2026-03-08 22:00:09,733 - AICryptoStrategy - INFO - Allocating ETH/USDT: weight=0.091, atr=0.025, final=$72.73
2026-03-08 22:00:09,735 - freqtrade.freqtradebot - INFO - Long signal found: about create a new trade for ETH/USDT with stake_amount: 72.73 and price: 1948.97 ...
2026-03-08 22:00:10,749 - freqtrade.freqtradebot - INFO - Order dry_run_buy_ETH/USDT_1773007209.736057 was created for ETH/USDT and status is open.
"""
```

Update `test_parse_allocations` to check for `atr` instead of `base`/`risk_cap`:

```python
def test_parse_allocations():
    result = parse_log_content(SAMPLE_SIGNALS_LOG)
    alloc = result["allocations"]
    assert alloc["BTC/USDT"]["weight"] == 0.091
    assert alloc["BTC/USDT"]["atr"] == 0.050
    assert alloc["BTC/USDT"]["final"] == 90.91
    assert alloc["ETH/USDT"]["weight"] == 0.091
    assert alloc["ETH/USDT"]["atr"] == 0.025
    assert alloc["ETH/USDT"]["final"] == 72.73
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
.venv/bin/python -m pytest tests/scripts/test_log_parser.py::test_parse_allocations -v
```

Expected: `FAILED — assert {} == expected` (regex doesn't match new format)

- [ ] **Step 3: Fix _parse_allocations regex in log_parser.py**

In `scripts/report/log_parser.py`, replace the `_parse_allocations` function body:

```python
def _parse_allocations(lines: list[str]) -> dict:
    allocations: dict[str, dict] = {}

    for line in lines:
        m = re.search(
            r"Allocating (\S+/\S+): weight=([\d.]+), atr=([\d.]+), final=\$([\d.]+)",
            line,
        )
        if m:
            allocations[m.group(1)] = {
                "weight": float(m.group(2)),
                "atr": float(m.group(3)),
                "final": float(m.group(4)),
            }

    return allocations
```

- [ ] **Step 4: Run log_parser tests to confirm they pass**

```bash
.venv/bin/python -m pytest tests/scripts/test_log_parser.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 5: Fix the generator to use the new allocation dict keys**

In `scripts/report/generator.py`, replace the Risk & Position Sizing section (lines 149-163):

```python
    # --- Risk & Position Sizing ---
    lines.append("## Risk & Position Sizing")
    if allocations:
        lines.append("| Pair | Weight | ATR% | Final Stake |")
        lines.append("|---|---|---|---|")
        for pair, alloc in sorted(allocations.items()):
            lines.append(
                f"| {pair} | {alloc['weight']:.3f} "
                f"| {alloc['atr'] * 100:.1f}% "
                f"| ${alloc['final']:.2f} |"
            )
    else:
        lines.append("No allocation data in this window.")
    lines.append("")
```

- [ ] **Step 6: Update the sample_log_metrics fixture in test_generator.py**

In `tests/scripts/test_generator.py`, update the `sample_log_metrics` fixture's `allocations` key:

```python
        "allocations": {
            "BTC/USDT": {"weight": 0.091, "atr": 0.050, "final": 90.91},
        },
```

- [ ] **Step 7: Run generator tests to confirm they pass**

```bash
.venv/bin/python -m pytest tests/scripts/test_generator.py -v
```

Expected: all 3 tests pass.

- [ ] **Step 8: Commit**

```bash
git add scripts/report/log_parser.py scripts/report/generator.py \
        tests/scripts/test_log_parser.py tests/scripts/test_generator.py
git commit -m "fix: update _parse_allocations regex to match real log format (weight/atr/final)"
```

---

### Task 4: Add prediction parsing to log_parser.py

Parse `PREDICTION <pair>: pred=...` lines and accumulate per-pair candle stats.

- [ ] **Step 1: Write failing tests for prediction parsing**

Add to `tests/scripts/test_log_parser.py`:

```python
SAMPLE_PREDICTION_LOG = """\
2026-03-11 14:00:01,001 - AICryptoStrategy - INFO - PREDICTION BTC/USDT: pred=+0.0082 (0.82%), threshold=1.00%, BELOW, close=84253.50000, do_predict=1
2026-03-11 14:00:01,002 - AICryptoStrategy - INFO - PREDICTION DOGE/USDT: pred=+0.0143 (1.43%), threshold=1.00%, ABOVE, close=0.09540, do_predict=1
2026-03-11 15:00:01,001 - AICryptoStrategy - INFO - PREDICTION BTC/USDT: pred=+0.0091 (0.91%), threshold=1.00%, BELOW, close=84300.00000, do_predict=1
2026-03-11 15:00:01,002 - AICryptoStrategy - INFO - PREDICTION DOGE/USDT: pred=-0.0021 (-0.21%), threshold=1.00%, BELOW, close=0.09510, do_predict=0
"""


def test_parse_predictions_counts_candles():
    result = parse_log_content(SAMPLE_PREDICTION_LOG)
    preds = result["predictions"]
    assert preds["BTC/USDT"]["candles"] == 2
    assert preds["DOGE/USDT"]["candles"] == 2


def test_parse_predictions_above_below_counts():
    result = parse_log_content(SAMPLE_PREDICTION_LOG)
    preds = result["predictions"]
    assert preds["BTC/USDT"]["above"] == 0
    assert preds["BTC/USDT"]["below"] == 2
    assert preds["DOGE/USDT"]["above"] == 1
    assert preds["DOGE/USDT"]["below"] == 1


def test_parse_predictions_avg_pred_pct():
    result = parse_log_content(SAMPLE_PREDICTION_LOG)
    preds = result["predictions"]
    # BTC: avg of 0.82 and 0.91 = 0.865
    assert abs(preds["BTC/USDT"]["avg_pred_pct"] - 0.865) < 0.01


def test_parse_predictions_last_do_predict():
    result = parse_log_content(SAMPLE_PREDICTION_LOG)
    preds = result["predictions"]
    assert preds["BTC/USDT"]["last_do_predict"] == 1
    assert preds["DOGE/USDT"]["last_do_predict"] == 0


def test_parse_predictions_empty_when_no_lines():
    result = parse_log_content("2026-03-11 14:00:00,000 - freqtrade - INFO - Bot heartbeat\n")
    assert result["predictions"] == {}


def test_predictions_key_present_in_return_dict():
    """parse_log_content must always include predictions and signal_aggregator keys."""
    result = parse_log_content("")
    assert "predictions" in result
    assert "signal_aggregator" in result
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/scripts/test_log_parser.py::test_parse_predictions_counts_candles tests/scripts/test_log_parser.py::test_predictions_key_present_in_return_dict -v
```

Expected: `FAILED — KeyError: 'predictions'`

- [ ] **Step 3: Add _parse_predictions to log_parser.py**

Add after `_parse_allocations`:

```python
def _parse_predictions(lines: list[str]) -> dict:
    """Parse PREDICTION log lines into per-pair candle stats.

    Accumulates a running sum of pred_pct per pair; computes avg at end.
    """
    per_pair: dict[str, dict] = {}
    sum_pred_pct: dict[str, float] = {}

    pattern = re.compile(
        r"PREDICTION (\S+/\S+): pred=[+-][\d.]+ \(([+-][\d.]+)%\), "
        r"threshold=[\d.]+%, (ABOVE|BELOW), close=[\d.]+, do_predict=(\d)"
    )

    for line in lines:
        m = pattern.search(line)
        if not m:
            continue
        pair = m.group(1)
        pred_pct = float(m.group(2))
        above_below = m.group(3)
        do_predict = int(m.group(4))

        if pair not in per_pair:
            per_pair[pair] = {"candles": 0, "above": 0, "below": 0,
                              "avg_pred_pct": 0.0, "last_do_predict": 0}
            sum_pred_pct[pair] = 0.0

        per_pair[pair]["candles"] += 1
        per_pair[pair]["last_do_predict"] = do_predict
        sum_pred_pct[pair] += pred_pct
        if above_below == "ABOVE":
            per_pair[pair]["above"] += 1
        else:
            per_pair[pair]["below"] += 1

    # Compute averages now that all lines are processed
    for pair, stats in per_pair.items():
        if stats["candles"] > 0:
            stats["avg_pred_pct"] = round(sum_pred_pct[pair] / stats["candles"], 3)

    return per_pair
```

- [ ] **Step 4: Update parse_log_content to call _parse_predictions and return new keys**

In `scripts/report/log_parser.py`, update `parse_log_content`:

```python
def parse_log_content(text: str) -> dict:
    """Parse raw log text and return structured metrics dict."""
    lines = text.splitlines()

    training = _parse_training(lines)
    signals = _parse_signals(lines)
    allocations = _parse_allocations(lines)
    health = _parse_health(lines)
    predictions = _parse_predictions(lines)
    signal_aggregator = _parse_signal_aggregator(lines)

    return {
        "training": training,
        "signals": signals,
        "allocations": allocations,
        "health": health,
        "predictions": predictions,
        "signal_aggregator": signal_aggregator,
    }
```

Add a stub `_parse_signal_aggregator` (will be implemented in Task 5):

```python
def _parse_signal_aggregator(lines: list[str]) -> dict:
    return {"approved": 0, "blocked_aggregator": 0,
            "blocked_rate_limit": 0, "blocked_cooldown": 0}
```

- [ ] **Step 5: Run prediction tests to confirm they pass**

```bash
.venv/bin/python -m pytest tests/scripts/test_log_parser.py -v
```

Expected: all tests pass including the 6 new prediction tests.

- [ ] **Step 6: Commit**

```bash
git add scripts/report/log_parser.py tests/scripts/test_log_parser.py
git commit -m "feat: add per-pair prediction parsing to log_parser"
```

---

### Task 5: Add signal_aggregator parsing + Prediction & Signal Summary to report

Complete the `_parse_signal_aggregator` stub and add the new report section to the generator.

- [ ] **Step 1: Write failing tests for signal_aggregator parsing**

Add to `tests/scripts/test_log_parser.py`:

```python
SAMPLE_SIGNAL_AGGREGATOR_LOG = """\
2026-03-11 19:00:02,537 - AICryptoStrategy - INFO - Signal aggregator approved XRP/USDT entry: confidence=0.7500, sources=['freqai_ml']
2026-03-11 19:00:05,760 - AICryptoStrategy - INFO - Signal aggregator blocked SOL/USDT entry: direction=HOLD, confidence=0.4000, sources=['freqai_ml']
2026-03-11 20:00:03,100 - AICryptoStrategy - INFO - Rate limit: 3 entries in last hour >= limit 3, skipping BTC/USDT
2026-03-11 20:00:04,200 - AICryptoStrategy - INFO - Rate limit: 3 entries in last hour >= limit 3, skipping ETH/USDT
2026-03-11 20:01:00,000 - AICryptoStrategy - INFO - Startup cooldown: 3 open trades >= limit 3, skipping AVAX/USDT
"""


def test_parse_signal_aggregator_approved():
    result = parse_log_content(SAMPLE_SIGNAL_AGGREGATOR_LOG)
    agg = result["signal_aggregator"]
    assert agg["approved"] == 1


def test_parse_signal_aggregator_blocked_aggregator():
    result = parse_log_content(SAMPLE_SIGNAL_AGGREGATOR_LOG)
    agg = result["signal_aggregator"]
    assert agg["blocked_aggregator"] == 1


def test_parse_signal_aggregator_blocked_rate_limit():
    result = parse_log_content(SAMPLE_SIGNAL_AGGREGATOR_LOG)
    agg = result["signal_aggregator"]
    assert agg["blocked_rate_limit"] == 2


def test_parse_signal_aggregator_blocked_cooldown():
    result = parse_log_content(SAMPLE_SIGNAL_AGGREGATOR_LOG)
    agg = result["signal_aggregator"]
    assert agg["blocked_cooldown"] == 1


def test_parse_signal_aggregator_zeros_when_no_lines():
    result = parse_log_content("2026-03-11 - INFO - heartbeat\n")
    agg = result["signal_aggregator"]
    assert agg == {"approved": 0, "blocked_aggregator": 0,
                   "blocked_rate_limit": 0, "blocked_cooldown": 0}
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/scripts/test_log_parser.py::test_parse_signal_aggregator_approved -v
```

Expected: `FAILED — assert 0 == 1` (stub always returns zeros)

- [ ] **Step 3: Implement _parse_signal_aggregator**

Replace the stub in `scripts/report/log_parser.py`:

```python
def _parse_signal_aggregator(lines: list[str]) -> dict:
    """Parse signal aggregator approved/blocked and rate-limit/cooldown lines."""
    counts = {
        "approved": 0,
        "blocked_aggregator": 0,
        "blocked_rate_limit": 0,
        "blocked_cooldown": 0,
    }
    for line in lines:
        if re.search(r"Signal aggregator approved \S+/\S+ entry", line):
            counts["approved"] += 1
        elif re.search(r"Signal aggregator blocked \S+/\S+ entry", line):
            counts["blocked_aggregator"] += 1
        elif re.search(r"Rate limit: .* skipping \S+/\S+", line):
            counts["blocked_rate_limit"] += 1
        elif re.search(r"Startup cooldown: .* skipping \S+/\S+", line):
            counts["blocked_cooldown"] += 1
    return counts
```

- [ ] **Step 4: Run all log_parser tests**

```bash
.venv/bin/python -m pytest tests/scripts/test_log_parser.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Write failing generator test for Prediction & Signal Summary section**

Add to `tests/scripts/test_generator.py`:

```python
def test_report_contains_prediction_signal_summary(sample_api_data, sample_log_metrics):
    """Prediction & Signal Summary section appears when predictions data is present."""
    sample_log_metrics["predictions"] = {
        "BTC/USDT": {"candles": 2, "above": 0, "below": 2, "avg_pred_pct": 0.42, "last_do_predict": 1},
        "DOGE/USDT": {"candles": 2, "above": 1, "below": 1, "avg_pred_pct": 1.12, "last_do_predict": 1},
    }
    sample_log_metrics["signal_aggregator"] = {
        "approved": 1, "blocked_aggregator": 0,
        "blocked_rate_limit": 2, "blocked_cooldown": 0,
    }
    report = generate_two_hour_report(
        window_start="20:00", window_end="22:00",
        date_str="2026-03-08",
        api_data=sample_api_data,
        log_metrics=sample_log_metrics,
    )
    assert "Prediction & Signal Summary" in report
    assert "approved=1" in report
    assert "blocked_rate_limit=2" in report
    assert "BTC/USDT" in report
    assert "DOGE/USDT" in report


def test_report_prediction_summary_fallback_when_absent(sample_api_data, sample_log_metrics):
    """Graceful fallback when predictions key is missing (old log snapshots)."""
    # sample_log_metrics has no "predictions" key
    report = generate_two_hour_report(
        window_start="20:00", window_end="22:00",
        date_str="2026-03-08",
        api_data=sample_api_data,
        log_metrics=sample_log_metrics,
    )
    assert "No prediction data in this window" in report


def test_report_risk_sizing_uses_atr_column(sample_api_data, sample_log_metrics):
    """Risk & Position Sizing table must show ATR% column, not Base Stake / Risk Cap."""
    report = generate_two_hour_report(
        window_start="20:00", window_end="22:00",
        date_str="2026-03-08",
        api_data=sample_api_data,
        log_metrics=sample_log_metrics,
    )
    assert "ATR%" in report
    assert "Base Stake" not in report
    assert "Risk Cap" not in report
```

- [ ] **Step 6: Run generator tests to confirm new ones fail**

```bash
.venv/bin/python -m pytest tests/scripts/test_generator.py -v
```

Expected: the 3 new tests fail; the original 3 pass.

- [ ] **Step 7: Add Prediction & Signal Summary section to generator.py**

In `scripts/report/generator.py`, update the function signature and add the new section. After line 21 (`health = log_metrics["health"]`), add:

```python
    predictions = log_metrics.get("predictions", {})
    signal_aggregator = log_metrics.get("signal_aggregator", {})
```

Insert the new section **after** the Per-Pair Signal Activity section (after `lines.append("")` at line 129) and **before** Model Training Summary:

```python
    # --- Prediction & Signal Summary ---
    lines.append("## Prediction & Signal Summary")
    if predictions:
        agg = signal_aggregator
        lines.append(
            f"- Aggregator: approved={agg.get('approved', 0)} "
            f"| blocked_rate_limit={agg.get('blocked_rate_limit', 0)} "
            f"| blocked_aggregator={agg.get('blocked_aggregator', 0)} "
            f"| blocked_cooldown={agg.get('blocked_cooldown', 0)}"
        )
        lines.append("")
        lines.append("| Pair | Candles | Avg Pred% | Above 1.0% | Approved | do_predict |")
        lines.append("|---|---|---|---|---|---|")
        for pair in sorted(predictions.keys()):
            p = predictions[pair]
            # "Approved" per pair: count of approved lines for this pair is not
            # tracked per-pair in signal_aggregator (aggregate only). Show - instead.
            lines.append(
                f"| {pair} | {p['candles']} "
                f"| {p['avg_pred_pct']:+.2f}% "
                f"| {p['above']} "
                f"| - "
                f"| {p['last_do_predict']} |"
            )
    else:
        lines.append("No prediction data in this window.")
    lines.append("")
```

- [ ] **Step 8: Run all generator and log_parser tests**

```bash
.venv/bin/python -m pytest tests/scripts/ -v
```

Expected: all 17 tests pass.

- [ ] **Step 9: Commit**

```bash
git add scripts/report/log_parser.py scripts/report/generator.py \
        tests/scripts/test_log_parser.py tests/scripts/test_generator.py
git commit -m "feat: add signal aggregator parsing and Prediction & Signal Summary to 2h report"
```

---

## Chunk 3: SQLite export — export-db.sh + setup-cron.sh

**Files:**
- Create: `scripts/export-db.sh`
- Modify: `scripts/setup-cron.sh`

No Python tests here — this is a bash script. Verification is manual (run the script and inspect output).

---

### Task 6: Create export-db.sh

- [ ] **Step 1: Create scripts/export-db.sh**

```bash
#!/bin/bash
# Daily SQLite export for AI Crypto Trader.
# Copies tradesv3.dryrun.sqlite from the Docker container to logs/db-exports/,
# named with the current timestamp. Keeps the last 7 files.
#
# Run via cron at 23:55 daily (4 min before daily-report.py at 23:59).
# Usage: ./scripts/export-db.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
EXPORT_DIR="$PROJECT_DIR/logs/db-exports"
CONTAINER="crypto-freqtrade-1"
DB_PATH="/freqtrade/tradesv3.dryrun.sqlite"
KEEP=7

mkdir -p "$EXPORT_DIR"

FILENAME="$(date +%Y-%m-%d_%H-%M).sqlite"
DEST="$EXPORT_DIR/$FILENAME"

if ! docker cp "$CONTAINER:$DB_PATH" "$DEST" 2>> "$PROJECT_DIR/logs/rotation.log"; then
    echo "[$(date)] ERROR: docker cp failed — is $CONTAINER running?" >> "$PROJECT_DIR/logs/rotation.log"
    exit 0
fi

echo "[$(date)] DB exported: $DEST" >> "$PROJECT_DIR/logs/rotation.log"

# Rolling retention: delete oldest file when count exceeds KEEP
# Filename sort is lexicographically chronological (ISO date format)
FILE_COUNT=$(ls -1 "$EXPORT_DIR"/*.sqlite 2>/dev/null | wc -l)
if [ "$FILE_COUNT" -gt "$KEEP" ]; then
    OLDEST=$(ls -1 "$EXPORT_DIR"/*.sqlite | sort | head -1)
    rm "$OLDEST"
    echo "[$(date)] DB export pruned oldest: $OLDEST" >> "$PROJECT_DIR/logs/rotation.log"
fi
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x /Users/brendan/Sites/crypto/scripts/export-db.sh
```

- [ ] **Step 3: Verify the script runs correctly against the live container**

```bash
/Users/brendan/Sites/crypto/scripts/export-db.sh
```

Expected:
- No errors printed to terminal
- `logs/db-exports/YYYY-MM-DD_HH-MM.sqlite` exists
- `logs/rotation.log` contains `DB exported:` line

```bash
ls -la /Users/brendan/Sites/crypto/logs/db-exports/
tail -3 /Users/brendan/Sites/crypto/logs/rotation.log
```

- [ ] **Step 4: Verify rolling deletion by running script 8 times and confirming max 7 files**

```bash
for i in $(seq 1 8); do
    /Users/brendan/Sites/crypto/scripts/export-db.sh
    sleep 61  # ensure unique filenames (minute-resolution)
done
ls /Users/brendan/Sites/crypto/logs/db-exports/ | wc -l
```

Expected output: `7`

> **Note:** If you don't want to wait 8 minutes, manually create 8 dummy `.sqlite` files in `logs/db-exports/` with different timestamps, run the script once, and verify the oldest is gone.

```bash
# Quick verification alternative:
EXPORT_DIR=/Users/brendan/Sites/crypto/logs/db-exports
for i in $(seq 1 8); do touch "$EXPORT_DIR/2026-03-0${i}_00-00.sqlite"; done
/Users/brendan/Sites/crypto/scripts/export-db.sh
ls "$EXPORT_DIR"/*.sqlite | wc -l  # should be 7 (8 dummies + 1 real - 2 deleted = 7)
rm "$EXPORT_DIR"/2026-03-0*.sqlite  # clean up dummies
```

- [ ] **Step 5: Commit**

```bash
git add scripts/export-db.sh
git commit -m "feat: add daily SQLite export script with 7-day rolling retention"
```

---

### Task 7: Update setup-cron.sh

- [ ] **Step 1: Add the DB export cron entry to setup-cron.sh**

In `scripts/setup-cron.sh`, append the following block **after** the existing daily-report block and its re-read (the script already has a re-read at line 24 after the rotate-logs block). Add before the final `echo "Done."`:

```bash
# Re-read after potential update
EXISTING=$(crontab -l 2>/dev/null || true)

DB_EXPORT_ENTRY="55 23 * * * $PROJECT_DIR/scripts/export-db.sh >> $PROJECT_DIR/logs/rotation.log 2>&1"

if echo "$EXISTING" | grep -q "export-db.sh"; then
    echo "DB export cron already installed."
else
    echo "$EXISTING" | { cat; echo "$DB_EXPORT_ENTRY"; } | crontab -
    echo "Installed: SQLite export at 23:55"
fi
```

- [ ] **Step 2: Run setup-cron.sh to install the new entry**

```bash
/Users/brendan/Sites/crypto/scripts/setup-cron.sh
```

Expected output includes: `Installed: SQLite export at 23:55`

- [ ] **Step 3: Verify the crontab has all 3 entries**

```bash
crontab -l
```

Expected output contains all three lines:
```
0 */2 * * * .../scripts/two-hour-report.py ...
59 23 * * * .../scripts/daily-report.py ...
55 23 * * * .../scripts/export-db.sh ...
```

- [ ] **Step 4: Run setup-cron.sh a second time to verify idempotency**

```bash
/Users/brendan/Sites/crypto/scripts/setup-cron.sh
```

Expected output: `DB export cron already installed.` (no duplicate added)

```bash
crontab -l | grep export-db | wc -l  # should be 1
```

- [ ] **Step 5: Commit**

```bash
git add scripts/setup-cron.sh
git commit -m "feat: add SQLite export cron entry to setup-cron.sh"
```

---

## Final Verification

Run the full test suite to confirm nothing is broken:

```bash
.venv/bin/python -m pytest tests/strategies/test_ai_crypto_strategy.py tests/scripts/ -v
```

Expected: all tests pass (9 original strategy + 9 new strategy + 6 original parser + 11 new parser + 3 original generator + 6 new generator = 44 tests).

Restart the bot so the strategy changes take effect:

```bash
docker compose restart
```

Wait for the next candle cycle (~60 seconds after the next hour) and verify the new log line appears:

```bash
docker logs crypto-freqtrade-1 --tail 50 2>&1 | grep PREDICTION
```

Expected: lines like `PREDICTION BTC/USDT: pred=+0.0082 (0.82%), threshold=1.00%, BELOW, close=84253.50000, do_predict=1`
