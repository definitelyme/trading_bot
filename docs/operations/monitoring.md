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
- No `ERROR` or `Exception` lines

### "No active trades" Is Normal

The bot only enters trades when the ML model predicts >0.5% price increase. In sideways or bearish markets, it may wait hours or even days before finding a signal strong enough to act on.
