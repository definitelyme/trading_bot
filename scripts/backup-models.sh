#!/bin/bash
# Back up FreqAI models to Cloudflare R2.
#
# Usage:
#   ./scripts/backup-models.sh
#
# What it does:
#   1. Syncs user_data/models/ → r2:bucket/latest/  (mirrors current state — no file accumulation)
#   2. Copies a named snapshot  → r2:bucket/snapshots/YYYY-MM-DD/
#   3. Deletes snapshots older than 28 days from R2
#
# Requirements:
#   - rclone installed and configured with a remote named 'r2'
#   - Run as the same user who configured rclone (config at ~/.config/rclone/rclone.conf)
#   - Verify setup: rclone ls r2:crypto-bot-backup
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MODELS_DIR="$PROJECT_DIR/user_data/models"
BUCKET="r2:crypto-bot-backup"
DATE=$(date +%Y-%m-%d)

if [ ! -d "$MODELS_DIR" ] || [ -z "$(ls -A "$MODELS_DIR" 2>/dev/null)" ]; then
  echo "No models found at $MODELS_DIR — nothing to back up"
  exit 0
fi

echo "=== Model Backup to R2 ==="
echo "  Source:   $MODELS_DIR"
echo "  Date:     $DATE"
echo ""

# 1. Sync to latest/ — mirrors current state, deletes files no longer in source
echo "[1/3] Syncing to $BUCKET/latest/ ..."
rclone sync "$MODELS_DIR/" "$BUCKET/latest/" --progress
echo "  ✓ latest/ synced (previous latest replaced)"

# 2. Copy a named snapshot for this date
echo ""
echo "[2/3] Creating snapshot: $BUCKET/snapshots/$DATE/ ..."
rclone copy "$MODELS_DIR/" "$BUCKET/snapshots/$DATE/" --progress
echo "  ✓ Snapshot saved"

# 3. Rotate: delete snapshots older than 28 days
echo ""
echo "[3/3] Rotating snapshots older than 28 days..."
rclone delete "$BUCKET/snapshots/" --min-age 28d --rmdirs
echo "  ✓ Old snapshots rotated"

echo ""
echo "=== Backup complete ==="
echo "  Latest:   $BUCKET/latest/"
echo "  Snapshot: $BUCKET/snapshots/$DATE/"
echo ""
echo "List all snapshots:"
echo "  rclone ls $BUCKET/snapshots/"
