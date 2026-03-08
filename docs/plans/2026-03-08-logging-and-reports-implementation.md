# Logging & Reports Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automated 2-hour log rotation with daily performance reports for tracking and improving the ML trading model.

**Architecture:** Freqtrade writes to a log file via `--logfile`. A bash cron job rotates it every 2 hours (copytruncate pattern). A Python script queries the Freqtrade REST API and parses log files to generate a daily markdown report. Both scripts run on the host via cron.

**Tech Stack:** Bash (rotation), Python 3 + requests (reports), cron (scheduling), Docker (config changes only).

---

### Task 1: Docker and gitignore changes

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.gitignore`

**Step 1: Update docker-compose.yml**

Add the `--logfile` flag and a volume mount for logs. The updated file should be:

```yaml
services:
  freqtrade:
    build: .
    restart: unless-stopped
    volumes:
      - ./user_data:/freqtrade/user_data
      - ./.env:/freqtrade/.env
      - ./logs:/freqtrade/user_data/logs
    ports:
      - "8080:8080"
    env_file:
      - .env
    command: >
      trade
      --config user_data/config.json
      --strategy AICryptoStrategy
      --freqaimodel XGBoostRegressor
      --logfile user_data/logs/freqtrade.log
      --dry-run
```

Changes from current:
- Added volume `./logs:/freqtrade/user_data/logs` — maps host `logs/` to container log path
- Added `--logfile user_data/logs/freqtrade.log` — Freqtrade writes to both stdout AND this file

**Step 2: Update .gitignore**

Add `logs/` to `.gitignore` (log files contain trade data and should not be committed):

```
logs/
```

**Step 3: Create logs directory structure**

```bash
mkdir -p logs/reports
```

**Step 4: Verify Docker still starts**

```bash
docker compose down && docker compose up --build -d
```

Wait 30 seconds, then check:

```bash
docker compose logs --tail 5
```

Expected: bot starts normally with heartbeat lines.

Then verify the log file exists on host:

```bash
ls -la logs/freqtrade.log
```

Expected: file exists and growing.

**Step 5: Commit**

```bash
git add docker-compose.yml .gitignore
git commit -m "feat: add Freqtrade log file output and logs volume mount"
```

---

### Task 2: Log rotation script

**Files:**
- Create: `scripts/rotate-logs.sh`

**Step 1: Create scripts directory**

```bash
mkdir -p scripts
```

**Step 2: Write the rotation script**

Create `scripts/rotate-logs.sh`:

```bash
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
```

**Step 3: Make executable**

```bash
chmod +x scripts/rotate-logs.sh
```

**Step 4: Test the script manually**

Make sure the bot is running and `logs/freqtrade.log` has content, then:

```bash
./scripts/rotate-logs.sh
```

Verify:
- A date folder was created: `ls logs/$(date +%Y-%m-%d)/`
- A snapshot file exists with content: `wc -l logs/$(date +%Y-%m-%d)/*.log`
- The active log was truncated: `wc -l logs/freqtrade.log` (should be 0 or very small)
- rotation.log was updated: `cat logs/rotation.log`

**Step 5: Commit**

```bash
git add scripts/rotate-logs.sh
git commit -m "feat: add 2-hour log rotation script"
```

---

### Task 3: Daily report script

**Files:**
- Create: `scripts/daily-report.py`

**Step 1: Install requests in project venv**

```bash
source .venv/bin/activate && pip install requests
```

**Step 2: Write the daily report script**

Create `scripts/daily-report.py`:

```python
#!/usr/bin/env python3
"""Daily performance report generator for AI Crypto Trader.

Queries the Freqtrade REST API and parses today's log files to generate
a markdown report. Run via cron at 23:59 daily.

Usage: python3 scripts/daily-report.py [--date YYYY-MM-DD]
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import requests

PROJECT_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_DIR / "logs"
CONFIG_FILE = PROJECT_DIR / "user_data" / "config.json"
API_BASE = "http://localhost:8080/api/v1"


def load_config():
    """Read API credentials from config.json."""
    with open(CONFIG_FILE) as f:
        config = json.load(f)
    return {
        "username": config["api_server"]["username"],
        "password": config["api_server"]["password"],
    }


def get_api_token(creds):
    """Authenticate and get JWT token."""
    resp = requests.post(
        f"{API_BASE}/token/login",
        json=creds,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def api_get(endpoint, token):
    """Make authenticated GET request to Freqtrade API."""
    resp = requests.get(
        f"{API_BASE}{endpoint}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def parse_logs(date_str):
    """Parse today's rotated log files for model metrics."""
    date_dir = LOGS_DIR / date_str
    metrics = {
        "retrains": 0,
        "total_training_time": 0.0,
        "nan_drop_lines": 0,
        "nan_total_points": 0,
        "nan_dropped_points": 0,
        "entry_signals": 0,
        "stoploss_exits": 0,
        "trailing_stop_exits": 0,
        "roi_exits": 0,
        "signal_exits": 0,
        "heartbeat_gaps": 0,
        "errors": [],
    }

    log_files = sorted(date_dir.glob("*.log")) if date_dir.exists() else []
    # Also include the active log
    active_log = LOGS_DIR / "freqtrade.log"
    if active_log.exists():
        log_files.append(active_log)

    prev_timestamp = None
    for log_file in log_files:
        for line in log_file.read_text(errors="replace").splitlines():
            # Training completion
            if "Done training" in line:
                metrics["retrains"] += 1
                m = re.search(r"\((\d+\.?\d*) secs?\)", line)
                if m:
                    metrics["total_training_time"] += float(m.group(1))

            # NaN drops
            if "prediction data points due to NaNs" in line:
                metrics["nan_drop_lines"] += 1
                m = re.search(r"dropped (\d+) of (\d+)", line)
                if m:
                    metrics["nan_dropped_points"] += int(m.group(1))
                    metrics["nan_total_points"] += int(m.group(2))

            # Entry signals
            if "Long signal found" in line or "Short signal found" in line:
                metrics["entry_signals"] += 1

            # Exit reasons
            if "exit_signal" in line.lower() and "Exiting" in line:
                metrics["signal_exits"] += 1
            if "stop_loss" in line.lower() and "Exiting" in line:
                metrics["stoploss_exits"] += 1
            if "trailing_stop_loss" in line.lower() and "Exiting" in line:
                metrics["trailing_stop_exits"] += 1
            if "roi" in line.lower() and "Exiting" in line:
                metrics["roi_exits"] += 1

            # Heartbeat gap detection
            ts_match = re.match(
                r"freqtrade-\d+\s+\|\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line
            )
            if ts_match:
                try:
                    ts = datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S")
                    if prev_timestamp and (ts - prev_timestamp).total_seconds() > 300:
                        metrics["heartbeat_gaps"] += 1
                    prev_timestamp = ts
                except ValueError:
                    pass

            # Errors
            if "ERROR" in line or "Exception" in line:
                metrics["errors"].append(line.strip()[:200])

    return metrics


def generate_report(date_str, token):
    """Generate the daily markdown report."""
    # Query API
    try:
        profit = api_get("/profit", token)
        trades = api_get("/trades?limit=100", token)
        performance = api_get("/performance", token)
        balance = api_get("/balance", token)
        status = api_get("/status", token)
    except requests.RequestException as e:
        return f"# Daily Report — {date_str}\n\nAPI Error: {e}\n"

    # Parse logs
    metrics = parse_logs(date_str)

    # Build report
    lines = []
    lines.append(f"# Daily Report — {date_str}\n")

    # Portfolio Summary
    total_balance = balance.get("total", 0)
    profit_all = profit.get("profit_all_coin", 0)
    profit_pct = profit.get("profit_all_ratio", 0) * 100 if profit.get("profit_all_ratio") else 0
    trade_count = profit.get("trade_count", 0)
    closed_count = profit.get("closed_trade_count", 0)
    open_count = len(status) if isinstance(status, list) else 0
    winning = profit.get("winning_trades", 0)
    losing = profit.get("losing_trades", 0)
    win_rate = (winning / closed_count * 100) if closed_count > 0 else 0

    lines.append("## Portfolio Summary")
    lines.append(f"- Current balance: ${total_balance:.2f}")
    lines.append(f"- Total P&L: ${profit_all:.2f} ({profit_pct:.2f}%)")
    lines.append(f"- Open trades: {open_count} | Closed trades: {closed_count}")
    lines.append(f"- Winning: {winning} | Losing: {losing} | Win rate: {win_rate:.1f}%")
    lines.append("")

    # Open Trades
    if isinstance(status, list) and status:
        lines.append("## Open Trades")
        lines.append("| Pair | Entry Price | Current Price | P&L % | P&L $ | Duration |")
        lines.append("|---|---|---|---|---|---|")
        for t in status:
            pair = t.get("pair", "?")
            entry = t.get("open_rate", 0)
            current = t.get("current_rate", 0)
            pnl_pct = t.get("profit_pct", 0)
            pnl_abs = t.get("profit_abs", 0)
            duration = t.get("trade_duration", "?")
            lines.append(f"| {pair} | ${entry:.4f} | ${current:.4f} | {pnl_pct:.2f}% | ${pnl_abs:.2f} | {duration} |")
        lines.append("")

    # Closed Trades Today
    trade_list = trades.get("trades", []) if isinstance(trades, dict) else trades
    today_trades = [
        t for t in trade_list
        if t.get("close_date", "").startswith(date_str)
    ]
    if today_trades:
        lines.append("## Closed Trades Today")
        lines.append("| Pair | Entry | Exit | P&L % | P&L $ | Duration | Exit Reason |")
        lines.append("|---|---|---|---|---|---|---|")
        for t in today_trades:
            pair = t.get("pair", "?")
            entry = t.get("open_rate", 0)
            exit_p = t.get("close_rate", 0)
            pnl_pct = t.get("profit_pct", 0)
            pnl_abs = t.get("profit_abs", 0)
            duration = t.get("trade_duration", "?")
            reason = t.get("exit_reason", "?")
            lines.append(f"| {pair} | ${entry:.4f} | ${exit_p:.4f} | {pnl_pct:.2f}% | ${pnl_abs:.2f} | {duration} | {reason} |")
        lines.append("")

    # Per-Pair Performance
    if isinstance(performance, list) and performance:
        lines.append("## Per-Pair Performance (cumulative)")
        lines.append("| Pair | Trades | Avg Profit | Total P&L |")
        lines.append("|---|---|---|---|")
        for p in performance:
            pair = p.get("pair", "?")
            count = p.get("count", 0)
            avg = p.get("profit", 0)
            total = p.get("profit_abs", 0)
            lines.append(f"| {pair} | {count} | {avg:.2f}% | ${total:.2f} |")
        lines.append("")

    # Model Metrics
    nan_rate = (
        (metrics["nan_dropped_points"] / metrics["nan_total_points"] * 100)
        if metrics["nan_total_points"] > 0
        else 0
    )
    lines.append("## Model Metrics (from logs)")
    lines.append(f"- Training time: {metrics['total_training_time']:.1f}s")
    lines.append(f"- Retrains today: {metrics['retrains']}")
    lines.append(f"- NaN drop rate: {nan_rate:.1f}%")
    lines.append(f"- Entry signals: {metrics['entry_signals']}")
    lines.append(f"- Stoploss exits: {metrics['stoploss_exits']}")
    lines.append(f"- Trailing stop exits: {metrics['trailing_stop_exits']}")
    lines.append(f"- ROI exits: {metrics['roi_exits']}")
    lines.append(f"- ML signal exits: {metrics['signal_exits']}")
    lines.append("")

    # Flags
    flags = []
    if metrics["heartbeat_gaps"] > 0:
        flags.append(f"WARNING: {metrics['heartbeat_gaps']} heartbeat gap(s) detected (>5 min silence — possible sleep/crash)")
    if metrics["stoploss_exits"] > 2:
        flags.append(f"ATTENTION: {metrics['stoploss_exits']} stoploss exits today — review entry timing")
    if nan_rate > 30:
        flags.append(f"WARNING: NaN drop rate {nan_rate:.1f}% is high (>30%) — check indicator periods vs training data")
    if metrics["errors"]:
        flags.append(f"ERRORS: {len(metrics['errors'])} error(s) in logs")
        for err in metrics["errors"][:5]:
            flags.append(f"  - {err}")
    if not flags:
        flags.append("No issues detected.")

    lines.append("## Flags")
    for flag in flags:
        lines.append(f"- {flag}")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate daily trading report")
    parser.add_argument(
        "--date",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Date to report on (YYYY-MM-DD, default: today)",
    )
    args = parser.parse_args()

    # Authenticate
    try:
        creds = load_config()
        token = get_api_token(creds)
    except FileNotFoundError:
        print(f"Error: Config file not found at {CONFIG_FILE}", file=sys.stderr)
        sys.exit(1)
    except requests.RequestException as e:
        print(f"Error: Cannot connect to Freqtrade API at {API_BASE}: {e}", file=sys.stderr)
        print("Is the bot running? Check: docker compose ps", file=sys.stderr)
        sys.exit(1)

    # Generate report
    report = generate_report(args.date, token)

    # Save
    report_dir = LOGS_DIR / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / f"{args.date}-daily.md"
    report_file.write_text(report)

    print(f"Report saved to {report_file}")
    print(report)


if __name__ == "__main__":
    main()
```

**Step 3: Make executable**

```bash
chmod +x scripts/daily-report.py
```

**Step 4: Test the script manually**

Make sure the bot is running, then:

```bash
source .venv/bin/activate && python3 scripts/daily-report.py
```

Expected: report prints to stdout and is saved to `logs/reports/YYYY-MM-DD-daily.md`.

If the API is unreachable, the script should print an error message and exit with code 1.

**Step 5: Commit**

```bash
git add scripts/daily-report.py
git commit -m "feat: add daily performance report generator"
```

---

### Task 4: Cron setup

**Files:**
- Create: `scripts/setup-cron.sh` (helper to install cron entries)

**Step 1: Write the cron setup helper**

Create `scripts/setup-cron.sh`:

```bash
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

echo ""
echo "Current crontab:"
crontab -l
echo ""
echo "Done. Cron entries installed."
```

**Step 2: Make executable**

```bash
chmod +x scripts/setup-cron.sh
```

**Step 3: Run the setup**

```bash
./scripts/setup-cron.sh
```

Expected output: both cron entries installed and displayed.

**Step 4: Verify cron is working**

```bash
crontab -l
```

Expected: two entries visible — one for rotation (every 2h), one for daily report (23:59).

**Step 5: Commit**

```bash
git add scripts/setup-cron.sh
git commit -m "feat: add cron setup script for log rotation and daily reports"
```

---

### Task 5: Update documentation

**Files:**
- Modify: `docs/operations/monitoring.md`
- Modify: `docs/operations/running-the-bot.md`

**Step 1: Add log rotation section to monitoring.md**

Add after the "Reading Logs" section:

```markdown
## Log Rotation

Logs are automatically rotated every 2 hours into daily folders:

```
logs/
  freqtrade.log              ← active log (Freqtrade writes here)
  2026-03-08/
    2026-03-08_18-00_to_20-00.log
    2026-03-08_20-00_to_22-00.log
    ...12 files per day
  reports/
    2026-03-08-daily.md      ← auto-generated daily report
```

### Manual Commands

- **Run rotation now**: `./scripts/rotate-logs.sh`
- **Generate today's report**: `source .venv/bin/activate && python3 scripts/daily-report.py`
- **Generate report for a specific date**: `python3 scripts/daily-report.py --date 2026-03-08`
- **Check cron is running**: `crontab -l`
- **Check rotation history**: `cat logs/rotation.log`

### Daily Reports

Auto-generated at 23:59. Contains:
- Portfolio summary (balance, P&L, win rate)
- Open and closed trades with entry/exit prices
- Per-pair performance
- Model metrics (training time, NaN rate, signal counts)
- Flags (heartbeat gaps, frequent stoploss hits, errors)

Share these reports with Claude to analyze model performance and plan parameter improvements.
```

**Step 2: Add log file note to running-the-bot.md**

Add to the docker-compose.yml structure section:

```markdown
- **Log file**: `--logfile user_data/logs/freqtrade.log` — writes to both stdout AND a file for rotation
```

**Step 3: Commit**

```bash
git add docs/operations/monitoring.md docs/operations/running-the-bot.md
git commit -m "docs: add log rotation and daily report documentation"
```

---

### Task 6: macOS sleep prevention documentation

**Files:**
- Modify: `docs/operations/running-the-bot.md`

**Step 1: Add sleep prevention section**

Add to running-the-bot.md:

```markdown
## Keeping the Bot Running 24/7 (macOS)

Docker pauses when macOS enters system sleep. To prevent this:

1. **System Settings → Battery → Options**
2. Enable **"Prevent automatic sleeping when the display is off"**
3. Keep your Mac **plugged in**

The display can dim, lock, or show a screensaver — that's fine. Only full system sleep stops Docker.

This is a temporary setup until the bot is moved to a VPS. The log rotation script detects gaps in heartbeat messages and flags them in the daily report.
```

**Step 2: Commit**

```bash
git add docs/operations/running-the-bot.md
git commit -m "docs: add macOS sleep prevention guide"
```
