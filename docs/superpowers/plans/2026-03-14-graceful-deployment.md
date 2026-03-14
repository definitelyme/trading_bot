# Graceful Deployment Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `restart.sh` to wait for open trades before restarting, add a `--force` override to `deploy.yml`, and fix the missing `export-db.sh` cron in `setup.sh`.

**Architecture:** A single `scripts/restart.sh` replaces the current immediate-restart script. By default it polls the Freqtrade REST API (`/api/v1/status`) every 5 minutes for up to 4 hours before proceeding with a Docker restart; `--force` skips the check. `deploy.yml` gains a `workflow_dispatch` trigger that passes `--force` when ticked. `setup.sh` gains the missing `export-db.sh` daily cron, and the legacy `setup-cron.sh` is deleted.

**Tech Stack:** Bash, Docker Compose, GitHub Actions (appleboy/ssh-action), Freqtrade REST API (curl + python3), Telegram Bot API

**Spec:** `docs/superpowers/specs/2026-03-14-graceful-deployment-design.md`

---

## Chunk 1: Setup cleanup + restart.sh rewrite

### Task 1: Fix `setup.sh` — add `export-db.sh` cron + delete `setup-cron.sh`

**Files:**
- Modify: `scripts/setup.sh:58,85-98,110`
- Delete: `scripts/setup-cron.sh`

- [ ] **Step 1: Add `DB_EXPORT_ENTRY` variable**

In `scripts/setup.sh`, find the line:
```bash
BACKUP_ENTRY="0 3 * * * $PROJECT_DIR/scripts/backup-models.sh >> $PROJECT_DIR/logs/model-backup.log 2>&1"
```
Add one line immediately after it:
```bash
DB_EXPORT_ENTRY="55 23 * * * $PROJECT_DIR/scripts/export-db.sh >> $PROJECT_DIR/logs/rotation.log 2>&1"
```

- [ ] **Step 2: Add the cron install block**

Find and add after the closing `fi` of the `backup-models.sh` cron block:
```bash
    echo "  ✓ Installed: model backup daily at 03:00"
fi
```
Insert the following block immediately after that `fi` (outside it, at the same indentation level):
```bash
EXISTING=$(crontab -l 2>/dev/null || true)

if echo "$EXISTING" | grep -q "export-db.sh"; then
    echo "  ✓ DB export cron already installed"
else
    echo "$EXISTING" | { cat; echo "$DB_EXPORT_ENTRY"; } | crontab -
    echo "  ✓ Installed: SQLite DB export daily at 23:55"
fi
```

- [ ] **Step 3: Update the verification grep**

Find:
```bash
crontab -l 2>/dev/null | grep -E "(two-hour-report|daily-report|backup-models)" | while read -r line; do
```
Replace with:
```bash
crontab -l 2>/dev/null | grep -E "(two-hour-report|daily-report|backup-models|export-db)" | while read -r line; do
```

- [ ] **Step 4: Update the summary echo**

Find:
```bash
echo "  • At 03:00 daily: model backup to Cloudflare R2 (requires rclone configured)"
```
Add one line after it:
```bash
echo "  • At 23:55 daily: SQLite DB export to logs/db-exports/ (7-day rolling retention)"
```

- [ ] **Step 5: Validate `setup.sh` syntax**

```bash
bash -n scripts/setup.sh && echo "Syntax OK"
```
Expected: `Syntax OK`

- [ ] **Step 6: Delete `setup-cron.sh`**

```bash
git rm scripts/setup-cron.sh
```

- [ ] **Step 7: Commit**

```bash
git add scripts/setup.sh
git commit -m "fix: add export-db.sh cron to setup.sh and remove legacy setup-cron.sh"
```

---

### Task 2: Rewrite `scripts/restart.sh`

**Files:**
- Modify: `scripts/restart.sh` (full rewrite)

- [ ] **Step 1: Verify current file state before rewriting**

```bash
cat scripts/restart.sh
```
Note: The current file has basic `--rebuild` support but no trade check. The rewrite replaces it entirely.

- [ ] **Step 2: Write the new `restart.sh`**

Write `scripts/restart.sh` with exactly this content:

```bash
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
CURL_OPTS="--max-time 10 --connect-timeout 5 -s"

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
      HTTP_CODE=$(curl $CURL_OPTS \
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
```

- [ ] **Step 3: Make executable**

```bash
chmod +x scripts/restart.sh
```

- [ ] **Step 4: Validate syntax**

```bash
bash -n scripts/restart.sh && echo "Syntax OK"
```
Expected: `Syntax OK`

- [ ] **Step 5: Run shellcheck if available**

```bash
shellcheck scripts/restart.sh && echo "shellcheck OK" || echo "shellcheck not available"
```
Expected: `shellcheck OK` or `shellcheck not available` — no hard failure here since shellcheck may not be installed.

- [ ] **Step 6: Verify flags are parsed correctly (dry-run test)**

```bash
# Test: confirm --force and --rebuild are parsed without running Docker
bash -c '
  source scripts/restart.sh --force --rebuild 2>&1 || true
' | head -3
```

This will fail at the Docker step (no Docker on CI) but the flag parsing and echo lines should be visible. More complete testing is done on the VPS — see Task 3 testing section.

- [ ] **Step 7: Commit**

```bash
git add scripts/restart.sh
git commit -m "feat: rewrite restart.sh with graceful trade-check, --force flag, and Telegram notifications"
```

---

## Chunk 2: CI/CD update

### Task 3: Update `.github/workflows/deploy.yml`

**Files:**
- Modify: `.github/workflows/deploy.yml` (full replacement)

- [ ] **Step 1: Read the current file to understand what changes**

```bash
cat .github/workflows/deploy.yml
```

Note the three things being added:
1. `workflow_dispatch` trigger with `force_deploy` boolean
2. New "Build restart args" step
3. Updated SSH deploy `script:` block (adds `ACTIONS_URL`, removes old if/else rebuild logic, passes `${{ steps.restart_args.outputs.args }}`)

Also note the "Notify Telegram — deploy starting" step gets updated to show `[FORCED]` in the message when force-deploy is used.

- [ ] **Step 2: Write the updated `deploy.yml`**

Write `.github/workflows/deploy.yml` with exactly this content:

```yaml
name: Deploy to VPS

on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      force_deploy:
        description: "Skip open-trade check and deploy immediately"
        type: boolean
        default: false

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2  # Required for Dockerfile change detection

      - name: Detect if Dockerfile changed (needs full image rebuild)
        id: dockerfile_check
        run: |
          if git diff HEAD~1 HEAD --name-only | grep -qE "^Dockerfile$"; then
            echo "rebuild=true" >> $GITHUB_OUTPUT
          else
            echo "rebuild=false" >> $GITHUB_OUTPUT
          fi

      - name: Build restart args
        id: restart_args
        run: |
          ARGS=""
          # NOTE: github.event.inputs.force_deploy is empty string (not "false") on push
          # events. The = "true" comparison handles both cases correctly.
          if [ "${{ github.event.inputs.force_deploy }}" = "true" ]; then
            ARGS="--force"
          fi
          if [ "${{ steps.dockerfile_check.outputs.rebuild }}" = "true" ]; then
            ARGS="$ARGS --rebuild"
          fi
          # Trim leading space if only --rebuild is set
          ARGS="${ARGS# }"
          echo "args=$ARGS" >> $GITHUB_OUTPUT

      - name: Notify Telegram — deploy starting
        run: |
          COMMIT_MSG=$(git log -1 --pretty=format:'%s')
          SHORT_SHA=$(git rev-parse --short HEAD)
          FORCE="${{ github.event.inputs.force_deploy }}"
          REBUILD="${{ steps.dockerfile_check.outputs.rebuild }}"
          NOTE=""
          if [ "$FORCE" = "true" ]; then
            NOTE=" [FORCED]"
          fi
          if [ "$REBUILD" = "true" ]; then
            NOTE="$NOTE (image rebuild)"
          fi
          MSG="🚀 Deploying: $COMMIT_MSG ($SHORT_SHA)$NOTE"
          curl -s -X POST "https://api.telegram.org/bot${{ secrets.TELEGRAM_BOT_TOKEN }}/sendMessage" \
            -d "chat_id=${{ secrets.TELEGRAM_CHAT_ID }}" \
            -d "text=$MSG" > /dev/null

      - name: Deploy to VPS via SSH
        # Pinned to commit SHA — verify at: https://github.com/appleboy/ssh-action/releases/tag/v1.0.3
        # ACTIONS_URL MUST be in this script: block (not a separate run: step) — it runs on the VPS,
        # not the GitHub Actions runner.
        uses: appleboy/ssh-action@4a03da89e5c43da56e502053be254c02e2b6ded5  # v1.0.3
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            export ACTIONS_URL="https://github.com/${{ github.repository }}/actions/workflows/deploy.yml"
            set -e
            cd /opt/crypto
            git pull origin main
            ./scripts/restart.sh ${{ steps.restart_args.outputs.args }}

      - name: Notify Telegram — deploy succeeded
        if: success()
        run: |
          curl -s -X POST "https://api.telegram.org/bot${{ secrets.TELEGRAM_BOT_TOKEN }}/sendMessage" \
            -d "chat_id=${{ secrets.TELEGRAM_CHAT_ID }}" \
            -d "text=✅ Deployment complete. Bot is running." > /dev/null

      - name: Notify Telegram — deploy failed
        # Also fires when restart.sh exits 1 due to 4h trade timeout abort.
        # In that case, restart.sh already sent a specific Telegram message with the force-deploy URL.
        # This message adds the GitHub Actions link for the run log.
        if: failure()
        run: |
          COMMIT_MSG=$(git log -1 --pretty=format:'%s')
          SHORT_SHA=$(git rev-parse --short HEAD)
          curl -s -X POST "https://api.telegram.org/bot${{ secrets.TELEGRAM_BOT_TOKEN }}/sendMessage" \
            -d "chat_id=${{ secrets.TELEGRAM_CHAT_ID }}" \
            -d "text=❌ Deployment FAILED: $COMMIT_MSG ($SHORT_SHA). Check GitHub Actions." > /dev/null
```

- [ ] **Step 3: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml')); print('YAML valid')"
```
Expected: `YAML valid`

- [ ] **Step 4: Verify `workflow_dispatch` trigger is present**

```bash
grep -A4 "workflow_dispatch:" .github/workflows/deploy.yml
```
Expected: shows the `inputs:` block with `force_deploy`.

- [ ] **Step 5: Verify all 5 required secrets are still referenced**

```bash
grep -oP 'secrets\.\K[A-Z_]+' .github/workflows/deploy.yml | sort -u
```
Expected: `TELEGRAM_BOT_TOKEN  TELEGRAM_CHAT_ID  VPS_HOST  VPS_SSH_KEY  VPS_USER`

- [ ] **Step 6: Verify `ACTIONS_URL` is set inside the `script:` block (not in a `run:` step)**

```bash
python3 -c "
import yaml
wf = yaml.safe_load(open('.github/workflows/deploy.yml'))
steps = wf['jobs']['deploy']['steps']
ssh_step = next(s for s in steps if 'appleboy/ssh-action' in s.get('uses', ''))
script = ssh_step['with']['script']
assert 'export ACTIONS_URL' in script, 'ACTIONS_URL not in script block!'
lines = script.strip().splitlines()
assert lines[0].startswith('export ACTIONS_URL'), f'ACTIONS_URL not first line: {lines[0]}'
print('ACTIONS_URL placement: OK')
"
```
Expected: `ACTIONS_URL placement: OK`

- [ ] **Step 7: Verify restart args step outputs are wired correctly**

```bash
python3 -c "
import yaml
wf = yaml.safe_load(open('.github/workflows/deploy.yml'))
steps = wf['jobs']['deploy']['steps']
# Check restart_args step exists
args_step = next((s for s in steps if s.get('id') == 'restart_args'), None)
assert args_step is not None, 'restart_args step missing'
# Check SSH step references restart_args output
ssh_step = next(s for s in steps if 'appleboy/ssh-action' in s.get('uses', ''))
assert 'restart_args.outputs.args' in ssh_step['with']['script'], 'restart_args not used in SSH step'
print('restart_args wiring: OK')
"
```
Expected: `restart_args wiring: OK`

- [ ] **Step 8: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "feat: add workflow_dispatch force-deploy override and graceful restart integration to deploy.yml"
```

---

## Post-implementation verification

After all tasks are committed, run these to confirm everything is consistent:

- [ ] **Verify git log looks right**

```bash
git log --oneline -5
```
Expected: 3 new commits on top of the previous feature branch work.

- [ ] **Verify setup.sh has 4 cron entries now**

```bash
grep -E "ENTRY=" scripts/setup.sh
```
Expected: `ROTATE_ENTRY`, `REPORT_ENTRY`, `BACKUP_ENTRY`, `DB_EXPORT_ENTRY` — four entries.

- [ ] **Verify setup-cron.sh is gone**

```bash
ls scripts/setup-cron.sh 2>/dev/null && echo "STILL EXISTS — delete it" || echo "Gone: OK"
```
Expected: `Gone: OK`

- [ ] **Verify restart.sh has all four flags covered**

```bash
grep -E "\-\-force|\-\-rebuild|FORCE|REBUILD" scripts/restart.sh | head -10
```
Expected: shows `--force`, `--rebuild`, `FORCE=false`, `REBUILD=false`, and both conditionals.

- [ ] **Full syntax check on all modified scripts**

```bash
bash -n scripts/restart.sh && echo "restart.sh: OK"
bash -n scripts/setup.sh && echo "setup.sh: OK"
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml')); print('deploy.yml: OK')"
```
Expected: all three `OK`.

---

## VPS smoke test (run after deploying to VPS)

These require a running bot on the VPS. Run from the VPS as the `deploy` user.

- [ ] **Test: `--force` skips trade check and restarts immediately**

```bash
cd /opt/crypto
./scripts/restart.sh --force
# Expected: "[FORCED] Skipping open-trade check" then Docker restart completes
```

- [ ] **Test: no open trades → restarts immediately without --force**

```bash
cd /opt/crypto
# Run only when bot has 0 open trades (check: curl -s -u user:pass http://localhost:8080/api/v1/status | python3 -c "import json,sys; print(len(json.load(sys.stdin)))")
./scripts/restart.sh
# Expected: no "Deploy queued" Telegram message; Docker restarts immediately
```

- [ ] **Test: `--force --rebuild` combination**

```bash
./scripts/restart.sh --force --rebuild
# Expected: "[FORCED]" message, then "Rebuilding image and starting container..."
```

- [ ] **Test: API credentials preflight (missing credentials)**

```bash
cd /opt/crypto
# Temporarily blank out the USERNAME in .env to trigger the preflight warning
cp .env .env.bak
sed -i 's/^FREQTRADE__API_SERVER__USERNAME=.*/FREQTRADE__API_SERVER__USERNAME=/' .env
./scripts/restart.sh
# Expected: "WARN: API credentials not set in .env — skipping trade check" and Telegram warning sent
# Then restore:
mv .env.bak .env
```

- [ ] **Test: workflow_dispatch from GitHub**

In the GitHub repo → Actions → "Deploy to VPS" → "Run workflow" → tick "Skip open-trade check" → Run
Expected: Telegram message with `[FORCED]` in the deploy-starting notification; deployment completes.
