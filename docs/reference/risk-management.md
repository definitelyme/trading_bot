# Risk Management

## RiskManager

**File**: `user_data/strategies/risk/risk_manager.py`

### Position Sizing — Half-Kelly

```
f* = (confidence - (1 - confidence)) * 0.5
```

- Adjusted for ATR volatility: reduces size in high-volatility conditions
- Capped at max 5% of portfolio per trade (`MAX_PORTFOLIO_PCT_PER_TRADE`)
- Returns 0 if confidence is below `MIN_SIGNAL_CONFIDENCE` (0.65)

### Circuit Breakers

| Breaker | Threshold | Env Variable |
|---|---|---|
| 24h drawdown | 10% | `CIRCUIT_BREAKER_24H_DRAWDOWN` |
| 7d drawdown | 20% | `CIRCUIT_BREAKER_7D_DRAWDOWN` |

When triggered:
- All entries blocked
- Position sizes forced to 0
- Manual reset required via `reset_circuit_breaker()`

## SignalAggregator

**File**: `user_data/strategies/signals/signal_aggregator.py`

Combines BUY/SELL/HOLD signals from multiple strategy modules:

- Conflicting signals (both BUY and SELL present) → **HOLD**
- Below confidence threshold → **HOLD**
- Returns aggregated direction + average confidence

## Future Data Clients

These are implemented but not yet integrated into the live pipeline:

| Client | File | Signal |
|---|---|---|
| LunarCrushClient | `data_clients/lunarcrush_client.py` | Galaxy Score sentiment (0-1) |
| GlassnodeClient | `data_clients/glassnode_client.py` | Exchange inflow signal (high inflow = bearish) |
| NewsNLPClient | `data_clients/news_nlp_client.py` | FinBERT headline sentiment analysis |
