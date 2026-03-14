#!/bin/bash
# Smart restart for the AI Crypto Trader bot.
#
# Usage:
#   ./scripts/restart.sh           — recreate container (picks up compose changes, no image rebuild)
#   ./scripts/restart.sh --rebuild — full image rebuild + recreate (use when Dockerfile changed)
#
# Requirements: run as a user in the 'docker' group.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REBUILD=false

for arg in "$@"; do
  case $arg in
    --rebuild) REBUILD=true ;;
  esac
done

echo "=== AI Crypto Trader — Restart ==="
cd "$PROJECT_DIR"

if [ "$REBUILD" = true ]; then
  echo "[1/1] Rebuilding image and recreating container..."
  docker compose up --build -d
  echo "  ✓ Image rebuilt and container started"
else
  echo "[1/1] Recreating container (no image rebuild)..."
  # 'up -d' recreates container if compose definition changed;
  # does NOT pick up image changes without --build.
  docker compose up -d
  echo "  ✓ Container recreated"
fi

echo ""
echo "Status:"
docker compose ps --format '  {{.Name}}: {{.Status}}'
