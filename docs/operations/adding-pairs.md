# Adding Pairs

## The One File to Edit

All trading pairs are defined in a single file:

```
user_data/config.pairs.json
```

This is the **only place** you need to change when adding or removing pairs. Both dry-run and live configs load this file automatically.

## How to Add a Pair

1. Open `user_data/config.pairs.json`
2. Add the pair to `pair_whitelist`
3. Restart the container: `docker compose down && docker compose up -d`

## How to Remove a Pair

Delete the pair's line from `config.pairs.json` and restart.

## Pair Format Rules

- Format: `BASE/QUOTE` where QUOTE must match `stake_currency` (USDT)
- `SOL/USDT` works
- `SOL/USDC` does NOT work (different quote currency)

## No Model Deletion Needed

FreqAI automatically trains models for new pairs. Existing pair models remain valid. You do NOT need to delete `user_data/models/` when adding new pairs.

> **Exception**: If you change feature engineering (indicators, timeframes, targets), delete models and retrain from scratch.

## Current Pairs (16)

**Original 11:**
BTC, ETH, SOL, AVAX, XRP, DOGE, PEPE, SUI, WIF, NEAR, FET — all /USDT

**Added March 2026 (top 2026 YTD performers on Bybit):**
- **HYPE/USDT** — Hyperliquid DEX L1, +35–78% YTD, $296M/day volume
- **ZRO/USDT** — LayerZero (+72% YTD), institutional-grade L1 backed by Citadel/ARK
- **MORPHO/USDT** — DeFi lending protocol (+46% YTD), Apollo Global partnership
- **XMR/USDT** — Monero privacy coin (ATH Jan 2026), $82M/day on Bybit
- **KITE/USDT** — AI payment blockchain (+165% YTD, note: only ~4 months of data)

## Pair Selection Guidelines

For more active trading, prioritise pairs with:
- **High volume** — reduces slippage, more reliable signals
- **Clear narrative/catalyst** — model learns trend patterns better
- **6+ months of history on Bybit** — gives FreqAI enough training data

| Category | Examples | Notes |
|----------|---------|-------|
| Meme coins | DOGE, PEPE, WIF | Highest volatility, most trade opportunities |
| AI/narrative | FET, NEAR, KITE | Trend-driven moves |
| DeFi | MORPHO | Institutional catalyst-driven |
| DEX/infra | HYPE, ZRO | High volume, strong narrative |
| Privacy | XMR | Macro-driven, high volume |
| Newer L1s | SUI | Active price discovery |

## Training Time Impact

Each new pair adds ~20–25 seconds to training.

| Pairs | Approx. training time |
|-------|-----------------------|
| 11 (original) | ~4–5 min |
| 16 (current)  | ~6–7 min |

## Max Open Trades

Currently set to 5. Adding more pairs doesn't mean more simultaneous trades — the bot picks the best opportunities up to this limit.
