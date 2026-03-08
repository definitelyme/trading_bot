# Dynamic Pair Allocation Design

**Date:** 2026-03-08
**Status:** Approved

## Problem

The bot has 11 whitelisted pairs but `max_open_trades: 5` limits it to 5 simultaneous positions. With `stake_amount: "unlimited"`, Freqtrade allocates equally (~$190/trade from $1000). This wastes opportunity on the other 6 pairs and treats all pairs the same regardless of performance.

## Goal

Enable trading all 11 pairs simultaneously with performance-weighted capital allocation. Better-performing pairs get more capital. The system must work at $200 (live start) through $1000+ (scaled live).

## Approach

Use Freqtrade's `custom_stake_amount()` hook with a new PairAllocator module that computes profit-factor weights from the Trade DB. Layer the existing RiskManager (Half-Kelly + ATR) as a per-trade volatility cap.

## Architecture

### New Module: PairAllocator

**File:** `user_data/strategies/risk/pair_allocator.py`

Computes and caches per-pair capital allocation weights.

**Weight calculation flow:**

1. Fetch closed trades from rolling window (default 30 days) per pair
2. For each pair with >= `min_trades` (default 5):
   - `profit_factor = gross_wins / gross_losses` (clamped to `pf_cap`, default 5.0)
   - If `profit_factor < pf_threshold` (default 0.7): pair gets zero performance allocation
3. Pairs with < `min_trades` in window: moved to exploration pool
4. Split capital: 90% performance pool, 10% exploration pool (configurable)
5. Performance pool: weighted by profit_factor (normalized to sum to 0.9)
6. Exploration pool: equal split among exploration-eligible pairs
7. Apply min_stake floor (default $10) — skip pairs below it, redistribute upward

**Caching:** Weights cached with timestamp. Refreshed every 4 hours (aligned with FreqAI retrain cycle).

**Cold start:** When all pairs lack sufficient trade history, 100% goes to exploration pool (equal allocation), capped by RiskManager.

### Strategy Integration: custom_stake_amount()

Added to `AICryptoStrategy`. Called by Freqtrade before each trade entry.

```
available_balance = wallets.get_free('USDT')
weight = pair_allocator.get_weight(pair)
base_stake = available_balance * weight
risk_cap = risk_manager.calculate_position_size(portfolio_value, confidence, atr_pct)
final_stake = min(base_stake, risk_cap)
→ return 0 if final_stake < min_stake (exchange minimum)
```

### RiskManager (existing, now wired in)

The existing `calculate_position_size()` serves as a per-trade volatility cap:
- Half-Kelly fraction based on model confidence
- ATR scaling reduces position size in volatile conditions
- Max portfolio % cap (5% per trade)
- Circuit breaker blocks all entries on excessive drawdown

### Helper Methods

- `_get_current_atr_pct(pair)`: Reads latest ATR from dataframe, divides by price
- `_get_model_confidence(pair)`: Reads latest `&-price_change` prediction magnitude

## Configuration

All configurable via environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `PAIR_ALLOC_WINDOW_DAYS` | 30 | Rolling window for profit factor calculation |
| `PAIR_ALLOC_MIN_TRADES` | 5 | Minimum trades before trusting profit factor |
| `PAIR_ALLOC_EXPLORATION_PCT` | 0.10 | Fraction of capital reserved for exploration |
| `PAIR_ALLOC_PF_THRESHOLD` | 0.7 | Profit factor below which pair gets zero performance allocation |
| `PAIR_ALLOC_PF_CAP` | 5.0 | Cap on profit factor to prevent outlier domination |
| `PAIR_ALLOC_MIN_STAKE` | 10.0 | Minimum stake in USDT; below this, skip the pair |
| `PAIR_ALLOC_REFRESH_HOURS` | 4 | How often to recalculate weights |

### Config file change

`user_data/config.json`: `max_open_trades` changed from 5 to 11.

## Edge Cases

| Scenario | Behavior |
|---|---|
| All pairs in cold start (fresh bot) | 100% exploration pool, equal allocation, RiskManager caps |
| Only 1 pair has history | Gets 90% performance pool; others split 10% exploration |
| Pair PF drops below threshold | Loses performance allocation at next 4h refresh; may qualify for exploration if few recent trades |
| Wallet too small for any trades | All pairs return 0; Freqtrade logs insufficient funds |
| Single pair dominates (PF=5.0) | PF cap prevents >~50% of performance pool |
| Circuit breaker trips | RiskManager returns 0 for all pairs; entry trend also blocks |
| Carry-forward | Capital from skipped pairs (below min_stake) redistributed to viable pairs |

## Scaling Behavior

The system self-adjusts to capital level:
- **$200**: ~6-8 pairs active (smallest pairs auto-skipped by min_stake floor)
- **$500**: most pairs active
- **$1000+**: all 11 pairs comfortably active

## Logging

- Weight recalculations: pairs with weights, exploration count
- Skipped pairs: pair name, calculated allocation, min_stake
- Cold-start fallback: pair, model confidence, trade count vs minimum
- Profit factor details: per-pair PF, window, trade count

## Files Changed

- **New:** `user_data/strategies/risk/pair_allocator.py`
- **Modified:** `user_data/strategies/AICryptoStrategy.py` — add `custom_stake_amount()`, helpers, PairAllocator instantiation
- **Modified:** `user_data/config.json` — `max_open_trades: 11`
- **Modified:** `.env.example` — new env vars

## Live Deployment Strategy

1. Run dry run with all 11 pairs to collect data and validate weighting
2. Start live with $200 and 5 pairs (existing `config.live.json`)
3. After 2-4 weeks of live data, expand to 11 pairs
4. System self-adjusts: at $200, naturally trades fewer pairs via min_stake floor
