# Environment Variables

All configuration secrets are stored in `.env` (never committed to git). Use `.env.example` as a reference for what variables exist.

## Variable Reference

| Variable | Required | Description |
|---|---|---|
| `BYBIT_API_KEY` | Yes | Bybit API key from [exchange setup](exchange-setup.md) |
| `BYBIT_SECRET` | Yes | Bybit API secret |
| `BINANCE_API_KEY` | No | Not used (Binance blocked in Nigeria) |
| `BINANCE_SECRET` | No | Not used |
| `OKX_API_KEY` | No | Not used (OKX exited Nigeria) |
| `OKX_SECRET` | No | Not used |
| `OKX_PASSPHRASE` | No | Not used |
| `COINBASE_API_KEY` | No | Not used |
| `COINBASE_SECRET` | No | Not used |
| `LUNARCRUSH_API_KEY` | No | For sentiment data (future use) |
| `SANTIMENT_API_KEY` | No | For sentiment data (future use) |
| `GLASSNODE_API_KEY` | No | For on-chain data (future use) |
| `TELEGRAM_TOKEN` | Yes | Telegram bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Yes | Your Telegram chat ID from @RawDataBot |
| `TRADING_MODE` | Yes | `dry_run` or `live` |
| `MAX_PORTFOLIO_PCT_PER_TRADE` | Yes | Max % of portfolio per trade (default `0.05`) |
| `CIRCUIT_BREAKER_24H_DRAWDOWN` | Yes | 24h drawdown limit before circuit breaker (default `0.10`) |
| `CIRCUIT_BREAKER_7D_DRAWDOWN` | Yes | 7d drawdown limit before circuit breaker (default `0.20`) |
| `MIN_SIGNAL_CONFIDENCE` | Yes | Minimum confidence to enter a trade (default `0.65`) |
| `FREQTRADE__EXCHANGE__KEY` | Yes | Same as BYBIT_API_KEY — Freqtrade override format |
| `FREQTRADE__EXCHANGE__SECRET` | Yes | Same as BYBIT_SECRET — Freqtrade override format |
| `FREQTRADE__TELEGRAM__TOKEN` | Yes | Same as TELEGRAM_TOKEN — Freqtrade override format |
| `FREQTRADE__TELEGRAM__CHAT_ID` | Yes | Same as TELEGRAM_CHAT_ID — Freqtrade override format |

## The FREQTRADE__ Override System

Freqtrade supports environment variable overrides using the pattern:

```
FREQTRADE__<SECTION>__<KEY>
```

This maps to `config.json → section → key`. For example:

- `FREQTRADE__EXCHANGE__KEY=abc` overrides `config.json → exchange → key` with `abc`
- `FREQTRADE__TELEGRAM__TOKEN=xyz` overrides `config.json → telegram → token` with `xyz`

Double underscore `__` separates nesting levels.

This lets you keep secrets out of config files entirely. Config files have empty strings as placeholders, and env vars inject the real values at runtime. This is why you'll see empty `"key": ""` and `"secret": ""` fields in `config.json` — they're filled by the `FREQTRADE__` env vars when the bot starts.
