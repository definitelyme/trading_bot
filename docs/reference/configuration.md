# Configuration

Two config files exist: `config.json` (dry-run) and `config.live.json` (live trading).

## Key Differences

| Setting | config.json | config.live.json |
|---|---|---|
| `dry_run` | `true` | `false` |
| `dry_run_wallet` | `1000` | `0` |
| `listen_ip_address` | `0.0.0.0` | `127.0.0.1` |

## Field Reference

### Trading

| Field | Value | Description |
|---|---|---|
| `trading_mode` | `spot` | Spot trading (not futures) |
| `max_open_trades` | `5` | Maximum simultaneous trades |
| `stake_currency` | `USDT` | Quote currency for all pairs |
| `stake_amount` | `unlimited` | FreqAI manages sizing |
| `tradable_balance_ratio` | `0.95` | Fraction of wallet available for trading (5% reserve) |

### Exchange

| Field | Value | Description |
|---|---|---|
| `name` | `bybit` | Exchange identifier |
| `key` | `""` (empty) | Injected via `FREQTRADE__EXCHANGE__KEY` |
| `secret` | `""` (empty) | Injected via `FREQTRADE__EXCHANGE__SECRET` |
| `pair_whitelist` | 11 pairs | BTC, ETH, SOL, AVAX, XRP, DOGE, PEPE, SUI, WIF, NEAR, FET (all /USDT) |
| `pair_blacklist` | leveraged tokens | `*UP/USDT`, `*DOWN/USDT`, `*BEAR/USDT`, `*BULL/USDT` |

### Pairlists

| Field | Value | Description |
|---|---|---|
| `method` | `StaticPairList` | Uses the whitelist as-is |

### FreqAI

| Field | Value | Description |
|---|---|---|
| `enabled` | `true` | FreqAI active |
| `freqaimodel` | `XGBoostRegressor` | ML model type |
| `purge_old_models` | `2` | Keep last 2 model versions |
| `train_period_days` | `30` | Training window |
| `backtest_period_days` | `7` | Backtest evaluation window |
| `live_retrain_hours` | `4` | Retrain every 4 hours |
| `identifier` | `ai_crypto_v1` | Model directory name |
| `indicator_periods_candles` | `[10, 20, 50]` | Periods for expanded indicators |
| `label_period_candles` | `24` | Prediction horizon (24 candles = 24h) |
| `DI_threshold` | `0.9` | Dissimilarity Index cutoff |
| `n_estimators` | `800` | XGBoost trees |
| `learning_rate` | `0.02` | XGBoost learning rate |
| `max_depth` | `8` | XGBoost tree depth |

### Pricing

| Field | Value | Description |
|---|---|---|
| `entry_pricing.price_side` | `same` | Use order book |
| `entry_pricing.order_book_top` | `1` | Best bid/ask |
| `exit_pricing.price_side` | `same` | Use order book |
| `exit_pricing.order_book_top` | `1` | Best bid/ask |

### Risk

| Field | Value | Description |
|---|---|---|
| `stoploss` | `-0.05` | -5% stop loss (max ~$9.50 loss per $190 trade) |
| `trailing_stop` | `true` | Trailing stop enabled |
| `trailing_stop_positive` | `0.01` | Trail 1% behind peak price |
| `trailing_stop_positive_offset` | `0.02` | Activate trailing stop after +2% profit |
| `trailing_only_offset_is_reached` | `true` | Don't trail until offset is reached |
| `minimal_roi` | time-based | +10% at 0min, +5% at 2h, +2% at 4h, +1% at 8h |

See [Risk Management](../reference/risk-management.md) for a full explanation of how these protect against losses.

### Telegram

| Field | Value | Description |
|---|---|---|
| `enabled` | `true` | Telegram notifications active |
| `token` | `""` (empty) | Injected via `FREQTRADE__TELEGRAM__TOKEN` |
| `chat_id` | `""` (empty) | Injected via `FREQTRADE__TELEGRAM__CHAT_ID` |

### API Server

| Field | Value | Description |
|---|---|---|
| `enabled` | `true` | Web UI active |
| `listen_ip_address` | `0.0.0.0` | Accept connections from outside container |
| `listen_port` | `8080` | Web UI port |
| `jwt_secret_key` | (set in config) | Must be 32+ bytes for SHA256 |
| `username` | `trader` | Web UI login |
| `password` | (set in config) | Web UI password |

### Bot

| Field | Value | Description |
|---|---|---|
| `bot_name` | `AI Crypto Trader` | Display name |
| `initial_state` | `running` | Start trading immediately |
| `force_entry_enable` | `true` | Allow manual force entries |
| `process_throttle_secs` | `5` | Seconds between processing cycles |

## Env Var Override Note

Fields with empty strings (`""`) in config are placeholders. The `FREQTRADE__` environment variables inject real values at runtime. See [Environment Variables](../getting-started/environment-variables.md) for the full override system.
