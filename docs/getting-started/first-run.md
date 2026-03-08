# First Run

## Steps

1. **Clone the repo**
   ```bash
   git clone <repo-url>
   cd crypto
   ```

2. **Create your `.env` file**
   ```bash
   cp .env.example .env
   ```

3. **Fill in required values** in `.env`:
   - `BYBIT_API_KEY` and `BYBIT_SECRET` — from [Exchange Setup](exchange-setup.md)
   - `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID` — from [Telegram Setup](../debugging/telegram-setup.md)
   - `FREQTRADE__EXCHANGE__KEY` — same value as `BYBIT_API_KEY`
   - `FREQTRADE__EXCHANGE__SECRET` — same value as `BYBIT_SECRET`
   - `FREQTRADE__TELEGRAM__TOKEN` — same value as `TELEGRAM_TOKEN`
   - `FREQTRADE__TELEGRAM__CHAT_ID` — same value as `TELEGRAM_CHAT_ID`

4. **Start the bot**
   ```bash
   docker compose up --build -d
   ```

5. **Check logs**
   ```bash
   docker compose logs --tail 50
   ```

6. **Look for training output:**
   - `Starting training BTC/USDT` → model training has begun
   - `Done training BTC/USDT (20s)` → model completed for that pair
   - This repeats for each of the 11 pairs (~4-5 minutes total)

7. **Verify via Telegram:** Send `/start` to your bot
   - Expected: bot responds with status, exchange, and pairs info

8. **Check balance:** Send `/balance` to confirm the simulated $1,000 wallet
