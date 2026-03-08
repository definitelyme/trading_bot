#!/usr/bin/env python3
"""
Combined log rotation + 2-hour analytical report.

Runs every 2 hours via cron. Rotates freqtrade.log, parses the snapshot,
queries the API, and generates a detailed markdown report.

Usage: python3 scripts/two-hour-report.py
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

from report.log_parser import parse_log_content
from report.generator import generate_two_hour_report
from report.rotation import compute_window_names, rotate_log

PROJECT_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_DIR / "logs"
LOG_FILE = LOGS_DIR / "freqtrade.log"
CONFIG_FILE = PROJECT_DIR / "user_data" / "config.json"
API_BASE = "http://localhost:8080/api/v1"


def load_auth() -> HTTPBasicAuth:
    with open(CONFIG_FILE) as f:
        config = json.load(f)
    return HTTPBasicAuth(
        config["api_server"]["username"],
        config["api_server"]["password"],
    )


def api_get(endpoint: str, auth: HTTPBasicAuth) -> dict:
    resp = requests.get(f"{API_BASE}{endpoint}", auth=auth, timeout=10)
    resp.raise_for_status()
    return resp.json()


def main():
    now = datetime.now()
    date_str, w_start, w_end = compute_window_names(now=now)

    snapshot_name = f"{date_str}_{w_start}-00_to_{w_end}-00.log"
    report_name = f"{date_str}_{w_start}-00_to_{w_end}-00-report.md"
    snapshot_dir = LOGS_DIR / date_str

    # 1. Rotate log
    snapshot_path = rotate_log(LOG_FILE, snapshot_dir, snapshot_name)
    if snapshot_path is None:
        print(f"[{now}] Log empty or missing, skipping rotation and report")
        return

    print(f"[{now}] Rotated: {snapshot_path}")

    # 2. Parse the rotated log
    log_text = snapshot_path.read_text(errors="replace")
    log_metrics = parse_log_content(log_text)

    # 3. Query API
    try:
        auth = load_auth()
        api_data = {
            "profit": api_get("/profit", auth),
            "balance": api_get("/balance", auth),
            "status": api_get("/status", auth),
            "trades": api_get("/trades?limit=100", auth),
        }
    except (requests.RequestException, FileNotFoundError) as e:
        print(f"[{now}] API error: {e} — generating report with log data only")
        api_data = {
            "profit": {},
            "balance": {},
            "status": [],
            "trades": {"trades": []},
        }

    # 4. Generate report
    report = generate_two_hour_report(
        window_start=f"{w_start}:00",
        window_end=f"{w_end}:00",
        date_str=date_str,
        api_data=api_data,
        log_metrics=log_metrics,
    )

    # 5. Save report
    report_path = snapshot_dir / report_name
    report_path.write_text(report)
    print(f"[{now}] Report: {report_path}")


if __name__ == "__main__":
    # Add scripts/ to sys.path so `from report.x import y` works
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
