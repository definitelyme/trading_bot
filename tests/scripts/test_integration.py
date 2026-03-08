"""Integration tests for the full two-hour report pipeline.

Tests the end-to-end flow: log rotation → log parsing → report generation,
with the API mocked out (since we can't rely on a live Freqtrade instance).
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime

from scripts.report.log_parser import parse_log_content
from scripts.report.generator import generate_two_hour_report
from scripts.report.rotation import rotate_log, compute_window_names

# Realistic log content combining training, signals, allocations, and health
REALISTIC_LOG = """\
2026-03-08 20:00:05,123 - freqtrade.worker - INFO - Bot heartbeat. PID=1, version='2026.2', state='RUNNING'
2026-03-08 20:01:05,456 - freqtrade.worker - INFO - Bot heartbeat. PID=1, version='2026.2', state='RUNNING'
2026-03-08 20:34:19,580 - freqtrade.freqai.base_models.BaseRegressionModel - INFO - -------------------- Starting training BTC/USDT --------------------
2026-03-08 20:34:19,593 - freqtrade.freqai.data_kitchen - INFO - BTC/USDT: dropped 129 training points due to NaNs in populated dataset 719.
2026-03-08 20:34:20,149 - datasieve.pipeline - INFO - DI tossed 21 predictions for being too far from training data.
2026-03-08 20:34:20,157 - freqtrade.freqai.base_models.BaseRegressionModel - INFO - Training model on 290 features
2026-03-08 20:34:20,161 - freqtrade.freqai.base_models.BaseRegressionModel - INFO - Training model on 395 data points
2026-03-08 20:34:44,156 - freqtrade.freqai.base_models.BaseRegressionModel - INFO - -------------------- Done training BTC/USDT (24.57 secs) --------------------
2026-03-08 20:35:08,968 - freqtrade.freqai.base_models.BaseRegressionModel - INFO - -------------------- Starting training ETH/USDT --------------------
2026-03-08 20:35:08,973 - freqtrade.freqai.data_kitchen - INFO - ETH/USDT: dropped 129 training points due to NaNs in populated dataset 719.
2026-03-08 20:35:09,219 - datasieve.pipeline - INFO - DI tossed 5 predictions for being too far from training data.
2026-03-08 20:35:09,223 - freqtrade.freqai.base_models.BaseRegressionModel - INFO - Training model on 434 features
2026-03-08 20:35:09,223 - freqtrade.freqai.base_models.BaseRegressionModel - INFO - Training model on 395 data points
2026-03-08 20:35:30,000 - freqtrade.freqai.base_models.BaseRegressionModel - INFO - -------------------- Done training ETH/USDT (21.03 secs) --------------------
2026-03-08 21:00:07,650 - AICryptoStrategy - INFO - Allocating BTC/USDT: weight=0.091, base=$90.91, risk_cap=$0.00, final=$90.91
2026-03-08 21:00:07,651 - freqtrade.freqtradebot - INFO - Long signal found: about create a new trade for BTC/USDT with stake_amount: 90.91 and price: 66939.5 ...
2026-03-08 21:00:08,676 - freqtrade.freqtradebot - INFO - Order dry_run_buy_BTC/USDT_1773007207.65213 was created for BTC/USDT and status is closed.
2026-03-08 21:00:09,733 - AICryptoStrategy - INFO - Allocating ETH/USDT: weight=0.091, base=$90.91, risk_cap=$0.00, final=$90.91
2026-03-08 21:59:55,789 - freqtrade.worker - INFO - Bot heartbeat. PID=1, version='2026.2', state='RUNNING'
"""

SAMPLE_API_DATA = {
    "profit": {
        "profit_all_coin": -10.75,
        "profit_all_ratio": -0.01075,
        "trade_count": 8,
        "closed_trade_count": 2,
        "winning_trades": 1,
        "losing_trades": 1,
        "max_drawdown": 0.02,
        "max_drawdown_abs": 20.0,
        "bot_start_date": "2026-03-08 18:00:00",
    },
    "balance": {"total": 989.25, "free": 272.0},
    "status": [
        {
            "pair": "BTC/USDT",
            "open_rate": 66939.5,
            "current_rate": 65800.0,
            "profit_pct": -1.70,
            "profit_abs": -1.55,
            "trade_duration": "2:15:00",
            "enter_tag": "",
        },
    ],
    "trades": {
        "trades": [
            {
                "pair": "BTC/USDT",
                "open_date": "2026-03-08 21:00:08",
                "close_date": None,
                "open_rate": 66939.5,
                "close_rate": None,
                "profit_pct": -1.70,
                "profit_abs": -1.55,
                "trade_duration": "2:15:00",
                "exit_reason": None,
                "is_short": False,
            },
        ],
    },
}


class TestFullPipeline:
    """End-to-end: rotation → parsing → report generation."""

    def test_rotate_parse_generate(self, tmp_path):
        """Full pipeline: write log, rotate it, parse the snapshot, generate report."""
        # Setup: write a realistic log file
        log_file = tmp_path / "freqtrade.log"
        log_file.write_text(REALISTIC_LOG)

        snapshot_dir = tmp_path / "2026-03-08"

        # Step 1: Rotate
        snapshot_path = rotate_log(
            log_file=log_file,
            snapshot_dir=snapshot_dir,
            snapshot_name="2026-03-08_20-00_to_22-00.log",
        )
        assert snapshot_path is not None
        assert snapshot_path.exists()
        assert log_file.read_text() == ""  # truncated

        # Step 2: Parse the rotated snapshot
        log_text = snapshot_path.read_text()
        metrics = parse_log_content(log_text)

        # Verify training parsed correctly
        assert metrics["training"]["total_retrains"] == 2
        assert "BTC/USDT" in metrics["training"]["per_pair"]
        assert "ETH/USDT" in metrics["training"]["per_pair"]

        # Verify signals parsed
        assert metrics["signals"]["entry_signals"]["BTC/USDT"] == 1
        assert metrics["signals"]["orders_created"]["BTC/USDT"] == 1

        # Verify allocations parsed
        assert metrics["allocations"]["BTC/USDT"]["weight"] == 0.091
        assert metrics["allocations"]["ETH/USDT"]["weight"] == 0.091

        # Verify health parsed
        assert metrics["health"]["heartbeat_count"] == 3
        assert metrics["health"]["bot_version"] == "2026.2"
        assert metrics["health"]["first_timestamp"] == "2026-03-08 20:00:05"
        assert metrics["health"]["last_timestamp"] == "2026-03-08 21:59:55"

        # Step 3: Generate report
        report = generate_two_hour_report(
            window_start="20:00",
            window_end="22:00",
            date_str="2026-03-08",
            api_data=SAMPLE_API_DATA,
            log_metrics=metrics,
        )

        # Verify all sections present
        assert "# 2-Hour Report" in report
        assert "Portfolio Snapshot" in report
        assert "Open Trades" in report
        assert "Per-Pair Signal Activity" in report
        assert "Model Training Summary" in report
        assert "Risk & Position Sizing" in report
        assert "Flags" in report
        assert "Raw Metrics" in report

        # Verify actual data shows up in report
        assert "BTC/USDT" in report
        assert "ETH/USDT" in report
        assert "$989.25" in report
        assert "24.6s" in report  # BTC training time
        assert "2026.2" in report  # bot version

    def test_pipeline_with_api_failure(self, tmp_path):
        """Pipeline works gracefully when API is unavailable (log-only report)."""
        log_file = tmp_path / "freqtrade.log"
        log_file.write_text(REALISTIC_LOG)
        snapshot_dir = tmp_path / "2026-03-08"

        # Rotate
        snapshot_path = rotate_log(
            log_file=log_file,
            snapshot_dir=snapshot_dir,
            snapshot_name="test.log",
        )

        # Parse
        metrics = parse_log_content(snapshot_path.read_text())

        # Simulate API failure fallback data
        fallback_api_data = {
            "profit": {},
            "balance": {},
            "status": [],
            "trades": {"trades": []},
        }

        # Generate report with fallback data
        report = generate_two_hour_report(
            window_start="20:00",
            window_end="22:00",
            date_str="2026-03-08",
            api_data=fallback_api_data,
            log_metrics=metrics,
        )

        # Report should still have all sections
        assert "# 2-Hour Report" in report
        assert "No open trades" in report
        assert "Model Training Summary" in report
        assert "BTC/USDT" in report  # from log metrics

    def test_pipeline_empty_log(self, tmp_path):
        """Pipeline handles empty log file (rotation returns None)."""
        log_file = tmp_path / "freqtrade.log"
        log_file.write_text("")

        result = rotate_log(
            log_file=log_file,
            snapshot_dir=tmp_path / "2026-03-08",
            snapshot_name="test.log",
        )
        assert result is None

    def test_pipeline_missing_log(self, tmp_path):
        """Pipeline handles missing log file (rotation returns None)."""
        log_file = tmp_path / "nonexistent.log"

        result = rotate_log(
            log_file=log_file,
            snapshot_dir=tmp_path / "2026-03-08",
            snapshot_name="test.log",
        )
        assert result is None

    def test_report_saved_to_correct_location(self, tmp_path):
        """Verify report file is written next to the snapshot."""
        log_file = tmp_path / "freqtrade.log"
        log_file.write_text(REALISTIC_LOG)

        date_str = "2026-03-08"
        snapshot_dir = tmp_path / date_str

        # Rotate
        snapshot_path = rotate_log(
            log_file=log_file,
            snapshot_dir=snapshot_dir,
            snapshot_name=f"{date_str}_20-00_to_22-00.log",
        )

        # Parse + generate
        metrics = parse_log_content(snapshot_path.read_text())
        report = generate_two_hour_report(
            window_start="20:00",
            window_end="22:00",
            date_str=date_str,
            api_data=SAMPLE_API_DATA,
            log_metrics=metrics,
        )

        # Save report
        report_path = snapshot_dir / f"{date_str}_20-00_to_22-00-report.md"
        report_path.write_text(report)

        # Verify both files exist side-by-side
        assert snapshot_path.exists()
        assert report_path.exists()
        assert snapshot_path.parent == report_path.parent
        assert report_path.read_text().startswith("# 2-Hour Report")


class TestWindowComputation:
    """Integration tests for window naming across edge cases."""

    def test_all_even_hours(self):
        """Every even hour produces valid window names."""
        for hour in range(0, 24, 2):
            date_str, start, end = compute_window_names(hour=hour)
            assert len(start) == 2
            assert len(end) == 2
            assert int(end) == hour or (hour == 0 and end == "00")

    def test_odd_hours_round_down(self):
        """Odd hours round down to even window end."""
        _, start, end = compute_window_names(hour=15)
        assert end == "14"
        assert start == "12"

    def test_midnight_uses_yesterday(self):
        """Hour 0 window dates to yesterday."""
        now = datetime(2026, 3, 9, 0, 0, 0)
        date_str, start, end = compute_window_names(hour=0, now=now)
        assert date_str == "2026-03-08"
        assert start == "22"
        assert end == "00"

    def test_hour_2_uses_today(self):
        """Hour 2 window dates to today."""
        now = datetime(2026, 3, 9, 2, 0, 0)
        date_str, start, end = compute_window_names(hour=2, now=now)
        assert date_str == "2026-03-09"
        assert start == "00"
        assert end == "02"
