import pytest
from user_data.strategies.signals.signal_aggregator import SignalAggregator, Signal

@pytest.fixture
def aggregator():
    return SignalAggregator(min_confidence=0.65)

def test_buy_signal_emitted_when_confidence_above_threshold(aggregator):
    signals = [
        Signal(direction="BUY", confidence=0.80, strategy="trend"),
        Signal(direction="BUY", confidence=0.75, strategy="sentiment"),
    ]
    result = aggregator.aggregate(signals)
    assert result.direction == "BUY"
    assert result.confidence >= 0.65

def test_hold_emitted_when_confidence_below_threshold(aggregator):
    signals = [
        Signal(direction="BUY", confidence=0.50, strategy="trend"),
        Signal(direction="SELL", confidence=0.55, strategy="sentiment"),
    ]
    result = aggregator.aggregate(signals)
    assert result.direction == "HOLD"

def test_hold_emitted_on_conflicting_signals(aggregator):
    signals = [
        Signal(direction="BUY", confidence=0.85, strategy="trend"),
        Signal(direction="SELL", confidence=0.85, strategy="mean_reversion"),
    ]
    result = aggregator.aggregate(signals)
    assert result.direction == "HOLD"

def test_empty_signals_returns_hold(aggregator):
    result = aggregator.aggregate([])
    assert result.direction == "HOLD"

def test_confidence_is_weighted_average(aggregator):
    signals = [
        Signal(direction="BUY", confidence=0.80, strategy="trend"),
        Signal(direction="BUY", confidence=0.70, strategy="sentiment"),
    ]
    result = aggregator.aggregate(signals)
    assert abs(result.confidence - 0.75) < 0.01

def test_sell_signal_emitted_when_all_sell_above_threshold(aggregator):
    signals = [
        Signal(direction="SELL", confidence=0.80, strategy="trend"),
        Signal(direction="SELL", confidence=0.70, strategy="mean_reversion"),
    ]
    result = aggregator.aggregate(signals)
    assert result.direction == "SELL"
    assert result.confidence >= 0.65

def test_single_buy_above_threshold(aggregator):
    signals = [Signal(direction="BUY", confidence=0.90, strategy="trend")]
    result = aggregator.aggregate(signals)
    assert result.direction == "BUY"
    assert result.confidence == 0.90

def test_single_sell_below_threshold_returns_hold(aggregator):
    signals = [Signal(direction="SELL", confidence=0.50, strategy="trend")]
    result = aggregator.aggregate(signals)
    assert result.direction == "HOLD"

def test_contributing_strategies_tracked(aggregator):
    signals = [
        Signal(direction="BUY", confidence=0.80, strategy="trend"),
        Signal(direction="BUY", confidence=0.75, strategy="sentiment"),
    ]
    result = aggregator.aggregate(signals)
    assert "trend" in result.contributing_strategies
    assert "sentiment" in result.contributing_strategies

def test_hold_signals_return_hold(aggregator):
    signals = [
        Signal(direction="HOLD", confidence=0.90, strategy="trend"),
    ]
    result = aggregator.aggregate(signals)
    assert result.direction == "HOLD"
    assert result.confidence == 0.0
