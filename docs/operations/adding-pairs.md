# Adding Pairs

## How to Add a Pair

1. Edit `pair_whitelist` in `config.json`
2. Restart the container: `docker compose down && docker compose up -d`

## Pair Format Rules

- Format: `BASE/QUOTE` where QUOTE must match `stake_currency` (USDT)
- `SOL/USDT` works
- `SOL/USDC` does NOT work (different quote currency)

## No Model Deletion Needed

FreqAI automatically trains models for new pairs. Existing pair models remain valid. You do NOT need to delete `user_data/models/` when adding new pairs.

## Current Pairs (11)

BTC, ETH, SOL, AVAX, XRP, DOGE, PEPE, SUI, WIF, NEAR, FET — all /USDT

## Volatile Pair Recommendations

For more active trading, consider these high-volatility pairs:

- **Meme coins**: DOGE, PEPE, WIF, SHIB — highest volatility, most trade opportunities
- **AI/narrative tokens**: FET, NEAR — trend-driven moves
- **Newer L1s**: SUI — active price discovery

## Training Time Impact

Each new pair adds ~20-25 seconds to training. 11 pairs ≈ 4-5 minutes total.

## Max Open Trades

Currently set to 5. Adding more pairs doesn't mean more simultaneous trades — the bot picks the best opportunities up to this limit.
