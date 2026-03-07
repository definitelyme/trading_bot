import pytest
from user_data.strategies.risk.risk_manager import RiskManager

@pytest.fixture
def risk_manager():
    return RiskManager(
        max_portfolio_pct=0.05,
        drawdown_24h_limit=0.10,
        drawdown_7d_limit=0.20,
        min_confidence=0.65,
    )

def test_position_size_scales_with_confidence(risk_manager):
    # Use high ATR so raw sizes stay below the 5% cap
    size_low = risk_manager.calculate_position_size(
        portfolio_value=1000.0, confidence=0.65, atr_pct=0.20
    )
    size_high = risk_manager.calculate_position_size(
        portfolio_value=1000.0, confidence=0.90, atr_pct=0.20
    )
    assert size_high > size_low

def test_position_size_never_exceeds_max_pct(risk_manager):
    size = risk_manager.calculate_position_size(
        portfolio_value=1000.0, confidence=1.0, atr_pct=0.001
    )
    assert size <= 1000.0 * 0.05

def test_position_size_zero_below_min_confidence(risk_manager):
    size = risk_manager.calculate_position_size(
        portfolio_value=1000.0, confidence=0.50, atr_pct=0.02
    )
    assert size == 0.0

def test_circuit_breaker_fires_on_24h_drawdown(risk_manager):
    risk_manager.record_drawdown(amount=110.0, portfolio_value=1000.0, window="24h")
    assert risk_manager.is_circuit_breaker_active() is True

def test_circuit_breaker_inactive_below_threshold(risk_manager):
    risk_manager.record_drawdown(amount=50.0, portfolio_value=1000.0, window="24h")
    assert risk_manager.is_circuit_breaker_active() is False

def test_atr_reduces_position_size(risk_manager):
    # Use high ATR values so raw sizes stay below the 5% cap
    size_low_vol = risk_manager.calculate_position_size(
        portfolio_value=1000.0, confidence=0.80, atr_pct=0.15
    )
    size_high_vol = risk_manager.calculate_position_size(
        portfolio_value=1000.0, confidence=0.80, atr_pct=0.30
    )
    assert size_low_vol > size_high_vol
