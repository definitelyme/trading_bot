# AI Crypto Trading Bot

AI-powered cryptocurrency trading bot using Freqtrade + FreqAI with XGBoost ML models. The bot downloads market data, engineers technical features, trains a regression model to predict price movements, and executes trades based on ML predictions with built-in risk management.

> **Security Rules**
> - **NEVER** read or modify `.env` directly — it contains real API keys and secrets
> - Use `.env.example` as the reference for what variables exist
> - To add new env vars: update `.env.example` first, then inform the developer to add values to `.env` manually
> - `.env` is gitignored and must stay that way

## Current Status

| Parameter | Value |
|---|---|
| Exchange | Bybit |
| Mode | dry_run (paper trading) |
| Simulated Wallet | $1,000 USDT |
| Model | XGBoostRegressor |
| Timeframe | 1h (with 4h correlation data) |
| Pairs | BTC, ETH, SOL, AVAX, XRP, DOGE, PEPE, SUI, WIF, NEAR, FET (all /USDT) |
| Entry Threshold | >0.5% predicted price increase |

## Quick Links

### Getting Started
- [Prerequisites](getting-started/prerequisites.md) — system requirements
- [Exchange Setup](getting-started/exchange-setup.md) — Bybit API key creation
- [Environment Variables](getting-started/environment-variables.md) — every `.env` variable explained
- [First Run](getting-started/first-run.md) — clone, configure, start

### Reference
- [Architecture](reference/architecture.md) — system design and data flow
- [Strategy](reference/strategy.md) — AICryptoStrategy internals
- [Configuration](reference/configuration.md) — every config field explained
- [Model Training](reference/model-training.md) — FreqAI/XGBoost pipeline
- [Risk Management](reference/risk-management.md) — position sizing and circuit breakers

### Operations
- [Running the Bot](operations/running-the-bot.md) — Docker commands
- [Monitoring](operations/monitoring.md) — Telegram, web UI, logs
- [Adding Pairs](operations/adding-pairs.md) — add/remove trading pairs
- [Going Live](operations/going-live.md) — switch from dry_run to live

### Debugging
- [Docker Issues](debugging/docker-issues.md) — build failures, command errors
- [FreqAI Errors](debugging/freqai-errors.md) — model and training issues
- [Exchange Connectivity](debugging/exchange-connectivity.md) — API and network problems
- [Telegram Setup](debugging/telegram-setup.md) — bot creation and configuration
- [Web UI](debugging/web-ui.md) — login, JWT, connection issues

### Model Safety
- [Valid Reasons to Delete Models](valid-reasons-to-delete-any-model.md) — **read before changing features, config, or model type**

### Design
- [Original Design](plans/2026-03-07-ai-crypto-trading-design.md)
- [Implementation Plan](plans/2026-03-07-ai-crypto-trading-implementation.md)
- [Documentation Structure](plans/2026-03-08-documentation-structure-design.md)
- [VPS Deployment & CI/CD Design](superpowers/specs/2026-03-14-vps-deployment-cicd-design.md)
