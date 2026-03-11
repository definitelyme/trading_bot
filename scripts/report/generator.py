"""Generate detailed 2-hour markdown report."""
from datetime import datetime


def generate_two_hour_report(
    window_start: str,
    window_end: str,
    date_str: str,
    api_data: dict,
    log_metrics: dict,
) -> str:
    """Build the full markdown report from API data + parsed log metrics."""
    lines: list[str] = []
    profit = api_data["profit"]
    balance = api_data["balance"]
    status = api_data["status"]
    trades = api_data["trades"]
    training = log_metrics["training"]
    signals = log_metrics["signals"]
    allocations = log_metrics["allocations"]
    health = log_metrics["health"]

    # --- Header ---
    lines.append(f"# 2-Hour Report — {date_str} {window_start} to {window_end}")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}")
    lines.append(f"Bot version: {health.get('bot_version', '?')}")
    lines.append(f"Log window: {health.get('first_timestamp', '?')} → {health.get('last_timestamp', '?')}")
    lines.append("")

    # --- Portfolio Snapshot ---
    total_bal = balance.get("total", 0)
    free_bal = balance.get("free", 0)
    pnl = profit.get("profit_all_coin", 0)
    pnl_pct = (profit.get("profit_all_ratio") or 0) * 100
    open_count = len(status) if isinstance(status, list) else 0
    max_trades = profit.get("trade_count", 0)
    closed = profit.get("closed_trade_count", 0)
    winning = profit.get("winning_trades", 0)
    losing = profit.get("losing_trades", 0)
    win_rate = (winning / closed * 100) if closed > 0 else 0
    unrealized = sum(t.get("profit_abs", 0) for t in status) if isinstance(status, list) else 0
    max_dd = profit.get("max_drawdown_abs", 0)

    lines.append("## Portfolio Snapshot")
    lines.append(f"- Balance: **${total_bal:.2f}** (available: ${free_bal:.2f})")
    lines.append(f"- Total P&L: **${pnl:.2f}** ({pnl_pct:+.2f}%)")
    lines.append(f"- Unrealized P&L: ${unrealized:.2f}")
    lines.append(f"- Open trades: {open_count} | Closed: {closed} | Total: {max_trades}")
    lines.append(f"- Win/Loss: {winning}W / {losing}L ({win_rate:.0f}% win rate)")
    lines.append(f"- Max drawdown: ${max_dd:.2f}")
    lines.append("")

    # --- Open Trades ---
    lines.append("## Open Trades")
    if isinstance(status, list) and status:
        lines.append("| Pair | Entry Price | Current Price | P&L % | P&L $ | Duration | Tag |")
        lines.append("|---|---|---|---|---|---|---|")
        for t in sorted(status, key=lambda x: x.get("profit_abs", 0)):
            lines.append(
                f"| {t.get('pair', '?')} "
                f"| ${t.get('open_rate', 0):.4f} "
                f"| ${t.get('current_rate', 0):.4f} "
                f"| {t.get('profit_pct', 0):+.2f}% "
                f"| ${t.get('profit_abs', 0):+.2f} "
                f"| {t.get('trade_duration', '?')} "
                f"| {t.get('enter_tag', '') or '-'} |"
            )
    else:
        lines.append("No open trades.")
    lines.append("")

    # --- Trades This Window ---
    trade_list = trades.get("trades", []) if isinstance(trades, dict) else trades
    window_trades = [
        t for t in trade_list
        if (t.get("open_date", "") or "").startswith(date_str)
        or (t.get("close_date", "") or "").startswith(date_str)
    ]
    lines.append("## Trades This Window")
    if window_trades:
        lines.append("| Pair | Dir | Entry | Exit | P&L % | P&L $ | Duration | Exit Reason |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for t in window_trades:
            direction = "Short" if t.get("is_short") else "Long"
            exit_price = t.get("close_rate") or 0
            exit_str = f"${exit_price:.4f}" if exit_price else "(open)"
            reason = t.get("exit_reason") or "(open)"
            lines.append(
                f"| {t.get('pair', '?')} "
                f"| {direction} "
                f"| ${t.get('open_rate', 0):.4f} "
                f"| {exit_str} "
                f"| {t.get('profit_pct', 0):+.2f}% "
                f"| ${t.get('profit_abs', 0):+.2f} "
                f"| {t.get('trade_duration', '?')} "
                f"| {reason} |"
            )
    else:
        lines.append("No trades opened or closed in this window.")
    lines.append("")

    # --- Per-Pair Signal Activity ---
    all_pairs = sorted(set(
        list(training.get("per_pair", {}).keys())
        + list(signals.get("entry_signals", {}).keys())
        + list(allocations.keys())
    ))
    lines.append("## Per-Pair Signal Activity")
    if all_pairs:
        lines.append("| Pair | Entry Signals | Orders | Exits | Training Time | DI Tossed | NaN Drop % |")
        lines.append("|---|---|---|---|---|---|---|")
        for pair in all_pairs:
            entry_sig = signals.get("entry_signals", {}).get(pair, 0)
            orders = signals.get("orders_created", {}).get(pair, 0)
            pair_exits = signals.get("exits", {}).get(pair, [])
            exit_count = len(pair_exits)
            t_info = training.get("per_pair", {}).get(pair, {})
            t_time = t_info.get("time", 0)
            di = t_info.get("di_tossed", 0)
            nan_d = t_info.get("nan_dropped", 0)
            nan_t = t_info.get("nan_total", 1)
            nan_pct = (nan_d / nan_t * 100) if nan_t > 0 else 0
            lines.append(
                f"| {pair} | {entry_sig} | {orders} | {exit_count} "
                f"| {t_time:.1f}s | {di} | {nan_pct:.1f}% |"
            )
    else:
        lines.append("No pair activity in this window.")
    lines.append("")

    # --- Model Training Summary ---
    lines.append("## Model Training Summary")
    lines.append(f"- Retrains this window: **{training['total_retrains']}**")
    lines.append(f"- Total training time: **{training['total_time']:.1f}s**")
    avg_time = training["total_time"] / training["total_retrains"] if training["total_retrains"] > 0 else 0
    lines.append(f"- Avg time per pair: {avg_time:.1f}s")
    lines.append("")
    if training.get("per_pair"):
        lines.append("| Pair | Time | Features | Data Points | NaN Dropped | NaN Total | NaN % | DI Tossed |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for pair, info in sorted(training["per_pair"].items()):
            nan_pct = (info["nan_dropped"] / info["nan_total"] * 100) if info["nan_total"] > 0 else 0
            lines.append(
                f"| {pair} | {info['time']:.1f}s | {info['features']} | {info['data_points']} "
                f"| {info['nan_dropped']} | {info['nan_total']} | {nan_pct:.1f}% | {info['di_tossed']} |"
            )
    lines.append("")

    # --- Risk & Position Sizing ---
    lines.append("## Risk & Position Sizing")
    if allocations:
        lines.append("| Pair | Weight | ATR% | Final Stake |")
        lines.append("|---|---|---|---|")
        for pair, alloc in sorted(allocations.items()):
            lines.append(
                f"| {pair} | {alloc['weight']:.3f} "
                f"| {alloc['atr'] * 100:.1f}% "
                f"| ${alloc['final']:.2f} |"
            )
    else:
        lines.append("No allocation data in this window.")
    lines.append("")

    # Exit reason summary
    all_exits = {}
    for pair, reasons in signals.get("exits", {}).items():
        for r in reasons:
            all_exits[r] = all_exits.get(r, 0) + 1
    if all_exits:
        lines.append("**Exit reasons this window:**")
        for reason, count in sorted(all_exits.items(), key=lambda x: -x[1]):
            lines.append(f"- {reason}: {count}")
        lines.append("")

    # --- Flags & Recommendations ---
    lines.append("## Flags & Recommendations")
    flags: list[str] = []

    if health["heartbeat_gaps"] > 0:
        flags.append(f"WARNING: {health['heartbeat_gaps']} heartbeat gap(s) detected (>5 min silence)")

    if health["errors"]:
        flags.append(f"ERRORS: {len(health['errors'])} error(s) in logs")
        for err in health["errors"][:5]:
            flags.append(f"  - `{err[:150]}`")

    # Per-pair flags
    for pair, info in training.get("per_pair", {}).items():
        nan_pct = (info["nan_dropped"] / info["nan_total"] * 100) if info["nan_total"] > 0 else 0
        if nan_pct > 20:
            flags.append(f"WARNING: {pair} NaN drop rate {nan_pct:.0f}% (>20%) — check indicator warmup")
        if info["di_tossed"] > 50:
            flags.append(f"WARNING: {pair} DI tossed {info['di_tossed']} predictions — model may be stale")

    # Pairs with zero signals
    trained_pairs = set(training.get("per_pair", {}).keys())
    signaling_pairs = set(signals.get("entry_signals", {}).keys())
    silent_pairs = trained_pairs - signaling_pairs
    if silent_pairs:
        flags.append(f"INFO: {len(silent_pairs)} pair(s) with no entry signals: {', '.join(sorted(silent_pairs))}")

    # Stoploss clustering
    for pair, reasons in signals.get("exits", {}).items():
        sl_count = sum(1 for r in reasons if "stop_loss" in r.lower())
        if sl_count >= 2:
            flags.append(f"ATTENTION: {pair} hit stoploss {sl_count}x — review entry timing")

    if not flags:
        flags.append("No issues detected.")

    for flag in flags:
        lines.append(f"- {flag}")
    lines.append("")

    # --- Raw Metrics ---
    lines.append("## Raw Metrics")
    lines.append(f"- Log lines processed: {health['total_lines']}")
    lines.append(f"- Heartbeats: {health['heartbeat_count']}")
    lines.append(f"- First log entry: {health.get('first_timestamp', '?')}")
    lines.append(f"- Last log entry: {health.get('last_timestamp', '?')}")
    lines.append(f"- Bot started: {profit.get('bot_start_date', '?')}")
    lines.append("")

    return "\n".join(lines)
