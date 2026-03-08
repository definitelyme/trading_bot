# Architecture

## System Overview

```
Bybit Exchange API
     ↓ (OHLCV candle data)
Freqtrade Data Provider
     ↓ (historical + live data)
FreqAI Pipeline
     ↓ (feature engineering → XGBoost training/prediction)
AICryptoStrategy
     ↓ (entry/exit signals)
Trade Execution (dry_run or live)
     ↓ (notifications)
Telegram Bot + Web UI
```

## Key Components

| Component | File | Role |
|---|---|---|
| AICryptoStrategy | `user_data/strategies/AICryptoStrategy.py` | Main strategy — feature engineering, entry/exit logic |
| RiskManager | `user_data/strategies/risk/risk_manager.py` | Position sizing (half-Kelly) + circuit breakers |
| SignalAggregator | `user_data/strategies/signals/signal_aggregator.py` | Combines signals from multiple sources |
| LunarCrushClient | `user_data/strategies/data_clients/lunarcrush_client.py` | Sentiment data (future) |
| GlassnodeClient | `user_data/strategies/data_clients/glassnode_client.py` | On-chain data (future) |
| NewsNLPClient | `user_data/strategies/data_clients/news_nlp_client.py` | FinBERT NLP sentiment (future) |

## Import Hack

Freqtrade loads strategies as standalone files, not Python packages. Relative imports (`from .risk import ...`) don't work. The strategy uses a `sys.path` hack at the top of the file:

```python
strategies_dir = str(Path(__file__).parent)
sys.path.insert(0, strategies_dir)
```

This allows importing sub-modules like `risk/` and `signals/` using absolute imports.

## Docker Architecture

- **Base image**: `freqtradeorg/freqtrade:stable`
- **Added pip packages**: xgboost, lightgbm, torch, transformers, httpx, datasieve
- **Volume mounts**: `./user_data:/freqtrade/user_data` (live sync), `./.env:/freqtrade/.env`
- **Port**: 8080 for web UI
- **Note**: `datasieve` is required by FreqAI but not included in the base image
