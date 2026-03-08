# Monitoring

## Telegram Commands

| Command | Description |
|---|---|
| `/start` | Bot status, exchange, strategy info |
| `/status` | Current open trades (empty = no active trades) |
| `/profit` | Cumulative profit/loss (shows data once trades complete) |
| `/balance` | Wallet balance (simulated in dry_run) |
| `/daily` | Daily P&L breakdown |
| `/count` | Open trades vs max allowed |
| `/performance` | Per-pair performance stats |
| `/help` | Full command list |

## Web UI

- **URL**: `http://localhost:8080`
- **Credentials**: username `trader`, password from config (default `change-this-password`)
- **Requires** `listen_ip_address: "0.0.0.0"` in config when running in Docker (not `127.0.0.1`)
- **Requires** `jwt_secret_key` to be 32+ bytes — see [Web UI debugging](../debugging/web-ui.md)

## Reading Logs

### Healthy Indicators

- `Bot heartbeat. PID=1, state='RUNNING'` — bot is alive (every 60 seconds)
- `Starting training BTC/USDT` / `Done training BTC/USDT (20s)` — model training cycle
- `Total time spent training pairlist Ns` — all models trained
- `Total time spent inferencing pairlist Ns` — predictions complete for all pairs
- `dropped N of 1000 prediction data points due to NaNs` — normal if under 20% (101/1000 = 10.1% is typical)
- `Long signal found: about create a new trade for PAIR` — model predicted >0.5% increase, opening trade
- `LIMIT_BUY has been fulfilled for Trade(...)` — dry_run order filled at limit price
- No `ERROR` or `Exception` lines

### Messages You Can Ignore

- `connection rejected (400 Bad Request)` — Web UI WebSocket noise, doesn't affect the bot
- `Notification 'entry_fill' not sent` — this notification type isn't enabled in config (add `"entry_fill": "on"` to `notification_settings` if you want fill confirmations)
- `Found open order for Trade(...)` repeated many times — dry_run waiting for simulated limit order to fill at the limit price, will resolve on its own

### First Run Behavior

On the first candle after training completes, the bot may open all `max_open_trades` (5) simultaneously if the model is bullish on multiple pairs. This is normal — the model evaluates all 11 pairs and picks the best opportunities up to the trade limit.

With the current config, each trade stakes $190 ($1,000 x 0.95 / 5), deploying $950 total. The remaining $50 stays in reserve. See [Risk Management](../reference/risk-management.md) for how loss protection works.

### "No active trades" Is Normal

The bot only enters trades when the ML model predicts >0.5% price increase. In sideways or bearish markets, it may wait hours or even days before finding a signal strong enough to act on.

## Log Rotation

Logs are automatically rotated every 2 hours into daily folders:

```
logs/
  freqtrade.log              ← active log (Freqtrade writes here)
  2026-03-08/
    2026-03-08_18-00_to_20-00.log
    2026-03-08_20-00_to_22-00.log
    ...12 files per day
  reports/
    2026-03-08-daily.md      ← auto-generated daily report
```

### Manual Commands

- **Run rotation now**: `./scripts/rotate-logs.sh`
- **Generate today's report**: `source .venv/bin/activate && python3 scripts/daily-report.py`
- **Generate report for a specific date**: `python3 scripts/daily-report.py --date 2026-03-08`
- **Check cron is running**: `crontab -l`
- **Check rotation history**: `cat logs/rotation.log`

### Daily Reports

Auto-generated at 23:59. Contains:
- Portfolio summary (balance, P&L, win rate)
- Open and closed trades with entry/exit prices
- Per-pair performance
- Model metrics (training time, NaN rate, signal counts)
- Flags (heartbeat gaps, frequent stoploss hits, errors)

Share these reports with Claude to analyze model performance and plan parameter improvements.
