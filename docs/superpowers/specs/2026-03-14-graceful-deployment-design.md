# Graceful Deployment Design

**Date**: 2026-03-14
**Status**: Approved
**Scope**: CI/CD graceful restart with open-trade awareness, manual force override, and db-export cron fix

---

## Problem Statement

The current `deploy.yml` restarts the bot immediately on every merge to `main`, regardless of whether open trades exist. In live trading, this creates a brief window (~30s–2min) where the bot cannot act on price movements. Additionally:

- `scripts/setup.sh` is missing the `export-db.sh` cron entry, leaving `logs/db-exports/` always empty
- `scripts/setup-cron.sh` is a legacy script that overlaps `setup.sh`. It does contain the `export-db.sh` cron, but since callers are directed to run `setup.sh` (not `setup-cron.sh`), the entry is effectively unreachable. Deleting `setup-cron.sh` and adding its missing entry to `setup.sh` resolves both the duplication and the bug.
- `scripts/restart.sh` and a proposed `graceful-restart.sh` would have created another duplicate script pair — avoided by merging into one script with flags

---

## Design Decisions

### One script, not two

`restart.sh` is rewritten to include the graceful trade-check behaviour as its default. A `--force` flag skips it. This avoids the `setup.sh`/`setup-cron.sh` duplication pattern that already caused the `db-exports` bug. All callers (CI/CD, manual VPS use) use the same script with composable flags.

### Freqtrade REST API for trade detection

The script polls `GET /api/v1/status` (Freqtrade's built-in API, already running on port 8080) every 5 minutes. Credentials are read from `.env` via `grep`. This requires no new infrastructure.

`.env.example` must include `FREQTRADE__API_SERVER__USERNAME` and `FREQTRADE__API_SERVER__PASSWORD` so VPS setup guides the developer to fill them in. The script does a preflight check: if either credential is empty, it emits a distinct `WARN: API credentials not set` message and falls into the "API unreachable" path rather than silently sending a misleading Telegram warning.

### Distinct error path for HTTP 401

An HTTP 401 response from the API means credentials are misconfigured — this is different from the bot being unreachable. The script distinguishes: HTTP 401 → `WARN: API auth failed (wrong credentials?) — assuming no open trades`; connection error / non-200 other → `WARN: API unreachable — assuming no open trades`. Both proceed with the deploy rather than blocking, because a deploy that's not blocked on bad credentials is still safer than a deploy that hangs forever.

### Hourly notification via last_notified timestamp

The notification fires when `(now - last_notified) >= 3600`, not via a modulo operation. This avoids double-firing at the first poll and eliminates clock-drift edge cases.

### `ACTIONS_URL` passed from GitHub Actions runner into SSH session

The `export ACTIONS_URL=...` line is the first line inside the `appleboy/ssh-action` `script:` block — not a separate `run:` step. Both lines execute in the same shell on the VPS, so the variable is available when `restart.sh` runs. If `ACTIONS_URL` is not set (manual VPS use), the abort Telegram message simply omits the link.

### API unreachable = proceed

If the API is unreachable (container down, bot crashed), the script treats this as "no open trades" and deploys. If the bot is already down, there is nothing to protect.

### `docker compose down` + `up -d` semantics

`docker compose down` tears down the container (no-op if it is already stopped). `docker compose up -d` creates a fresh container from the current compose file. The sequence is destructive-then-recreate, not idempotent — but correct for all cases: running bot, stopped bot, or crashed bot.

### Two Telegram messages on abort (intentional)

On a 4-hour timeout abort, the user receives:
1. A specific message from `restart.sh`: "X trades still open after 4h — here's the force-deploy link"
2. A generic failure message from `deploy.yml`: "Deployment FAILED — Check GitHub Actions"

Both are useful. Message 1 explains why and provides the force-deploy URL. Message 2 links to the Actions run log. This is possible because `restart.sh` exits 1, which triggers `set -e` in the SSH script block, which causes the ssh-action step to fail, which triggers deploy.yml's `if: failure()` notification step. The double-message behaviour is intentional.

### `github.event.inputs.force_deploy` is empty string on push events

When the workflow is triggered by a `push` event (not `workflow_dispatch`), `github.event.inputs.force_deploy` is empty string, not `"false"`. The comparison `= "true"` handles this correctly — empty string is not equal to `"true"`. Do NOT change this comparison to `!= "false"`, as that would treat push events as force-deploys.

---

## Architecture

```
Trigger: push to main  OR  workflow_dispatch (force_deploy: true/false)
         │
         ▼
deploy.yml (GitHub Actions — ubuntu-latest runner)
  1. Detect Dockerfile change → set rebuild flag
  2. Build RESTART_ARGS: "--force" if force_deploy="true", "--rebuild" if Dockerfile changed
     Note: --force and --rebuild may both be set simultaneously — this is valid
  3. Send Telegram: "🚀 Deploying: <commit msg> (<sha>)"
  4. SSH into VPS (appleboy/ssh-action) → script block:
       export ACTIONS_URL="https://github.com/${{ github.repository }}/actions/workflows/deploy.yml"
       cd /opt/crypto
       git pull origin main
       ./scripts/restart.sh ${{ steps.restart_args.outputs.args }}
  5. On success: Telegram "✅ Deployment complete"
  6. On failure: Telegram "❌ Deployment FAILED: <commit> — Check GitHub Actions"
         │
         ▼
scripts/restart.sh (runs on VPS at /opt/crypto)

  [Preflight]
    → Read USERNAME from .env: grep -m1 FREQTRADE__API_SERVER__USERNAME .env | cut -d= -f2
    → Read PASSWORD from .env: grep -m1 FREQTRADE__API_SERVER__PASSWORD .env | cut -d= -f2
    → If USERNAME or PASSWORD empty: log "WARN: API credentials not set in .env"
      → set API_AVAILABLE=false (skip to "API unreachable" path)

  [If --force]
    → Log "[FORCED] Skipping open-trade check"
    → Telegram: "⚡ Force deploy triggered — skipping trade check"
    → Jump to Docker restart

  [Default: trade check]
    → start_time = now
    → last_notified = now
    → first_message_sent = false
    → deadline = start_time + 14400  (4 hours)

    LOOP every 300 seconds (5 min):
      HTTP_CODE = curl --max-time 10 --connect-timeout 5 -o /tmp/ft_status.json
                       -w "%{http_code}" -s -u "$USERNAME:$PASSWORD"
                       http://localhost:8080/api/v1/status

      if HTTP_CODE == "401":
        Telegram: "⚠️ API auth failed (wrong credentials?) — assuming no open trades, deploying now"
        break

      if HTTP_CODE != "200" or curl failed:
        Telegram: "⚠️ API unreachable — assuming no open trades, deploying now"
        break

      trade_count = python3 -c "
        import json, sys
        try:
          data = json.load(open('/tmp/ft_status.json'))
          print(len(data) if isinstance(data, list) else 0)
        except Exception:
          print(0)
      "
      # Freqtrade GET /api/v1/status always returns a JSON array on HTTP 200.
      # The fallback (isinstance check + exception handler) guards against any
      # unexpected response shape — treating it as "no trades" to avoid infinite blocking.

      if trade_count == 0: break

      if not first_message_sent:
        Telegram: "🕐 Deploy queued: <trade_count> open trades. Checking every 5 min (timeout: 4h)"
        first_message_sent = true

      elif (now - last_notified) >= 3600:
        elapsed_h = (now - start_time) / 3600
        Telegram: "⏳ Still waiting: <trade_count> trades open, <elapsed_h>h elapsed"
        last_notified = now

      if now >= deadline:
        Telegram: "🚫 Deploy aborted: <trade_count> trades still open after 4h.
                   Force-deploy: $ACTIONS_URL"
        (ACTIONS_URL falls back to empty string if not set — link simply omitted)
        exit 1

      sleep 300

  [Docker restart]
    → ./scripts/export-db.sh || {
          echo "WARN: DB export failed — continuing restart"
          send_telegram_warn "⚠️ DB export failed before restart — continuing anyway"
      }
    → docker compose down
    → if --rebuild: docker compose up --build -d
    → else:         docker compose up -d
    → Show: docker compose ps --format '  {{.Name}}: {{.Status}}'
    → exit 0
```

---

## Components

### `scripts/restart.sh` — rewrite

**Flags** (all optional, combinable):
- `--force`: skip open-trade check and deploy immediately
- `--rebuild`: rebuild Docker image before starting
- `--force --rebuild`: skip trade check AND rebuild image

**Constants**:
```bash
TIMEOUT_SECONDS=14400   # 4 hours
POLL_INTERVAL=300       # 5 minutes
HOURLY_INTERVAL=3600    # 60 minutes between "still waiting" messages
API_URL="http://localhost:8080/api/v1"
CURL_OPTS="--max-time 10 --connect-timeout 5 -s"
```

**Inputs** (read from `.env` at runtime via `grep -m1 KEY .env | cut -d= -f2-`):
- `FREQTRADE__API_SERVER__USERNAME`
- `FREQTRADE__API_SERVER__PASSWORD`
- `FREQTRADE__TELEGRAM__TOKEN`
- `FREQTRADE__TELEGRAM__CHAT_ID`

> **Important**: Use `cut -d= -f2-` (not `cut -d= -f2`) to preserve `=` characters in values, which are common in base64-encoded passwords or JWT secrets.

**Environment variable** (set by deploy.yml before calling the script):
- `ACTIONS_URL`: full URL to the workflow dispatch page. Falls back to empty string if not set (manual VPS use — the abort message simply omits the link).

**Exit codes**:
- `0`: restart completed successfully
- `1`: deploy aborted (4h trade timeout) OR Docker error (set -euo pipefail catches Docker failures)

**Note on `set -euo pipefail`**: `export-db.sh` must be called as `./scripts/export-db.sh || { warn; }` to prevent its failure from triggering the pipefail exit. All other steps should fail fast.

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
    # Trim leading space if only --rebuild is set
    ARGS="${ARGS# }"
    echo "args=$ARGS" >> $GITHUB_OUTPUT
```

**Full updated SSH deploy step** `script:` block (replaces the current block entirely):
```yaml
- name: Deploy to VPS via SSH
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
```

**Important**: `export ACTIONS_URL=...` MUST be the first line inside the `script:` block (not a separate `run:` step). The `run:` step executes on the GitHub Actions runner; the `script:` block executes on the VPS.

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

Update the verification grep to include `export-db`:
```bash
crontab -l 2>/dev/null | grep -E "(two-hour-report|daily-report|backup-models|export-db)" | ...
```

Update the summary echo to include: `"  • At 23:55 daily: SQLite DB export to logs/db-exports/ (7-day rolling retention)"`

---

### `scripts/setup-cron.sh` — delete

Fully superseded by `setup.sh`. The `export-db.sh` entry from `setup-cron.sh` is being migrated to `setup.sh`. Deleting eliminates confusion about which script to run.

---

### `.env.example` — update

Add (already done in this branch):
```bash
# API server credentials — used by restart.sh to check for open trades before deploying
# Must match api_server.username / api_server.password in config.json
FREQTRADE__API_SERVER__USERNAME=
FREQTRADE__API_SERVER__PASSWORD=
FREQTRADE__API_SERVER__JWT_SECRET_KEY=
```

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| API credentials empty in `.env` | Preflight warns `WARN: API credentials not set` → treated as API unreachable → deploy proceeds |
| API returns HTTP 401 | Telegram: "API auth failed (wrong credentials?)" → deploy proceeds |
| API unreachable (bot down/crashed) | Telegram: "API unreachable — assuming no open trades" → deploy proceeds |
| 4h timeout, trades still open | Telegram abort message + force-deploy link → exit 1 |
| `--force` used | Log + Telegram "⚡ Force deploy" → skip straight to Docker restart |
| `--force --rebuild` combined | Skip trade check AND rebuild image (both flags valid together) |
| `export-db.sh` fails pre-restart | Telegram warning → continue restart (non-fatal, uses `|| { warn; }`) |
| `docker compose down` or `up` fails | `set -euo pipefail` catches it → exit 1 → deploy.yml failure notification fires |
| Bot already stopped before deploy | `docker compose down` no-ops; `docker compose up -d` creates fresh container |
| Concurrent deploys | GitHub Actions queues jobs — no collision |
| `ACTIONS_URL` not set (manual VPS use) | Abort message sends without the force-deploy link — not an error |

---

## Files Changed

| File | Change |
|---|---|
| `scripts/restart.sh` | **Rewrite** — add trade check loop, Telegram notifications, `--force` flag. Ensure `chmod +x scripts/restart.sh` after writing. |
| `.github/workflows/deploy.yml` | **Update** — add `workflow_dispatch`, build restart args step, pass args to SSH |
| `scripts/setup.sh` | **Update** — add `export-db.sh` cron, update verification grep + summary |
| `scripts/setup-cron.sh` | **Delete** |
| `.env.example` | **Update** — add `FREQTRADE__API_SERVER__USERNAME/PASSWORD/JWT_SECRET_KEY` |

No new files. No new dependencies (uses `curl` + `python3` already on the VPS).

---

## Testing

**Happy paths:**
- `restart.sh --force` with bot running: verify "⚡ Force deploy" Telegram sent, trade check skipped, Docker restarts
- `restart.sh` with bot running and 0 open trades: verify no "queued" message, restarts immediately
- `restart.sh` with mocked API returning 2 trades, then 0 on second poll: verify "queued" message sent, then restarts after second poll
- `restart.sh --rebuild`: verify `docker compose up --build -d` called (not plain `up -d`)
- `restart.sh --force --rebuild`: verify both flags applied — trade check skipped AND image rebuilt
- `deploy.yml` `workflow_dispatch` with `force_deploy: true`: verify `--force` in `RESTART_ARGS`
- `deploy.yml` push with Dockerfile changed: verify `--rebuild` in `RESTART_ARGS`
- `setup.sh`: verify `export-db.sh` cron appears in `crontab -l` after running

**Failure paths:**
- `restart.sh` with mocked API returning 2 trades for full 4h: verify exit 1, abort Telegram with `ACTIONS_URL` in message
- `export-db.sh` exits non-zero during restart: verify restart continues, Telegram warning sent, exit 0
- API returns HTTP 401: verify "API auth failed" Telegram sent, deploy proceeds (not blocked)
- `FREQTRADE__API_SERVER__USERNAME` empty in `.env`: verify `WARN: API credentials not set` logged, deploy proceeds
