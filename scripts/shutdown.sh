#!/bin/bash
# Shut down the AI Crypto Trader: stop Docker, remove cron jobs, rotate final logs.
# Run: ./scripts/shutdown.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python3"

echo "=== AI Crypto Trader — Shutdown ==="
echo ""

# 1. Generate a final 2-hour report before shutting down
echo "[1/4] Generating final report..."
if [ -s "$PROJECT_DIR/logs/freqtrade.log" ]; then
    "$VENV_PYTHON" "$PROJECT_DIR/scripts/two-hour-report.py" 2>&1 && \
        echo "  ✓ Final report saved" || \
        echo "  ⚠ Report generation failed (continuing shutdown)"
else
    echo "  - Log empty, skipping final report"
fi

# 2. Stop Docker
echo ""
echo "[2/4] Stopping Docker..."
cd "$PROJECT_DIR"
if docker compose ps --format '{{.Status}}' 2>/dev/null | grep -q "Up"; then
    docker compose down
    echo "  ✓ Container stopped and removed"
else
    echo "  - No running container found"
fi

# 3. Remove cron jobs
echo ""
echo "[3/4] Removing cron jobs..."
EXISTING=$(crontab -l 2>/dev/null || true)

if [ -n "$EXISTING" ]; then
    CLEANED=$(echo "$EXISTING" | grep -v "two-hour-report.py" | grep -v "daily-report.py" || true)
    if [ "$CLEANED" != "$EXISTING" ]; then
        if [ -z "$CLEANED" ]; then
            crontab -r 2>/dev/null || true
        else
            echo "$CLEANED" | crontab -
        fi
        echo "  ✓ Cron jobs removed"
    else
        echo "  - No matching cron jobs found"
    fi
else
    echo "  - No crontab installed"
fi

# 4. Summary
echo ""
echo "[4/4] Verification..."
echo ""
echo "  Docker:"
if docker compose ps --format '  {{.Name}}: {{.Status}}' 2>/dev/null | grep -q .; then
    docker compose ps --format '  {{.Name}}: {{.Status}}'
else
    echo "  (no containers)"
fi
echo ""
echo "  Cron jobs:"
REMAINING=$(crontab -l 2>/dev/null | grep -E "(two-hour-report|daily-report)" || true)
if [ -n "$REMAINING" ]; then
    echo "$REMAINING" | while read -r line; do echo "  $line"; done
else
    echo "  (none)"
fi

echo ""
echo "=== Shutdown complete ==="
echo ""
echo "What was preserved:"
echo "  • Log snapshots in logs/YYYY-MM-DD/"
echo "  • Daily reports in logs/reports/"
echo "  • Configuration and strategy files"
echo ""
echo "To start again: ./scripts/setup.sh"
