# Analytics & Logging Enhancement — Design Spec
Date: 2026-03-11
Status: Approved

## Problem

After 2 days of live trading, three gaps exist in the observability pipeline:

1. **Per-candle predictions are invisible** — the model predicts price changes for all 11 pairs every hour, but only pairs that cross the 1.0% threshold appear in logs. There is no record of what BTC/ETH/SOL predicted, so you cannot tell if the model is silently underperforming vs. accurately predicting low movement.

2. **Signal pass/fail is untracked** — "Signal aggregator approved/blocked" lines appear in raw logs but are not aggregated into any report. You cannot see at a glance how many signals passed/failed and why (rate limit vs. aggregator decision vs. cooldown).

3. **No historical trade database** — the SQLite file containing all trades lives inside the Docker container and is never exported. If the container is recreated, all trade history is lost. There is no rolling backup.

## Approach

Extend the existing cron pipeline (Option 1 of three evaluated). No new infrastructure; three targeted additions:

| Addition | Where | When |
|---|---|---|
| Per-candle prediction logging | `AICryptoStrategy.py` | Every candle (live, in-strategy) |
| Signal pass/fail section | `scripts/report/log_parser.py` + `generator.py` | Every 2h (parsed from rotated log) |
| Daily SQLite export | New `scripts/export-db.sh` + cron at 23:55 | Daily (7-day rolling) |

---

## Section 1: Per-Candle Prediction Logging

### Location
`user_data/strategies/AICryptoStrategy.py` → `populate_entry_trend`

### Change
Add a call to a new private method `_log_predictions(dataframe, metadata)` at the end of `populate_entry_trend`, after the signal logic. This method reads the last row of the dataframe and emits one structured log line per candle cycle.

### Log format
```
PREDICTION BTC/USDT: pred=+0.0082 (0.82%), threshold=1.00%, BELOW, close=84253.50, do_predict=1
PREDICTION DOGE/USDT: pred=+0.0143 (1.43%), threshold=1.00%, ABOVE, close=0.09540, do_predict=1
```

### Fields
| Field | Source | Purpose |
|---|---|---|
| `pred` | `dataframe["&-price_change"].iloc[-1]` | Raw model output |
| `%` | pred × 100 | Human-readable |
| `threshold` | Hardcoded `0.010` (same as signal logic) | Visible in logs for auditing |
| `ABOVE/BELOW` | pred > 0.010 | Whether this candle would signal |
| `close` | `dataframe["close"].iloc[-1]` | Sanity check on model inputs |
| `do_predict` | `dataframe["do_predict"].iloc[-1]` | FreqAI data-quality flag |

### Guard conditions
- Skip if `"&-price_change"` not in dataframe columns (model not yet trained)
- Skip if `"do_predict"` not in dataframe columns
- Skip if dataframe is empty or last row has NaN prediction

### Volume
11 lines per candle cycle × 24 cycles/day = 264 lines/day. Negligible.

---

## Section 2: Signal Pass/Fail Parsing + 2h Report Section

### Location A — Parser
`scripts/report/log_parser.py`

Three new regex patterns added to the existing parsing loop:

| Pattern | Example log line | Field updated |
|---|---|---|
| `PREDICTION <pair>: pred=([+-]\d+\.\d+) \(([+-]\d+\.\d+)%\), threshold=[\d.]+%, (ABOVE\|BELOW), close=([\d.]+), do_predict=(\d)` | `PREDICTION BTC/USDT: pred=...` | `metrics["predictions"][pair]` |
| `Signal aggregator approved (\S+) entry` | `Signal aggregator approved WIF/USDT entry: confidence=0.7500` | `metrics["signal_aggregator"]["approved"]` |
| `Signal aggregator blocked (\S+) entry` | `Signal aggregator blocked XRP/USDT entry: direction=HOLD` | `metrics["signal_aggregator"]["blocked_aggregator"]` |
| `Rate limit: .* skipping (\S+)` | `Rate limit: 3 entries in last hour >= limit 3, skipping BTC/USDT` | `metrics["signal_aggregator"]["blocked_rate_limit"]` |
| `Startup cooldown: .* skipping (\S+)` | `Startup cooldown: 3 open trades >= limit 3, skipping ETH/USDT` | `metrics["signal_aggregator"]["blocked_cooldown"]` |

New metrics dict structure:
```python
"predictions": {
    "BTC/USDT":  {"candles": int, "above": int, "below": int,
                  "avg_pred_pct": float, "last_do_predict": int},
    ...  # one entry per pair that appears in logs
},
"signal_aggregator": {
    "approved": int,
    "blocked_aggregator": int,
    "blocked_rate_limit": int,
    "blocked_cooldown": int,
}
```

### Location B — Generator
`scripts/report/generator.py`

New section **"Prediction & Signal Summary"** inserted between "Per-Pair Signal Activity" and "Model Training Summary":

```markdown
## Prediction & Signal Summary
- Aggregator: approved=1 | blocked_rate_limit=2 | blocked_aggregator=0 | blocked_cooldown=0

| Pair       | Candles | Avg Pred% | Above 1.0% | Approved | do_predict |
|------------|---------|-----------|------------|----------|------------|
| BTC/USDT   | 2       | +0.42%    | 0          | 0        | 1          |
| DOGE/USDT  | 2       | +1.12%    | 1          | 1        | 1          |
| WIF/USDT   | 2       | +1.51%    | 2          | 1        | 1          |
```

### Backward compatibility
If `"predictions"` key is absent from `log_metrics` (old log snapshots without PREDICTION lines), the section renders as `No prediction data in this window.` — no crash.

---

## Section 3: Daily SQLite Export

### Location
New file: `scripts/export-db.sh`
Updated file: `scripts/setup-cron.sh`

### Export script logic
```
1. EXPORT_DIR=$PROJECT_DIR/logs/db-exports
2. mkdir -p $EXPORT_DIR
3. FILENAME=YYYY-MM-DD_HH-MM.sqlite  (date at script run time)
4. docker cp crypto-freqtrade-1:/freqtrade/tradesv3.dryrun.sqlite $EXPORT_DIR/$FILENAME
5. Count files in $EXPORT_DIR matching *.sqlite
6. If count > 7: delete oldest file (sort by filename, head -1, rm)
7. Log result to $PROJECT_DIR/logs/rotation.log
```

### Output directory
```
logs/db-exports/
  2026-03-11_23-55.sqlite
  2026-03-12_23-55.sqlite
  ...  (7 files max)
```

### Cron schedule
`55 23 * * *` — 4 minutes before `daily-report.py` (23:59)

### setup-cron.sh addition
New idempotent block following the existing pattern:
```bash
EXPORT_ENTRY="55 23 * * * $PROJECT_DIR/scripts/export-db.sh >> $PROJECT_DIR/logs/rotation.log 2>&1"
if echo "$EXISTING" | grep -q "export-db.sh"; then
    echo "DB export cron already installed."
else
    echo "$EXISTING" | { cat; echo "$EXPORT_ENTRY"; } | crontab -
    echo "Installed: SQLite export at 23:55"
fi
```

### Error handling
- If `docker cp` fails (container stopped): script logs error to `rotation.log` and exits 0 (cron does not spam)
- If `db-exports/` has < 7 files: deletion step is skipped

---

## Files Changed

| File | Change type |
|---|---|
| `user_data/strategies/AICryptoStrategy.py` | Add `_log_predictions()` method + call in `populate_entry_trend` |
| `scripts/report/log_parser.py` | Add 5 new regex patterns + 2 new metrics dict keys |
| `scripts/report/generator.py` | Add "Prediction & Signal Summary" section |
| `scripts/export-db.sh` | New file |
| `scripts/setup-cron.sh` | Add DB export cron entry block |

---

## Out of Scope

- No changes to `daily-report.py` (daily report already summarises from 2h reports via API)
- No new cron jobs beyond the DB export
- No SQLite schema changes or custom tables
- No Fear & Greed / News Sentiment integration
- No dashboard or visualisation layer
