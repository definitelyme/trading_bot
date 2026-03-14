# Graceful Deployment Design

**Date**: 2026-03-14
**Status**: Approved
**Scope**: CI/CD graceful restart with open-trade awareness, manual force override, and db-export cron fix

---

## Problem Statement

The current `deploy.yml` restarts the bot immediately on every merge to `main`, regardless of whether open trades exist. In live trading, this creates a brief window (~30s–2min) where the bot cannot act on price movements. Additionally:

- `scripts/setup.sh` is missing the `export-db.sh` cron entry, leaving `logs/db-exports/` always empty
- `scripts/setup-cron.sh` is a duplicate/legacy script that partially overlaps `setup.sh`, creating confusion and bugs
- `scripts/restart.sh` and a proposed `graceful-restart.sh` would have created another duplicate script pair

---

## Design Decisions

### One script, not two

`restart.sh` is rewritten to include the graceful trade-check behaviour as its default. A `--force` flag skips it. This avoids the `setup.sh`/`setup-cron.sh` duplication pattern that already caused the `db-exports` bug. All callers (CI/CD, manual VPS use) use the same script with composable flags.

### Freqtrade REST API for trade detection

The script polls `GET /api/v1/status` (Freqtrade's built-in API, already running on port 8080) every 5 minutes. Credentials are read from `.env` via `grep`. This requires no new infrastructure.

### API unreachable = proceed

If the API is unreachable (container down, bot crashed), the script treats this as "no open trades" and deploys. If the bot is already down, there is nothing to protect.

### GitHub Actions `workflow_dispatch` for force override

A manual trigger with a `force_deploy` boolean checkbox is added to `deploy.yml`. Triggerable from GitHub.com or GitHub mobile. When the abort message is sent to Telegram, it includes the direct URL to this workflow dispatch page so the force-deploy is two taps away.

### Two Telegram messages on abort (intentional)

On a 4-hour timeout abort, the user receives:
1. A specific message from `restart.sh`: "X trades still open after 4h — here's the force-deploy link"
2. A generic failure message from `deploy.yml`: "Deployment FAILED — Check GitHub Actions"

Both are useful. Message 1 explains why. Message 2 links to the Actions run log.

---

## Architecture

```
Trigger: push to main  OR  workflow_dispatch (force_deploy: true/false)
         │
         ▼
deploy.yml (GitHub Actions — ubuntu-latest runner)
  1. Detect Dockerfile change → set rebuild flag
  2. Build RESTART_ARGS: "--force" if force_deploy, "--rebuild" if Dockerfile changed
  3. Send Telegram: "🚀 Deploying: <commit msg> (<sha>)"
  4. SSH into VPS → export ACTIONS_URL → run ./scripts/restart.sh $RESTART_ARGS
  5. On success: Telegram "✅ Deployment complete"
  6. On failure: Telegram "❌ Deployment FAILED: <commit> — Check GitHub Actions"
         │
         ▼
scripts/restart.sh (runs on VPS at /opt/crypto)
  [If --force]
    → Log "FORCED: skipping open-trade check"
    → Telegram: "⚡ Force deploy triggered — skipping trade check"
    → Jump to Docker restart

  [Default: trade check]
    → Read API credentials from .env
    → deadline = now + 4h
    → first_check = true
    LOOP every 5 minutes:
      trade_count = curl GET /api/v1/status | python3 count
      if API unreachable:
        Telegram: "⚠️ API unreachable — assuming no open trades, deploying now"
        break
      if trade_count == 0: break
      if first_check:
        Telegram: "🕐 Deploy queued: <N> open trades. Checking every 5 min (timeout: 4h)"
        first_check = false
      if (now - start) % 3600 < 300:  # every ~60 min
        Telegram: "⏳ Still waiting: <N> trades open, <X>h elapsed"
      if now >= deadline:
        Telegram: "🚫 Deploy aborted: <N> trades still open after 4h.\nForce-deploy: $ACTIONS_URL"
        exit 1

  [Docker restart]
    → Run export-db.sh (non-fatal if it fails — warns and continues)
    → docker compose down
    → if --rebuild: docker compose up --build -d
    → else:         docker compose up -d
    → Show docker compose ps status
```

---

## Components

### `scripts/restart.sh` — rewrite

**Flags**:
- `--force`: skip open-trade check
- `--rebuild`: rebuild Docker image before starting

**Inputs** (read from `.env` at runtime):
- `FREQTRADE__API_SERVER__USERNAME`
- `FREQTRADE__API_SERVER__PASSWORD`
- `FREQTRADE__TELEGRAM__TOKEN`
- `FREQTRADE__TELEGRAM__CHAT_ID`

**Outputs**:
- Exit 0: restart completed successfully
- Exit 1: deploy aborted (trade timeout) or Docker error

**Constants**:
- `TIMEOUT_SECONDS=14400` (4 hours)
- `POLL_INTERVAL=300` (5 minutes)
- `API_URL=http://localhost:8080/api/v1`

**Environment variable**:
- `ACTIONS_URL`: set by deploy.yml before calling the script; used in abort Telegram message. Falls back to empty string if not set (manual VPS use).

---

### `.github/workflows/deploy.yml` — additions

**New trigger**:
```yaml
workflow_dispatch:
  inputs:
    force_deploy:
      description: "Skip open-trade check and deploy immediately"
      type: boolean
      default: false
```

**New step** (after Dockerfile check, before SSH deploy):
```yaml
- name: Build restart args
  id: restart_args
  run: |
    ARGS=""
    if [ "${{ github.event.inputs.force_deploy }}" = "true" ]; then
      ARGS="--force"
    fi
    if [ "${{ steps.dockerfile_check.outputs.rebuild }}" = "true" ]; then
      ARGS="$ARGS --rebuild"
    fi
    echo "args=$ARGS" >> $GITHUB_OUTPUT
```

**SSH deploy step** (updated `script` block):
```
export ACTIONS_URL="https://github.com/${{ github.repository }}/actions/workflows/deploy.yml"
cd /opt/crypto
git pull origin main
./scripts/restart.sh ${{ steps.restart_args.outputs.args }}
```

---

### `scripts/setup.sh` — minor addition

Add `export-db.sh` cron after the existing `backup-models.sh` block:
```bash
DB_EXPORT_ENTRY="55 23 * * * $PROJECT_DIR/scripts/export-db.sh >> $PROJECT_DIR/logs/rotation.log 2>&1"

EXISTING=$(crontab -l 2>/dev/null || true)
if echo "$EXISTING" | grep -q "export-db.sh"; then
    echo "  ✓ DB export cron already installed"
else
    echo "$EXISTING" | { cat; echo "$DB_EXPORT_ENTRY"; } | crontab -
    echo "  ✓ Installed: SQLite export daily at 23:55"
fi
```

Update the verification grep and summary echo to include `export-db`.

---

### `scripts/setup-cron.sh` — delete

Fully superseded by `setup.sh`. All its entries are either already in `setup.sh` or being added in this change. Deleting eliminates confusion about which script to run.

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| API unreachable (bot down) | Log warning, send Telegram warning, proceed with deploy |
| `.env` credentials missing | Auth fails → treated as API unreachable (same path above) |
| 4h timeout, trades still open | Send Telegram abort + force-deploy link, exit 1 |
| `--force` used | Log "FORCED", send Telegram notice, skip straight to Docker restart |
| `export-db.sh` fails pre-restart | Log error, send Telegram warning, continue restart (non-fatal) |
| Bot already stopped before deploy | `docker compose up -d` is idempotent — starts it cleanly |
| Concurrent deploys | GitHub Actions queues jobs — no collision |

---

## Files Changed

| File | Change |
|---|---|
| `scripts/restart.sh` | **Rewrite** — add trade check loop, Telegram notifications, `--force` flag |
| `.github/workflows/deploy.yml` | **Update** — add `workflow_dispatch`, build restart args step, pass args to SSH |
| `scripts/setup.sh` | **Update** — add `export-db.sh` cron, update verification grep + summary |
| `scripts/setup-cron.sh` | **Delete** |

No new files. No new dependencies.

---

## Testing

- `restart.sh --force`: verify skips trade check, sends "⚡ Force deploy" Telegram, restarts Docker
- `restart.sh` with bot running and no open trades: verify starts immediately, no waiting message
- `restart.sh` with mocked API returning 2 trades: verify waits, sends "queued" message
- `restart.sh` with API returning 200 but empty list after 1 poll: verify restarts after first successful check
- `deploy.yml` `workflow_dispatch` with `force_deploy: true`: verify `--force` is passed to script
- `deploy.yml` push with Dockerfile changed: verify `--rebuild` is passed
- `setup.sh`: verify `export-db.sh` cron appears in `crontab -l` after running
