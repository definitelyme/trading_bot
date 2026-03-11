"""Parse Freqtrade log content into structured metrics."""
import re
from collections import defaultdict


def parse_log_content(text: str) -> dict:
    """Parse raw log text and return structured metrics dict."""
    lines = text.splitlines()

    training = _parse_training(lines)
    signals = _parse_signals(lines)
    allocations = _parse_allocations(lines)
    health = _parse_health(lines)

    return {
        "training": training,
        "signals": signals,
        "allocations": allocations,
        "health": health,
    }


def _parse_training(lines: list[str]) -> dict:
    per_pair: dict[str, dict] = {}
    current_pair = None
    total_retrains = 0
    total_time = 0.0

    for line in lines:
        # Starting training
        m = re.search(r"Starting training (\S+/\S+)", line)
        if m:
            current_pair = m.group(1)
            per_pair.setdefault(current_pair, {
                "time": 0.0, "nan_dropped": 0, "nan_total": 0,
                "di_tossed": 0, "features": 0, "data_points": 0,
            })
            continue

        # NaN drops (pair-specific line)
        m = re.search(r"(\S+/\S+): dropped (\d+) training points due to NaNs in populated dataset (\d+)", line)
        if m:
            pair = m.group(1)
            per_pair.setdefault(pair, {
                "time": 0.0, "nan_dropped": 0, "nan_total": 0,
                "di_tossed": 0, "features": 0, "data_points": 0,
            })
            per_pair[pair]["nan_dropped"] = int(m.group(2))
            per_pair[pair]["nan_total"] = int(m.group(3))
            continue

        # DI tossed (applies to current_pair being trained)
        m = re.search(r"DI tossed (\d+) predictions", line)
        if m and current_pair and current_pair in per_pair:
            per_pair[current_pair]["di_tossed"] = int(m.group(1))
            continue

        # Feature count
        m = re.search(r"Training model on (\d+) features", line)
        if m and current_pair and current_pair in per_pair:
            per_pair[current_pair]["features"] = int(m.group(1))
            continue

        # Data points
        m = re.search(r"Training model on (\d+) data points", line)
        if m and current_pair and current_pair in per_pair:
            per_pair[current_pair]["data_points"] = int(m.group(1))
            continue

        # Done training
        m = re.search(r"Done training (\S+/\S+) \((\d+\.?\d*) secs?\)", line)
        if m:
            pair = m.group(1)
            secs = float(m.group(2))
            if pair in per_pair:
                per_pair[pair]["time"] = secs
            total_retrains += 1
            total_time += secs
            current_pair = None
            continue

    return {
        "total_retrains": total_retrains,
        "total_time": total_time,
        "per_pair": dict(per_pair),
    }


def _parse_signals(lines: list[str]) -> dict:
    entry_signals: dict[str, int] = defaultdict(int)
    orders_created: dict[str, int] = defaultdict(int)
    exits: dict[str, list[str]] = defaultdict(list)

    for line in lines:
        # Entry signals
        m = re.search(r"Long signal found.*?for (\S+/\S+)", line)
        if m:
            entry_signals[m.group(1)] += 1
            continue

        # Orders created
        m = re.search(r"Order dry_run_(?:buy|sell)_([A-Z]+/[A-Z]+)", line)
        if m:
            orders_created[m.group(1)] += 1
            continue

        # Exits
        if "Exiting" in line:
            pair_m = re.search(r"pair=(\S+/\S+)", line) or re.search(r"for (\S+/\S+)", line)
            reason_m = re.search(r"exit_type=([\w]+)", line) or re.search(r"reason: ([\w]+)", line)
            if pair_m:
                reason = reason_m.group(1) if reason_m else "unknown"
                exits[pair_m.group(1)].append(reason)

    return {
        "entry_signals": dict(entry_signals),
        "orders_created": dict(orders_created),
        "exits": dict(exits),
    }


def _parse_allocations(lines: list[str]) -> dict:
    allocations: dict[str, dict] = {}

    for line in lines:
        m = re.search(
            r"Allocating (\S+/\S+): weight=([\d.]+), atr=([\d.]+), final=\$([\d.]+)",
            line,
        )
        if m:
            allocations[m.group(1)] = {
                "weight": float(m.group(2)),
                "atr": float(m.group(3)),
                "final": float(m.group(4)),
            }

    return allocations


def _parse_health(lines: list[str]) -> dict:
    heartbeat_timestamps = []
    errors = []
    bot_version = None

    for line in lines:
        # Heartbeat
        m = re.search(
            r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*Bot heartbeat.*version='([^']+)'",
            line,
        )
        if m:
            heartbeat_timestamps.append(m.group(1))
            bot_version = m.group(2)
            continue

        # Errors (skip traceback continuation lines)
        if ("ERROR" in line or "Exception" in line) and re.match(r"\d{4}-\d{2}-\d{2}", line):
            errors.append(line.strip()[:300])

    # Detect gaps > 5 min between heartbeats
    heartbeat_gaps = 0
    from datetime import datetime
    prev = None
    for ts_str in heartbeat_timestamps:
        try:
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            if prev and (ts - prev).total_seconds() > 300:
                heartbeat_gaps += 1
            prev = ts
        except ValueError:
            pass

    # First/last timestamp in the entire log
    first_ts = None
    last_ts = None
    for line in lines:
        m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
        if m:
            if first_ts is None:
                first_ts = m.group(1)
            last_ts = m.group(1)

    return {
        "heartbeat_gaps": heartbeat_gaps,
        "heartbeat_count": len(heartbeat_timestamps),
        "errors": errors,
        "bot_version": bot_version,
        "first_timestamp": first_ts,
        "last_timestamp": last_ts,
        "total_lines": len(lines),
    }
