import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from scripts.report.rotation import rotate_log, compute_window_names


def test_compute_window_names_22():
    """Cron at 22:00 → covers 20:00–22:00."""
    date, start, end = compute_window_names(hour=22)
    assert start == "20"
    assert end == "22"


def test_compute_window_names_00():
    """Cron at 00:00 → covers 22:00–00:00, date is yesterday."""
    date, start, end = compute_window_names(hour=0)
    assert start == "22"
    assert end == "00"


def test_compute_window_names_02():
    """Cron at 02:00 → covers 00:00–02:00."""
    date, start, end = compute_window_names(hour=2)
    assert start == "00"
    assert end == "02"


def test_rotate_log_copies_and_truncates(tmp_path):
    log_file = tmp_path / "freqtrade.log"
    log_file.write_text("line1\nline2\nline3\n")

    snapshot_dir = tmp_path / "2026-03-08"
    snapshot_path = snapshot_dir / "2026-03-08_20-00_to_22-00.log"

    result = rotate_log(
        log_file=log_file,
        snapshot_dir=snapshot_dir,
        snapshot_name="2026-03-08_20-00_to_22-00.log",
    )

    assert result == snapshot_path
    assert snapshot_path.read_text() == "line1\nline2\nline3\n"
    assert log_file.read_text() == ""  # truncated


def test_rotate_log_skips_empty(tmp_path):
    log_file = tmp_path / "freqtrade.log"
    log_file.write_text("")

    result = rotate_log(
        log_file=log_file,
        snapshot_dir=tmp_path / "2026-03-08",
        snapshot_name="test.log",
    )

    assert result is None
