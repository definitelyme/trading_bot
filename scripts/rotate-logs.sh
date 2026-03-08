#!/bin/bash
# Log rotation script for Freqtrade
# Runs every 2 hours via cron. Copies current log to a timestamped snapshot,
# then truncates the active log. Freqtrade keeps writing (copytruncate pattern).

set -euo pipefail

# Project root (parent of scripts/)
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOGS_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOGS_DIR/freqtrade.log"

# Today's date and time window
TODAY=$(date +%Y-%m-%d)
HOUR=$(date +%H)
# Calculate the start of the 2-hour window (round down to even hour)
WINDOW_START=$(printf "%02d" $(( (10#$HOUR / 2) * 2 )))
WINDOW_END=$(printf "%02d" $(( (10#$HOUR / 2) * 2 + 2 )))

# Handle midnight rollover (22:00 to 00:00)
if [ "$WINDOW_END" = "24" ]; then
    WINDOW_END="00"
fi

DATE_DIR="$LOGS_DIR/$TODAY"
SNAPSHOT="$DATE_DIR/${TODAY}_${WINDOW_START}-00_to_${WINDOW_END}-00.log"

# Create today's folder if it doesn't exist
mkdir -p "$DATE_DIR"
mkdir -p "$LOGS_DIR/reports"

# Skip if log file doesn't exist or is empty
if [ ! -s "$LOG_FILE" ]; then
    echo "[$(date)] Log file empty or missing, skipping rotation" >> "$LOGS_DIR/rotation.log"
    exit 0
fi

# Copy log to timestamped snapshot
cp "$LOG_FILE" "$SNAPSHOT"

# Truncate the active log (Freqtrade holds file handle, keeps writing)
: > "$LOG_FILE"

# Check for heartbeat gaps (>5 min between heartbeats = potential sleep/crash)
LAST_HEARTBEAT=$(grep -o '[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\} [0-9]\{2\}:[0-9]\{2\}:[0-9]\{2\}' "$SNAPSHOT" | tail -1)
if [ -n "$LAST_HEARTBEAT" ]; then
    echo "[$(date)] Rotated: $SNAPSHOT (last activity: $LAST_HEARTBEAT)" >> "$LOGS_DIR/rotation.log"
else
    echo "[$(date)] WARNING: No timestamps found in log - bot may have been inactive" >> "$LOGS_DIR/rotation.log"
fi

echo "[$(date)] Rotation complete: $SNAPSHOT" >> "$LOGS_DIR/rotation.log"
