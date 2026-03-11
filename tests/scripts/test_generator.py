import pytest
from scripts.report.generator import generate_two_hour_report


@pytest.fixture
def sample_api_data():
    return {
        "profit": {
            "profit_all_coin": -10.75,
            "profit_all_ratio": -0.01075,
            "trade_count": 8,
            "closed_trade_count": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "max_drawdown": 0.0,
            "max_drawdown_abs": 0.0,
            "bot_start_date": "2026-03-08 21:34:14",
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
                    "open_date": "2026-03-08 22:00:08",
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


@pytest.fixture
def sample_log_metrics():
    return {
        "training": {
            "total_retrains": 11,
            "total_time": 285.3,
            "per_pair": {
                "BTC/USDT": {"time": 24.57, "nan_dropped": 129, "nan_total": 719, "di_tossed": 21, "features": 290, "data_points": 395},
                "ETH/USDT": {"time": 22.57, "nan_dropped": 129, "nan_total": 719, "di_tossed": 5, "features": 434, "data_points": 395},
            },
        },
        "signals": {
            "entry_signals": {"BTC/USDT": 1, "ETH/USDT": 1},
            "orders_created": {"BTC/USDT": 1, "ETH/USDT": 1},
            "exits": {},
        },
        "allocations": {
            "BTC/USDT": {"weight": 0.091, "atr": 0.050, "final": 90.91},
        },
        "health": {
            "heartbeat_gaps": 0,
            "heartbeat_count": 24,
            "errors": [],
            "bot_version": "2026.2",
            "first_timestamp": "2026-03-08 20:00:05",
            "last_timestamp": "2026-03-08 21:59:55",
            "total_lines": 2500,
        },
    }


def test_report_contains_all_sections(sample_api_data, sample_log_metrics):
    report = generate_two_hour_report(
        window_start="20:00",
        window_end="22:00",
        date_str="2026-03-08",
        api_data=sample_api_data,
        log_metrics=sample_log_metrics,
    )
    assert "# 2-Hour Report" in report
    assert "Portfolio Snapshot" in report
    assert "Open Trades" in report
    assert "Per-Pair Signal Activity" in report
    assert "Model Training Summary" in report
    assert "Risk & Position Sizing" in report
    assert "Flags" in report
    assert "BTC/USDT" in report


def test_report_flags_errors(sample_api_data, sample_log_metrics):
    sample_log_metrics["health"]["errors"] = ["2026-03-08 ERROR something broke"]
    sample_log_metrics["health"]["heartbeat_gaps"] = 2
    report = generate_two_hour_report(
        window_start="20:00",
        window_end="22:00",
        date_str="2026-03-08",
        api_data=sample_api_data,
        log_metrics=sample_log_metrics,
    )
    assert "WARNING" in report or "ERRORS" in report
    assert "heartbeat gap" in report.lower()


def test_report_no_open_trades(sample_api_data, sample_log_metrics):
    sample_api_data["status"] = []
    report = generate_two_hour_report(
        window_start="20:00",
        window_end="22:00",
        date_str="2026-03-08",
        api_data=sample_api_data,
        log_metrics=sample_log_metrics,
    )
    assert "No open trades" in report
