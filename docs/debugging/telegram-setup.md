# Telegram Setup

## Creating the Bot

1. Open Telegram, search for **@BotFather**
2. Send `/newbot`
3. Follow the prompts (choose a name and username)
4. Save the token (format: `1234567890:AAxxxxxxxxx`)

## Getting Your Chat ID

1. Search for **@RawDataBot** on Telegram (NOT @userinfobot — that one doesn't work reliably)
2. Send it any message
3. It replies with your chat info including `"id": 1234567890`
4. That number is your `TELEGRAM_CHAT_ID`

## Empty Token Crash

**Symptom**: Bot crashes on startup with `Telegram InvalidToken` error.

**Cause**: `telegram.enabled: true` in config but token/chat_id are empty strings, AND the `FREQTRADE__TELEGRAM__` env vars are not set.

**Fix**: Set these env vars in `.env`:
- `FREQTRADE__TELEGRAM__TOKEN=your_token_here`
- `FREQTRADE__TELEGRAM__CHAT_ID=your_chat_id_here`

**Alternative**: Set `telegram.enabled: false` in config to disable Telegram entirely.

## The FREQTRADE__ Pattern for Telegram

Config has empty `token` and `chat_id` fields:

```json
"telegram": {
    "enabled": true,
    "token": "",
    "chat_id": ""
}
```

Env vars inject real values at runtime:
- `FREQTRADE__TELEGRAM__TOKEN` → overrides `telegram.token`
- `FREQTRADE__TELEGRAM__CHAT_ID` → overrides `telegram.chat_id`

This keeps secrets out of config files that might be committed to git.
