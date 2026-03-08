# Going Live

## Pre-Flight Checklist

1. Run dry_run for at least 1 week
2. Review simulated trades via `/profit` and `/performance`
3. Verify the model is profitable on paper
4. Ensure Telegram notifications are working
5. Test that web UI is accessible

## Switching to Live

### Option A: Use config.live.json

1. `config.live.json` already has `dry_run: false`
2. Update `docker-compose.live.yml`:
   - Add `--freqaimodel XGBoostRegressor` to the command
   - Remove the `freqtrade` prefix from the command (Docker entrypoint handles it)
3. Start: `docker compose -f docker-compose.live.yml up -d`

### Option B: Environment Variable Override

Set `FREQTRADE__DRY_RUN=false` in `.env` — this overrides `config.json` without needing a separate config file.

## Security Hardening Before Going Live

- **Change `jwt_secret_key`** to a random 64-char hex string:
  ```bash
  python3 -c "import secrets; print(secrets.token_hex(32))"
  ```
- **Change `password`** to something strong
- **Set `listen_ip_address`** to `127.0.0.1` in live config (restrict web UI to local access only)
- **Consider Bybit API key IP restriction** — lock API access to your server's IP
- **Verify withdrawal permissions are DISABLED** on your API key

## Start Small

Use a small `tradable_balance_ratio` (e.g., `0.10`) at first to risk only 10% of your balance. Increase gradually as you gain confidence in the bot's performance.
