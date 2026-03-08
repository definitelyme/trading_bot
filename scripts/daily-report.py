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
