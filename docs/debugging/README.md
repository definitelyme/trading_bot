# Debugging

## How to Get Logs

```bash
docker compose logs --tail 100    # last 100 lines
docker compose logs -f             # follow live
```

## General Approach

1. Check logs for the error line
2. Find the specific error message
3. Look it up in the relevant guide below

## Guides

- [Docker Issues](docker-issues.md) — build failures, command errors, missing packages
- [FreqAI Errors](freqai-errors.md) — model training and prediction issues
- [Exchange Connectivity](exchange-connectivity.md) — API and network problems
- [Telegram Setup](telegram-setup.md) — bot creation, tokens, notifications
- [Web UI](web-ui.md) — login, JWT, connection issues
