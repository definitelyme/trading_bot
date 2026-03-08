# Logging, Reports & Model Improvement Design

**Date**: 2026-03-08
**Status**: Approved
**Goal**: Structured log rotation, automated daily performance reports, and a workflow for iteratively improving the ML model.

## Security Principles

- Scripts authenticate to the Freqtrade API using credentials from config.json (not `.env`)
- Log files are gitignored — they may contain trade data and timestamps
- No secrets are written to log files or reports

## 1. Log Rotation

### Architecture

Freqtrade writes to a log file via `--logfile`. A cron job rotates it every 2 hours using the copytruncate pattern.

### Directory Structure

```
logs/
  2026-03-08/
    freqtrade.log                    ← active log (truncated every 2h)
    2026-03-08_18-00_to_20-00.log   ← rotated snapshot
    2026-03-08_20-00_to_22-00.log
    ...12 files per day...
  2026-03-09/
    freqtrade.log
    ...
  reports/
    2026-03-08-daily.md
    2026-03-09-daily.md
```

### Changes Required

- **docker-compose.yml**: Add `--logfile user_data/logs/freqtrade.log` to command, add volume mount `./logs:/freqtrade/user_data/logs`
- **.gitignore**: Add `logs/`
- **scripts/rotate-logs.sh**: Rotation script
  1. Create today's date folder if missing
  2. Copy `logs/YYYY-MM-DD/freqtrade.log` to `logs/YYYY-MM-DD/YYYY-MM-DD_HH-00_to_HH+2-00.log`
  3. Truncate `freqtrade.log` to zero bytes
  4. Check for heartbeat gaps (>5 min silence = potential sleep/crash warning)
- **Cron entry**: `0 */2 * * * /path/to/scripts/rotate-logs.sh`

### Why Copytruncate

Freqtrade holds an open file handle to the log file. Moving the file would cause Freqtrade to keep writing to the old (now moved) file. Copytruncate copies first, then truncates in place — Freqtrade continues writing without interruption, no restart needed.

## 2. Daily Performance Report

### Script: `scripts/daily-report.py`

Runs at 23:59 via cron. Queries two data sources:

1. **Freqtrade REST API** (localhost:8080) — trade data, profit, balance, per-pair performance
2. **Today's rotated log files** — training metrics, prediction counts, errors

### API Endpoints Used

| Endpoint | Data |
|---|---|
| `GET /api/v1/profit` | Cumulative profit, trade count, win rate |
| `GET /api/v1/trades` | Individual trade details (entry, exit, P&L, duration) |
| `GET /api/v1/performance` | Per-pair performance stats |
| `GET /api/v1/balance` | Current wallet balance |
| `GET /api/v1/status` | Open trades |

### Report Format

Output: `logs/reports/YYYY-MM-DD-daily.md`

```markdown
# Daily Report — YYYY-MM-DD

## Portfolio Summary
- Starting balance: $X
- Current balance: $X
- Day P&L: $X (X%)
- Open trades: N | Closed trades: N

## Trade Activity
| Pair | Direction | Entry Price | Exit Price | P&L % | P&L $ | Duration | Exit Reason |
|---|---|---|---|---|---|---|---|

## Per-Pair Performance (cumulative)
| Pair | Total Trades | Wins | Losses | Win Rate | Avg Profit | Total P&L |
|---|---|---|---|---|---|---|

## Model Metrics (from logs)
- Training time: Xs (N pairs)
- Retrains today: N
- NaN drop rate: X%
- Pairs with entry signals: N/11
- Stoploss hits: N
- Trailing stop exits: N
- ROI exits: N
- ML signal exits: N

## Flags
- [auto-generated warnings: all trades same candle, stoploss hit, circuit breaker, gaps detected]
```

### Authentication

The script uses the `username` and `password` from `config.json` to get a JWT token from the API, then uses that token for all subsequent requests.

## 3. Sleep Prevention (macOS — temporary until VPS)

- System Settings → Battery → Options → "Prevent automatic sleeping when the display is off" → ON
- Display can dim/lock/screensaver — Docker keeps running
- Only system sleep pauses Docker
- The rotation script detects gaps (no heartbeat for >5 min) and flags them in the report

## 4. Model Improvement Workflow

### Daily Cycle

1. Daily report auto-generates at 23:59
2. Share report with Claude in a new conversation
3. Analyze: win rate, profit by pair, stoploss frequency, prediction accuracy
4. Decide if parameter changes are warranted
5. If yes — update config/strategy, rebuild container, model retrains

### Tuning Guide

| Metric | Threshold | Action |
|---|---|---|
| Win rate < 40% after 1 week | Entry threshold too low | Raise from 0.5% to 0.75% or 1% |
| Specific pair always losing | Pair not suited to model | Remove from pair_whitelist |
| Stoploss hit frequently | Stoploss too tight or entries too late | Widen stoploss or adjust trailing params |
| Model accuracy drops after retrain | Training data or features degrading | Adjust train_period_days, check features |
| Small but consistent profits | Exiting too early | Lower minimal_roi targets to hold longer |
| High NaN drop rate (>30%) | Insufficient training data | Increase train_period_days |

### Key Principle

Change ONE parameter at a time. Run for 2-3 days minimum. Compare daily reports before vs after. Never change multiple things simultaneously — you won't know what helped or hurt.

## Implementation Notes

- Two scripts: `scripts/rotate-logs.sh` (bash), `scripts/daily-report.py` (Python)
- Both run via cron on the host machine (not inside Docker)
- `daily-report.py` needs `requests` pip package (install in project venv)
- Log files and reports are gitignored
- The report script should handle the case where the bot is down (API unreachable) gracefully
- On VPS migration: same scripts work, just update cron paths
