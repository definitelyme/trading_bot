#!/bin/bash
# One-time setup for logging, reports, and cron jobs.
# Run once: ./scripts/setup.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python3"

echo "=== AI Crypto Trader — Setup ==="
echo ""

# 1. Create directories
echo "[1/4] Creating directories..."
mkdir -p "$PROJECT_DIR/logs/reports"
echo "  ✓ logs/ and logs/reports/"

# 2. Rebuild and restart Docker
echo ""
echo "[2/4] Rebuilding and restarting Docker..."
cd "$PROJECT_DIR"
docker compose down
docker compose up --build -d
echo "  ✓ Container rebuilt and started"

# Wait for bot to initialize
echo ""
echo -n "  Waiting for bot to start "
for i in $(seq 1 30); do
    echo -n "."
    sleep 1
done
echo " done"

# Verify bot is running
if docker compose ps --format '{{.Status}}' | grep -q "Up"; then
    echo "  ✓ Container is running"
else
    echo "  ✗ Container failed to start. Check: docker compose logs --tail 20"
    exit 1
fi

# Verify log file
if [ -s "$PROJECT_DIR/logs/freqtrade.log" ]; then
    echo "  ✓ Log file exists and has content"
else
    echo "  ⚠ Log file empty or missing (may need more time to populate)"
fi

# 3. Install cron jobs
echo ""
echo "[3/4] Installing cron jobs..."

ROTATE_ENTRY="0 */2 * * * $VENV_PYTHON $PROJECT_DIR/scripts/two-hour-report.py >> $PROJECT_DIR/logs/rotation.log 2>&1"
REPORT_ENTRY="59 23 * * * $VENV_PYTHON $PROJECT_DIR/scripts/daily-report.py >> $PROJECT_DIR/logs/rotation.log 2>&1"

EXISTING=$(crontab -l 2>/dev/null || true)

if echo "$EXISTING" | grep -q "two-hour-report.py"; then
    echo "  ✓ Log rotation cron already installed"
else
    echo "$EXISTING" | { cat; echo "$ROTATE_ENTRY"; } | crontab -
    echo "  ✓ Installed: log rotation every 2 hours"
fi

EXISTING=$(crontab -l 2>/dev/null || true)

if echo "$EXISTING" | grep -q "daily-report.py"; then
    echo "  ✓ Daily report cron already installed"
else
    echo "$EXISTING" | { cat; echo "$REPORT_ENTRY"; } | crontab -
    echo "  ✓ Installed: daily report at 23:59"
fi

# 4. Summary
sleep 2
echo ""
echo "[4/4] Verification..."
echo ""
echo "  Docker:"
docker compose ps --format '  {{.Name}}: {{.Status}}'
echo ""
echo "  Cron jobs:"
crontab -l 2>/dev/null | grep -E "(two-hour-report|daily-report)" | while read -r line; do
    echo "  $line"
done
echo ""
echo "  Log file:"
ls -lh "$PROJECT_DIR/logs/freqtrade.log" 2>/dev/null | awk '{print "  "$5, $9}' || echo "  (not yet created)"

echo ""
echo "=== Setup complete ==="
echo ""
echo "What happens now:"
echo "  • Freqtrade writes to logs/freqtrade.log"
echo "  • Every 2 hours: log rotated + analytical report saved to logs/YYYY-MM-DD/"
echo "  • At 23:59 daily: performance report saved to logs/reports/"
echo ""
echo "Manual commands:"
echo "  • Generate report now:  source .venv/bin/activate && python3 scripts/daily-report.py"
echo "  • Rotate + report now:  source .venv/bin/activate && python3 scripts/two-hour-report.py"
echo "  • Check bot logs:       docker compose logs --tail 20"
