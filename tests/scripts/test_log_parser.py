import pytest
from scripts.report.log_parser import parse_log_content

SAMPLE_TRAINING_LOG = """\
2026-03-08 21:34:19,580 - freqtrade.freqai.base_models.BaseRegressionModel - INFO - -------------------- Starting training BTC/USDT --------------------
2026-03-08 21:34:19,593 - freqtrade.freqai.data_kitchen - INFO - BTC/USDT: dropped 129 training points due to NaNs in populated dataset 719.
2026-03-08 21:34:20,149 - datasieve.pipeline - INFO - DI tossed 21 predictions for being too far from training data.
2026-03-08 21:34:20,157 - freqtrade.freqai.base_models.BaseRegressionModel - INFO - Training model on 290 features
2026-03-08 21:34:20,161 - freqtrade.freqai.base_models.BaseRegressionModel - INFO - Training model on 395 data points
2026-03-08 21:34:44,156 - freqtrade.freqai.base_models.BaseRegressionModel - INFO - -------------------- Done training BTC/USDT (24.57 secs) --------------------
2026-03-08 21:35:08,968 - freqtrade.freqai.base_models.BaseRegressionModel - INFO - -------------------- Starting training ETH/USDT --------------------
2026-03-08 21:35:08,973 - freqtrade.freqai.data_kitchen - INFO - ETH/USDT: dropped 129 training points due to NaNs in populated dataset 719.
2026-03-08 21:35:09,219 - datasieve.pipeline - INFO - DI tossed 5 predictions for being too far from training data.
2026-03-08 21:35:09,223 - freqtrade.freqai.base_models.BaseRegressionModel - INFO - Training model on 434 features
2026-03-08 21:35:09,223 - freqtrade.freqai.base_models.BaseRegressionModel - INFO - Training model on 395 data points
2026-03-08 21:35:30,000 - freqtrade.freqai.base_models.BaseRegressionModel - INFO - -------------------- Done training ETH/USDT (21.03 secs) --------------------
"""


def test_parse_training_metrics():
    result = parse_log_content(SAMPLE_TRAINING_LOG)
    training = result["training"]

    assert training["total_retrains"] == 2
    assert abs(training["total_time"] - 45.60) < 0.01

    btc = training["per_pair"]["BTC/USDT"]
    assert btc["time"] == 24.57
    assert btc["nan_dropped"] == 129
    assert btc["nan_total"] == 719
    assert btc["di_tossed"] == 21
    assert btc["features"] == 290
    assert btc["data_points"] == 395

    eth = training["per_pair"]["ETH/USDT"]
    assert eth["time"] == 21.03
    assert eth["di_tossed"] == 5
    assert eth["features"] == 434


SAMPLE_SIGNALS_LOG = """\
2026-03-08 22:00:07,650 - AICryptoStrategy - INFO - Allocating BTC/USDT: weight=0.091, base=$90.91, risk_cap=$0.00, final=$90.91
2026-03-08 22:00:07,651 - freqtrade.freqtradebot - INFO - Long signal found: about create a new trade for BTC/USDT with stake_amount: 90.91 and price: 66939.5 ...
2026-03-08 22:00:08,676 - freqtrade.freqtradebot - INFO - Order dry_run_buy_BTC/USDT_1773007207.65213 was created for BTC/USDT and status is closed.
2026-03-08 22:00:09,733 - AICryptoStrategy - INFO - Allocating ETH/USDT: weight=0.091, base=$90.91, risk_cap=$0.00, final=$90.91
2026-03-08 22:00:09,735 - freqtrade.freqtradebot - INFO - Long signal found: about create a new trade for ETH/USDT with stake_amount: 90.91 and price: 1948.97 ...
2026-03-08 22:00:10,749 - freqtrade.freqtradebot - INFO - Order dry_run_buy_ETH/USDT_1773007209.736057 was created for ETH/USDT and status is open.
"""

SAMPLE_HEALTH_LOG = """\
2026-03-08 21:34:22,078 - freqtrade.worker - INFO - Bot heartbeat. PID=1, version='2026.2', state='RUNNING'
2026-03-08 21:35:22,099 - freqtrade.worker - INFO - Bot heartbeat. PID=1, version='2026.2', state='RUNNING'
2026-03-08 21:42:22,145 - freqtrade.worker - INFO - Bot heartbeat. PID=1, version='2026.2', state='RUNNING'
2026-03-08 21:43:00,000 - freqtrade.strategy.strategy_wrapper - ERROR - Unexpected error FileNotFoundError
"""


def test_parse_signals():
    result = parse_log_content(SAMPLE_SIGNALS_LOG)
    signals = result["signals"]
    assert signals["entry_signals"]["BTC/USDT"] == 1
    assert signals["entry_signals"]["ETH/USDT"] == 1
    assert signals["orders_created"]["BTC/USDT"] == 1


def test_parse_allocations():
    result = parse_log_content(SAMPLE_SIGNALS_LOG)
    alloc = result["allocations"]
    assert alloc["BTC/USDT"]["weight"] == 0.091
    assert alloc["BTC/USDT"]["final"] == 90.91
    assert alloc["ETH/USDT"]["weight"] == 0.091


def test_parse_health_heartbeat_gap():
    result = parse_log_content(SAMPLE_HEALTH_LOG)
    health = result["health"]
    # 21:35 to 21:42 = 7 min gap > 5 min threshold
    assert health["heartbeat_gaps"] == 1
    assert health["heartbeat_count"] == 3
    assert health["bot_version"] == "2026.2"


def test_parse_health_errors():
    result = parse_log_content(SAMPLE_HEALTH_LOG)
    health = result["health"]
    assert len(health["errors"]) == 1
    assert "FileNotFoundError" in health["errors"][0]


def test_parse_health_timestamps():
    result = parse_log_content(SAMPLE_HEALTH_LOG)
    health = result["health"]
    assert health["first_timestamp"] == "2026-03-08 21:34:22"
    assert health["last_timestamp"] == "2026-03-08 21:43:00"
