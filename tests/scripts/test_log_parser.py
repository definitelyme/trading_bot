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
