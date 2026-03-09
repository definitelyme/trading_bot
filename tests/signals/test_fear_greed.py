import pytest
from unittest.mock import patch, MagicMock
from user_data.strategies.signals.fear_greed import FearGreedSignal


def test_disabled_returns_none():
    fg = FearGreedSignal(enabled=False)
    assert fg.get_signal() is None


def test_extreme_fear_returns_buy():
    fg = FearGreedSignal(enabled=True)
    with patch("user_data.strategies.signals.fear_greed.requests.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"data": [{"value": "15"}]},
        )
        mock_get.return_value.raise_for_status = MagicMock()
        signal = fg.get_signal()
    assert signal is not None
    assert signal.direction == "BUY"
    assert signal.confidence == 0.7
    assert signal.strategy == "fear_greed"


def test_fear_returns_weak_buy():
    fg = FearGreedSignal(enabled=True)
    with patch("user_data.strategies.signals.fear_greed.requests.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"data": [{"value": "35"}]},
        )
        mock_get.return_value.raise_for_status = MagicMock()
        signal = fg.get_signal()
    assert signal.direction == "BUY"
    assert signal.confidence == 0.55


def test_neutral_returns_hold():
    fg = FearGreedSignal(enabled=True)
    with patch("user_data.strategies.signals.fear_greed.requests.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"data": [{"value": "50"}]},
        )
        mock_get.return_value.raise_for_status = MagicMock()
        signal = fg.get_signal()
    assert signal.direction == "HOLD"


def test_extreme_greed_returns_sell():
    fg = FearGreedSignal(enabled=True)
    with patch("user_data.strategies.signals.fear_greed.requests.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"data": [{"value": "85"}]},
        )
        mock_get.return_value.raise_for_status = MagicMock()
        signal = fg.get_signal()
    assert signal.direction == "SELL"
    assert signal.confidence == 0.7


def test_api_failure_returns_none():
    fg = FearGreedSignal(enabled=True)
    with patch("user_data.strategies.signals.fear_greed.requests.get") as mock_get:
        mock_get.side_effect = Exception("Network error")
        signal = fg.get_signal()
    assert signal is None


def test_caching_avoids_repeated_calls():
    fg = FearGreedSignal(enabled=True)
    with patch("user_data.strategies.signals.fear_greed.requests.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"data": [{"value": "20"}]},
        )
        mock_get.return_value.raise_for_status = MagicMock()
        fg.get_signal()
        fg.get_signal()
    # Should only call API once due to caching
    assert mock_get.call_count == 1
