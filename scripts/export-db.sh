#!/bin/bash
# Daily SQLite export for AI Crypto Trader.
# Copies tradesv3.dryrun.sqlite from the Docker container to logs/db-exports/,
# named with the current timestamp. Keeps the last 7 files.
#
# Run via cron at 23:55 daily (4 min before daily-report.py at 23:59).
# Usage: ./scripts/export-db.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
EXPORT_DIR="$PROJECT_DIR/logs/db-exports"
CONTAINER="crypto-freqtrade-1"
DB_PATH="/freqtrade/tradesv3.dryrun.sqlite"
KEEP=7

mkdir -p "$EXPORT_DIR"

FILENAME="$(date +%Y-%m-%d_%H-%M).sqlite"
DEST="$EXPORT_DIR/$FILENAME"

if ! docker cp "$CONTAINER:$DB_PATH" "$DEST" 2>> "$PROJECT_DIR/logs/rotation.log"; then
    echo "[$(date)] ERROR: docker cp failed — is $CONTAINER running?" >> "$PROJECT_DIR/logs/rotation.log"
    exit 0
fi

echo "[$(date)] DB exported: $DEST" >> "$PROJECT_DIR/logs/rotation.log"

# Rolling retention: delete oldest file when count exceeds KEEP
# Filename sort is lexicographically chronological (ISO date format)
FILE_COUNT=$(ls -1 "$EXPORT_DIR"/*.sqlite 2>/dev/null | wc -l)
if [ "$FILE_COUNT" -gt "$KEEP" ]; then
    OLDEST=$(ls -1 "$EXPORT_DIR"/*.sqlite | sort | head -1)
    rm "$OLDEST"
    echo "[$(date)] DB export pruned oldest: $OLDEST" >> "$PROJECT_DIR/logs/rotation.log"
fi
