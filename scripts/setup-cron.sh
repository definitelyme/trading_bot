#!/bin/bash
# Installs cron entries for log rotation and daily reports.
# Run once: ./scripts/setup-cron.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python3"

# Cron entries
ROTATE_ENTRY="0 */2 * * * $PROJECT_DIR/scripts/rotate-logs.sh >> $PROJECT_DIR/logs/rotation.log 2>&1"
REPORT_ENTRY="59 23 * * * $VENV_PYTHON $PROJECT_DIR/scripts/daily-report.py >> $PROJECT_DIR/logs/rotation.log 2>&1"

# Check if entries already exist
EXISTING=$(crontab -l 2>/dev/null || true)

if echo "$EXISTING" | grep -q "rotate-logs.sh"; then
    echo "Log rotation cron already installed."
else
    echo "$EXISTING" | { cat; echo "$ROTATE_ENTRY"; } | crontab -
    echo "Installed: log rotation every 2 hours"
fi

# Re-read after potential update
EXISTING=$(crontab -l 2>/dev/null || true)

if echo "$EXISTING" | grep -q "daily-report.py"; then
    echo "Daily report cron already installed."
else
    echo "$EXISTING" | { cat; echo "$REPORT_ENTRY"; } | crontab -
    echo "Installed: daily report at 23:59"
fi

# Re-read after potential update
EXISTING=$(crontab -l 2>/dev/null || true)

DB_EXPORT_ENTRY="55 23 * * * $PROJECT_DIR/scripts/export-db.sh >> $PROJECT_DIR/logs/rotation.log 2>&1"

if echo "$EXISTING" | grep -q "export-db.sh"; then
    echo "DB export cron already installed."
else
    echo "$EXISTING" | { cat; echo "$DB_EXPORT_ENTRY"; } | crontab -
    echo "Installed: SQLite export at 23:55"
fi

echo ""
echo "Current crontab:"
crontab -l
echo ""
echo "Done. Cron entries installed."
