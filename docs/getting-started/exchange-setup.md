# Exchange Setup

## Supported Exchanges

**Bybit** is the primary and tested exchange for this bot.

### Regional Restrictions

- **Binance** — banned in Nigeria (DNS blocked at ISP level, API inaccessible)
- **OKX** — has exited the Nigerian market
- **Bybit** — works fully from Nigeria

## Creating Bybit API Keys

1. Log into [Bybit](https://www.bybit.com/) → Account & Security → API Management → Create New Key
2. Select **System-generated API Keys**
3. Set a name (e.g., `freqtrade-bot`)
4. Set permissions:
   - **Read-Write** access
   - **Unified Trading Account**
   - **Spot Trade** enabled
5. IP restriction: optional but recommended for production
6. Save the API key and secret immediately — the secret is shown only once

## Security Best Practices

- **Never enable withdrawal permissions** — the bot only needs read-write + trade
- Consider IP restrictions for live trading
- Store keys only in `.env` (never in config files or code)

## Testing the Connection

Create a virtual environment and test with ccxt:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install ccxt
```

```python
import ccxt
exchange = ccxt.bybit({"apiKey": "YOUR_KEY", "secret": "YOUR_SECRET"})
print(exchange.fetch_balance())
```

If you see your balance output, the connection is working.
