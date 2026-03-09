import pytest
from unittest.mock import patch, MagicMock
from user_data.strategies.signals.news_sentiment import NewsSentimentSignal


def test_disabled_returns_none():
    ns = NewsSentimentSignal(enabled=False)
    assert ns.get_signal("BTC/USDT") is None


def test_no_api_key_returns_none():
    ns = NewsSentimentSignal(enabled=True, api_key="")
    assert ns.get_signal("BTC/USDT") is None


def test_unknown_pair_returns_none():
    ns = NewsSentimentSignal(enabled=True, api_key="test-key")
    assert ns.get_signal("UNKNOWN/USDT") is None


def test_positive_sentiment_returns_buy():
    ns = NewsSentimentSignal(enabled=True, api_key="test-key")
    with patch.object(ns, "_fetch_headlines", return_value=["Bitcoin surges to new high"]):
        with patch.object(ns, "_load_pipeline"):
            ns._pipeline = MagicMock()
            ns._pipeline.return_value = [
                {"label": "positive", "score": 0.9},
            ]
            signal = ns.get_signal("BTC/USDT")
    assert signal is not None
    assert signal.direction == "BUY"
    assert signal.strategy == "news_sentiment"


def test_negative_sentiment_returns_sell():
    ns = NewsSentimentSignal(enabled=True, api_key="test-key")
    with patch.object(ns, "_fetch_headlines", return_value=["Bitcoin crashes 20%"]):
        with patch.object(ns, "_load_pipeline"):
            ns._pipeline = MagicMock()
            ns._pipeline.return_value = [
                {"label": "negative", "score": 0.9},
            ]
            signal = ns.get_signal("BTC/USDT")
    assert signal is not None
    assert signal.direction == "SELL"


def test_neutral_sentiment_returns_hold():
    ns = NewsSentimentSignal(enabled=True, api_key="test-key")
    with patch.object(ns, "_fetch_headlines", return_value=["Bitcoin trades sideways"]):
        with patch.object(ns, "_load_pipeline"):
            ns._pipeline = MagicMock()
            ns._pipeline.return_value = [
                {"label": "neutral", "score": 0.8},
            ]
            signal = ns.get_signal("BTC/USDT")
    assert signal.direction == "HOLD"


def test_score_to_signal_boundaries():
    """Test the score-to-signal conversion at boundaries."""
    assert NewsSentimentSignal._score_to_signal(0.65).direction == "BUY"
    assert NewsSentimentSignal._score_to_signal(0.35).direction == "SELL"
    assert NewsSentimentSignal._score_to_signal(0.50).direction == "HOLD"
    assert NewsSentimentSignal._score_to_signal(0.36).direction == "HOLD"
    assert NewsSentimentSignal._score_to_signal(0.64).direction == "HOLD"


def test_empty_headlines_returns_none():
    ns = NewsSentimentSignal(enabled=True, api_key="test-key")
    with patch.object(ns, "_fetch_headlines", return_value=[]):
        with patch.object(ns, "_load_pipeline"):
            ns._pipeline = MagicMock()
            signal = ns.get_signal("BTC/USDT")
    assert signal is None


def test_pipeline_load_failure_returns_none():
    ns = NewsSentimentSignal(enabled=True, api_key="test-key")
    # Force pipeline to stay None by making import fail
    with patch("user_data.strategies.signals.news_sentiment.requests.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"results": [{"title": "test"}]},
        )
        mock_get.return_value.raise_for_status = MagicMock()
        with patch.object(ns, "_load_pipeline", side_effect=lambda: None):
            # _pipeline stays None since _load_pipeline does nothing
            ns._pipeline = None
            signal = ns.get_signal("BTC/USDT")
    assert signal is None


def test_pair_currency_mapping():
    """All configured pairs should have a currency mapping."""
    ns = NewsSentimentSignal()
    expected_pairs = [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "AVAX/USDT", "XRP/USDT",
        "DOGE/USDT", "PEPE/USDT", "SUI/USDT", "WIF/USDT", "NEAR/USDT", "FET/USDT",
    ]
    for pair in expected_pairs:
        assert pair in ns.PAIR_TO_CURRENCY, f"Missing mapping for {pair}"
