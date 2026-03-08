"""Log rotation: copy + truncate."""
from datetime import datetime, timedelta
from pathlib import Path


def compute_window_names(hour: int | None = None, now: datetime | None = None) -> tuple[str, str, str]:
    """
    Compute the date string and window start/end for the PREVIOUS 2-hour window.

    Returns (date_str, window_start_hour, window_end_hour).
    The window covers [start, end) where end is the current even hour.
    """
    if now is None:
        now = datetime.now()
    if hour is None:
        hour = now.hour

    # Current even hour is the END of the window
    window_end = (hour // 2) * 2
    window_start = window_end - 2

    if window_start < 0:
        # Midnight rollover: window is 22:00–00:00, date is yesterday
        window_start = 22
        window_end = 0
        date_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        date_str = now.strftime("%Y-%m-%d")

    return date_str, f"{window_start:02d}", f"{window_end:02d}"


def rotate_log(log_file: Path, snapshot_dir: Path, snapshot_name: str) -> Path | None:
    """
    Copy log_file to snapshot_dir/snapshot_name, then truncate log_file.
    Returns the snapshot path, or None if log was empty/missing.
    """
    if not log_file.exists() or log_file.stat().st_size == 0:
        return None

    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshot_dir / snapshot_name

    # Copy content
    content = log_file.read_bytes()
    snapshot_path.write_bytes(content)

    # Truncate (Freqtrade holds file handle, keeps writing)
    with open(log_file, "w") as f:
        f.truncate(0)

    return snapshot_path
