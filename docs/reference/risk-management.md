# Risk Management

## How Loss Protection Works

You will **never lose your entire stake** on a single trade. Multiple layers of protection limit losses:

### Layer 1: Stoploss (-5%)

If a trade drops 5% from entry price, it's automatically sold. On a $190 trade, the **maximum loss is ~$9.50**, not $190. Example: BTC entry at $67,050 → stoploss triggers at ~$63,698 → sells automatically.

### Layer 2: Trailing Stop

Once a trade gains +2% profit, a trailing stop activates at 1% below the peak price. If BTC goes up 3% then starts falling, it auto-sells when it drops 1% from the peak — locking in most of the profit.

| Parameter | Value | Meaning |
|---|---|---|
| `trailing_stop` | `true` | Trailing stop enabled |
| `trailing_stop_positive` | `0.01` | Trail 1% behind peak |
| `trailing_stop_positive_offset` | `0.02` | Only activate after +2% profit |
| `trailing_only_offset_is_reached` | `true` | Don't trail until offset hit |

### Layer 3: Minimal ROI (Time-Based Profit Taking)

Auto-sells at decreasing profit targets as time passes:

| Time | Sell if profit reaches |
|---|---|
| Immediately | +10% |
| After 2 hours | +5% |
| After 4 hours | +2% |
| After 8 hours | +1% |

### Layer 4: ML Exit Signal

The model triggers exits when it predicts price will drop (`&-price_change < 0`), which can exit before stoploss is hit.

### Worst-Case Scenario

With 5 trades at $190 each and -5% stoploss:
- **Worst case per trade**: $190 x 5% = $9.50 loss
- **Worst case all 5 trades**: 5 x $9.50 = **$47.50** (4.75% of $1,000 wallet)
- **Circuit breaker kicks in** at 10% portfolio drawdown ($100), blocking all new trades

### How Stake Per Trade Is Calculated

```
stake_per_trade = wallet × tradable_balance_ratio ÷ max_open_trades
                = $1,000 × 0.95 ÷ 5
                = $190 per trade
```

This means $950 is deployed across 5 trades, with $50 held in reserve.

---

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
