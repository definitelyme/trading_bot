# Exchange Connectivity

## Binance Blocked in Nigeria

**Symptom**: DNS resolution failure, `NetworkError`, connection timeout when using Binance.

**Cause**: Binance is banned by Nigerian regulators. DNS is blocked at ISP level.

**Fix**: Use Bybit instead — fully functional from Nigeria.

**Also affected**: OKX has exited the Nigerian market. Coinbase has limited functionality.

---

## DNS Resolution Failure for api.bybit.com

**Symptom**: `socket.gaierror: [Errno -3] Temporary failure in name resolution`

**Cause**: Temporary network issue, ISP DNS problems.

**Fix**: Wait and retry. Check general internet connectivity. Try alternative DNS (8.8.8.8).

---

## "externally-managed-environment" pip Error

**Symptom**: `pip install ccxt` fails with `"externally-managed-environment"`.

**Cause**: Homebrew Python on macOS blocks system-wide pip installs.

**Fix**: Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install ccxt
```

---

## Bybit API Test Script

Quick test to verify your API keys work:

```python
import ccxt

exchange = ccxt.bybit({
    "apiKey": "YOUR_KEY",
    "secret": "YOUR_SECRET"
})
print(exchange.fetch_balance())
```

If you see balance output, the connection and credentials are working.
