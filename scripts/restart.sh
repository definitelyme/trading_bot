#!/bin/bash
# Graceful restart for the AI Crypto Trader bot.
#
# Checks for open trades before restarting. Waits up to 4 hours for them to
# close. Sends Telegram notifications throughout.
#
# Usage:
#   ./scripts/restart.sh                  — wait for trades to close (default)
#   ./scripts/restart.sh --force          — skip trade check, restart immediately
#   ./scripts/restart.sh --rebuild        — rebuild Docker image before restart
#   ./scripts/restart.sh --force --rebuild — skip trade check + rebuild image
#
# Environment (optional, set by deploy.yml):
#   ACTIONS_URL — GitHub Actions workflow URL included in abort Telegram message
#
# Requirements: run as a user in the 'docker' group; .env present in project root.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FORCE=false
REBUILD=false

# ── Constants ────────────────────────────────────────────────────────────────
TIMEOUT_SECONDS=14400   # 4 hours
POLL_INTERVAL=300       # 5 minutes between trade checks
HOURLY_INTERVAL=3600    # 60 minutes between "still waiting" Telegram messages
API_URL="http://localhost:8080/api/v1"
CURL_OPTS=(--max-time 10 --connect-timeout 5 -s)

# ── Argument parsing ─────────────────────────────────────────────────────────
for arg in "$@"; do
  case $arg in
    --force)   FORCE=true ;;
    --rebuild) REBUILD=true ;;
  esac
done

# ── Read credentials from .env ───────────────────────────────────────────────
# Use cut -d= -f2- (not -f2) to preserve = characters in values (e.g. base64 tokens).
read_env() {
  grep -m1 "^${1}=" "$PROJECT_DIR/.env" 2>/dev/null | cut -d= -f2- || true
}

API_USER=$(read_env FREQTRADE__API_SERVER__USERNAME)
API_PASS=$(read_env FREQTRADE__API_SERVER__PASSWORD)
TG_TOKEN=$(read_env FREQTRADE__TELEGRAM__TOKEN)
TG_CHAT=$(read_env FREQTRADE__TELEGRAM__CHAT_ID)

# ── Telegram helper ──────────────────────────────────────────────────────────
# Uses --data-urlencode to handle emojis and newlines safely.
# Falls back silently if credentials are missing (|| true prevents set -e exit).
send_telegram() {
  local msg="$1"
  if [ -n "$TG_TOKEN" ] && [ -n "$TG_CHAT" ]; then
    curl -s -X POST "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" \
      --data-urlencode "chat_id=${TG_CHAT}" \
      --data-urlencode "text=${msg}" > /dev/null || true
  fi
}

echo "=== AI Crypto Trader — Restart ==="
cd "$PROJECT_DIR"

# ── Trade check (skipped with --force) ───────────────────────────────────────
if [ "$FORCE" = true ]; then
  echo "[FORCED] Skipping open-trade check"
  send_telegram "⚡ Force deploy triggered — skipping trade check"
else
  # Preflight: check credentials are present before entering the polling loop
  if [ -z "$API_USER" ] || [ -z "$API_PASS" ]; then
    echo "WARN: FREQTRADE__API_SERVER__USERNAME or __PASSWORD not set in .env — skipping trade check"
    send_telegram "⚠️ API credentials not set in .env — assuming no open trades, deploying now"
  else
    start_time=$(date +%s)
    last_notified=$start_time
    deadline=$((start_time + TIMEOUT_SECONDS))
    first_message_sent=false

    while true; do
      now=$(date +%s)

      # curl exits 0 even on HTTP errors; we capture the code via -w.
      # On connection failure, curl exits non-zero — the || echo "000" catches that.
      HTTP_CODE=$(curl "${CURL_OPTS[@]}" \
        -o /tmp/ft_status.json \
        -w "%{http_code}" \
        -u "${API_USER}:${API_PASS}" \
        "${API_URL}/status" 2>/dev/null || echo "000")

      if [ "$HTTP_CODE" = "401" ]; then
        echo "WARN: API auth failed (HTTP 401) — check FREQTRADE__API_SERVER__USERNAME/PASSWORD in .env"
        send_telegram "⚠️ API auth failed (wrong credentials?) — assuming no open trades, deploying now"
        break
      elif [ "$HTTP_CODE" != "200" ]; then
        echo "WARN: API unreachable (HTTP ${HTTP_CODE}) — assuming no open trades, deploying now"
        send_telegram "⚠️ API unreachable — assuming no open trades, deploying now"
        break
      fi

      # GET /api/v1/status returns a JSON array of open trade objects.
      # isinstance guard + exception handler treats unexpected shapes as "no trades".
      trade_count=$(python3 -c "
import json
try:
    data = json.load(open('/tmp/ft_status.json'))
    print(len(data) if isinstance(data, list) else 0)
except Exception:
    print(0)
" 2>/dev/null || echo "0")

      # IMPORTANT: do NOT use `[ ... ] && break` here — under set -e, a false [ ]
      # exits with code 1 and aborts the entire script. Always use if/then/fi.
      if [ "$trade_count" = "0" ]; then break; fi

      # Send first notification the moment trades are detected
      if [ "$first_message_sent" = false ]; then
        send_telegram "🕐 Deploy queued: ${trade_count} open trade(s). Checking every 5 min (timeout: 4h)"
        first_message_sent=true
      elif [ $((now - last_notified)) -ge $HOURLY_INTERVAL ]; then
        elapsed_h=$(( (now - start_time) / 3600 ))
        send_telegram "⏳ Still waiting: ${trade_count} trade(s) open, ${elapsed_h}h elapsed"
        last_notified=$now
      fi

      # Check deadline BEFORE sleeping so we don't overshoot by a full poll interval
      if [ "$now" -ge "$deadline" ]; then
        abort_msg="🚫 Deploy aborted: ${trade_count} trade(s) still open after 4h."
        if [ -n "${ACTIONS_URL:-}" ]; then
          abort_msg="${abort_msg} Force-deploy: ${ACTIONS_URL}"
        fi
        send_telegram "$abort_msg"
        echo "Deploy aborted: ${trade_count} trade(s) still open after 4h timeout"
        exit 1
      fi

      sleep "$POLL_INTERVAL"
    done
  fi
fi

# ── Pre-restart: export DB snapshot ─────────────────────────────────────────
# Non-fatal: || { } prevents set -euo pipefail from exiting on export failure.
echo ""
echo "[1/2] Exporting DB snapshot before restart..."
"$PROJECT_DIR/scripts/export-db.sh" || {
  echo "WARN: DB export failed — continuing restart"
  send_telegram "⚠️ DB export failed before restart — continuing anyway"
}

# ── Docker restart ────────────────────────────────────────────────────────────
echo ""
echo "[2/2] Restarting container..."

docker compose down
# Wait for Telegram's long-poll session to expire server-side.
# Without this, the new container starts before the old one's getUpdates
# request is released, causing Conflict errors in the first ~30s of startup.
sleep 15

if [ "$REBUILD" = true ]; then
  echo "  Rebuilding image and starting container..."
  docker compose up --build -d
  echo "  ✓ Image rebuilt and container started"
else
  echo "  Starting container..."
  docker compose up -d
  echo "  ✓ Container started"
fi

echo ""
echo "Status:"
docker compose ps --format '  {{.Name}}: {{.Status}}'

exit 0
