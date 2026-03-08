# AI Crypto Trading System — Design Document

**Date:** 2026-03-07
**Status:** Approved
**Author:** Brainstorming session

---

## Overview

An AI-powered crypto trading system that automates trading across four major exchanges using a continuously learning ML ensemble. The system operates in three validated phases — Backtest, Dry Run, and Live — and scales from local development to cloud deployment. Capital preservation is the default posture; calculated high-confidence trades unlock larger positions dynamically.

---

## Goals

- Automate crypto trading across Binance, Bybit, OKX, and Coinbase Advanced
- Continuously learn and improve from each trade (reduce error rate over time)
- Factor in technical, sentiment, on-chain, and news signals simultaneously
- Protect capital by default; take large risks only when signals strongly converge
- Allow full observation in Demo (Dry Run) mode before committing real capital

---

## Architecture

Four layers with clear responsibilities:

```
┌─────────────────────────────────────────────────────┐
│                  DASHBOARD / ALERTS                  │
│         Freqtrade Web UI + Telegram Bot              │
└───────────────────────┬─────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────┐
│                 EXECUTION LAYER                      │
│   Freqtrade Core — order management, live trading,  │
│   paper trading, backtesting engine (CCXT)          │
│   Exchanges: Binance · Bybit · OKX · Coinbase       │
└───────────────────────┬─────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────┐
│              BRAIN / STRATEGY LAYER                  │
│   FreqAI — continuous ML retraining loop             │
│   Models: XGBoost + LSTM ensemble                    │
│   Strategies: trend, mean reversion, sentiment,      │
│               arbitrage signal detection             │
│   Risk Manager: Half-Kelly + ATR stops +             │
│                 drawdown circuit breaker             │
└───────────────────────┬─────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────┐
│                   DATA LAYER                         │
│   Market Data: CCXT (OHLCV, order book, funding)    │
│   Sentiment: LunarCrush API + Santiment API          │
│   On-Chain: Glassnode (BTC/ETH macro signals)       │
│   News/NLP: FinBERT pipeline on crypto news feeds   │
└─────────────────────────────────────────────────────┘
```

---

## Operational Modes

| Mode | Description | Capital at Risk |
|---|---|---|
| **Backtest** | Strategy runs against 2+ years of historical data | None |
| **Dry Run (Demo)** | Live market data, simulated trades, fake capital | None |
| **Live** | Real orders on exchange via CCXT | Yes |

**Progression:** Backtest → Dry Run (min 6 weeks) → Live parallel (min 4 weeks) → Scale up

Telegram alerts are labelled `[DRY RUN]` or `[LIVE]` at all times to prevent confusion.

---

## Components

### 1. Freqtrade Core
Orchestrates the full trade lifecycle. Manages WebSocket reconnects, partial fills, exchange errors, and position tracking. One instance per exchange (4 total), coordinated via shared config.

### 2. FreqAI Retraining Loop
Background thread that retrains the ML model on a rolling data window every 4 hours during live trading. This is the "learn on the job" engine — the mechanism by which error rate reduces over time.

### 3. Strategy Modules

| Strategy | Signal Source | Timeframe |
|---|---|---|
| Trend Following | EMA crossover + MACD + RSI via FreqAI | 1h, 4h |
| Mean Reversion | Bollinger Bands + ATR + Z-score | 15m, 1h |
| Sentiment-Driven | LunarCrush score + FinBERT news NLP | 1h, 4h |
| Arbitrage Detection | Cross-exchange price delta via CCXT | 1m, 5m |

Each strategy emits: `{ direction: BUY/SELL/HOLD, confidence: 0.0–1.0, strategy: "<name>" }`

### 4. Signal Aggregator
Combines signals from all strategy modules into a single weighted confidence score. Only passes to execution when the combined score exceeds the minimum threshold (default: 0.65). Discards low-confidence signals and waits for the next candle.

### 5. Risk Manager (hard-coded rules, never ML-overridden)
- **Position size:** Half-Kelly × ATR-adjusted volatility factor
- **Hard cap:** 5% of portfolio per trade (2% cap during first 3 months live)
- **Stop-loss:** ATR-based trailing stop, set at order entry, never removed
- **Circuit breaker:** Halts all trading on threshold breach, fires Telegram alert

### 6. Data Collector
Background service that fetches and caches:
- OHLCV candles + order book + funding rates (CCXT, per exchange per pair)
- LunarCrush sentiment scores (hourly)
- Santiment on-chain signals (daily)
- Glassnode BTC/ETH macro metrics (daily)
- Crypto news headlines → FinBERT NLP pipeline → sentiment score (0–1)

### 7. Telegram Bot + Web Dashboard
Real-time visibility into trades, model confidence, positions, P&L, and system health. Supports remote commands: pause trading, force-close position, adjust risk parameters.

---

## Data Flow

```
Every candle tick (e.g. every 5 minutes):

1. DATA COLLECTOR
   ├── Fetches latest OHLCV from all 4 exchanges (CCXT)
   ├── Fetches LunarCrush sentiment score for active pairs
   ├── Fetches latest news headlines → FinBERT NLP → score
   └── Writes to local time-series store (Parquet files)

2. FEATURE ENGINEERING
   ├── Technical indicators: EMA, MACD, RSI, ATR, Bollinger
   ├── Order flow: funding rate, open interest (Binance/Bybit)
   ├── Sentiment: social score + news NLP score (normalised 0–1)
   └── On-chain: Glassnode BTC exchange inflow/outflow (daily update)

3. FREQAI MODEL
   ├── XGBoost: predicts price direction probability
   ├── LSTM: predicts next N candle sequence pattern
   └── Ensemble: weighted average → single confidence score (0.0–1.0)

4. STRATEGY MODULES
   └── Each strategy evaluates its own signal conditions and emits signal

5. SIGNAL AGGREGATOR
   ├── Collects signals from all active strategies
   ├── Applies minimum confidence threshold (0.65 default)
   └── Passes to Risk Manager if threshold met; discards otherwise

6. RISK MANAGER
   ├── Calculates position size (Half-Kelly × ATR-adjusted)
   ├── Sets stop-loss price (ATR-based)
   ├── Checks circuit breaker status
   └── Sends order to Execution Layer if all clear

7. EXECUTION LAYER (Freqtrade)
   ├── [BACKTEST] → simulate against historical data
   ├── [DRY RUN]  → simulate with live data, no real order
   └── [LIVE]     → place real order on exchange via CCXT

8. FREQAI RETRAINING (background, every 4h)
   └── Retrains XGBoost + LSTM on rolling recent data window
```

---

## Risk Management

### Position Sizing
- Base formula: Half-Kelly (f/2) using signal confidence
- Volatility adjustment: position size inversely proportional to ATR
- Hard cap: 5% portfolio per trade (2% during first 3 months live)
- Zero leverage during Backtest, Dry Run, and first 3 months Live
- Maximum leverage ever: 2x, only after proven track record

### Circuit Breakers (halt all trading + Telegram alert)
- Single trade loss > 3% of portfolio
- Total drawdown > 10% in any rolling 24h window
- Total drawdown > 20% in any rolling 7-day window
- Exchange API error rate exceeds threshold
- Model confidence average drops below floor

### Error Handling

| Scenario | Response |
|---|---|
| Exchange API down | Exponential backoff retry, hold open positions, alert |
| WebSocket disconnect | Auto-reconnect, no orders during reconnect window |
| Model retraining fails | Continue with last good model, log, alert |
| Order rejected | Log reason, skip trade, do not retry blindly |
| Sentiment API down | Fall back to technical-only signals, tighten threshold |
| Circuit breaker fires | All trading halts, alert sent, manual restart required |
| VPS down (live) | Docker auto-restart; stops already set on exchange |

---

## Testing & Validation

### Backtesting Requirements (before Dry Run)
- Minimum 2 years of historical data
- Walk-forward validation (70% train / 30% test)
- Realistic fees per exchange (e.g. 0.1% taker on Binance)
- Slippage simulation enabled
- Tested across bull + bear + sideways market periods
- Sharpe Ratio > 1.0
- Maximum drawdown < 20%
- Win rate > 52%
- Zero look-ahead bias (strict timestamp validation)

### Dry Run Graduation Criteria (before Live)
- Minimum 6 consecutive weeks
- Positive P&L
- Win rate within ±5% of backtest results
- Circuit breaker fired < 3 times total
- No single simulated trade would have lost > 3% of portfolio
- Performance held across at least 2 different market conditions

### Live Parallel Validation (before scaling capital)
- Run Dry Run + Live simultaneously for minimum 4 weeks
- Live P&L tracks Dry Run P&L within acceptable variance
- No execution errors or unexpected order behaviour
- Only after this: gradually scale up capital

### Ongoing Model Health Monitoring
- Daily: log model confidence score distribution
- Weekly: compare live win rate vs expected win rate
- Monthly: full walk-forward revalidation on fresh data
- Full retrain trigger: win rate drops > 10% from baseline, or drawdown exceeds warning threshold

---

## Infrastructure

### Local Development Phase
- Run Freqtrade locally (macOS/Linux)
- Parquet files for local data storage
- All 3 modes available locally (backtest, dry run, live)

### Cloud Deployment Phase (when ready for Live)
- Docker-compose deployment to VPS
- Exchange co-location: AWS Tokyo (Binance/Bybit), AWS Frankfurt (OKX)
- Separate research machine from live trading VPS
- Secrets management: environment variables, never in code
- API keys: withdrawal-disabled + IP whitelisted on all exchanges
- Systemd / Docker restart policy for auto-recovery

---

## Tech Stack

| Component | Technology |
|---|---|
| Bot Framework | Freqtrade + FreqAI |
| Exchange Connectivity | CCXT (Python) |
| ML Models | XGBoost, LightGBM, LSTM (PyTorch) |
| RL Position Sizing | Stable Baselines3 (PPO) — future phase |
| Sentiment Data | LunarCrush API, Santiment API |
| News NLP | FinBERT (HuggingFace Transformers) |
| On-Chain Data | Glassnode API |
| Data Storage | Parquet files (local), S3 (cloud) |
| Alerting | Telegram Bot API |
| Dashboard | Freqtrade Web UI |
| Language | Python 3.11+ |
| Containerisation | Docker + Docker Compose |
| Cloud | AWS EC2 (VPS phase) |

---

## Key References

- [Freqtrade Documentation](https://www.freqtrade.io/en/stable/)
- [FreqAI Documentation](https://www.freqtrade.io/en/stable/freqai/)
- [CCXT GitHub](https://github.com/ccxt/ccxt)
- [LunarCrush API](https://lunarcrush.com/developers/api/endpoints)
- [Santiment API](https://academy.santiment.net/sanapi/)
- [Glassnode API](https://docs.glassnode.com/)
- [FinBERT (HuggingFace)](https://huggingface.co/ProsusAI/finbert)
- [Stable Baselines3](https://stable-baselines3.readthedocs.io/)
