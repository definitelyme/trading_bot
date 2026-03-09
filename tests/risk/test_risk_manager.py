import pytest
from user_data.strategies.risk.risk_manager import RiskManager

@pytest.fixture
def risk_manager():
    return RiskManager(
        max_portfolio_pct=0.05,
        drawdown_24h_limit=0.10,
        drawdown_7d_limit=0.20,
        min_confidence=0.55,
        kelly_fraction=0.25,
    )

def test_position_size_scales_with_confidence(risk_manager):
    # Use high ATR so raw sizes stay below the 5% cap
    size_low = risk_manager.calculate_position_size(
        portfolio_value=1000.0, confidence=0.55, atr_pct=0.20
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
        portfolio_value=1000.0, confidence=0.40, atr_pct=0.02
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

def test_circuit_breaker_fires_on_7d_drawdown(risk_manager):
    risk_manager.record_drawdown(amount=210.0, portfolio_value=1000.0, window="7d")
    assert risk_manager.is_circuit_breaker_active() is True

def test_circuit_breaker_inactive_below_7d_threshold(risk_manager):
    risk_manager.record_drawdown(amount=100.0, portfolio_value=1000.0, window="7d")
    assert risk_manager.is_circuit_breaker_active() is False

def test_circuit_breaker_blocks_position_sizing(risk_manager):
    risk_manager.record_drawdown(amount=110.0, portfolio_value=1000.0, window="24h")
    assert risk_manager.is_circuit_breaker_active() is True
    size = risk_manager.calculate_position_size(
        portfolio_value=1000.0, confidence=0.90, atr_pct=0.20
    )
    assert size == 0.0

def test_circuit_breaker_reset(risk_manager):
    risk_manager.record_drawdown(amount=110.0, portfolio_value=1000.0, window="24h")
    assert risk_manager.is_circuit_breaker_active() is True
    risk_manager.reset_circuit_breaker()
    assert risk_manager.is_circuit_breaker_active() is False

def test_cumulative_drawdown_triggers_breaker(risk_manager):
    # Multiple small losses that cumulatively exceed 10%
    risk_manager.record_drawdown(amount=40.0, portfolio_value=1000.0, window="24h")
    assert risk_manager.is_circuit_breaker_active() is False
    risk_manager.record_drawdown(amount=40.0, portfolio_value=1000.0, window="24h")
    assert risk_manager.is_circuit_breaker_active() is False
    risk_manager.record_drawdown(amount=30.0, portfolio_value=1000.0, window="24h")
    assert risk_manager.is_circuit_breaker_active() is True

def test_position_size_exactly_at_min_confidence(risk_manager):
    size = risk_manager.calculate_position_size(
        portfolio_value=1000.0, confidence=0.55, atr_pct=0.20
    )
    assert size > 0.0  # Exactly at threshold should produce a position

def test_position_size_just_below_min_confidence(risk_manager):
    size = risk_manager.calculate_position_size(
        portfolio_value=1000.0, confidence=0.5499, atr_pct=0.20
    )
    assert size == 0.0

def test_position_size_with_zero_portfolio(risk_manager):
    size = risk_manager.calculate_position_size(
        portfolio_value=0.0, confidence=0.90, atr_pct=0.02
    )
    assert size == 0.0


def test_quarter_kelly_smaller_than_half_kelly():
    """Quarter-Kelly should produce smaller positions than half-Kelly."""
    quarter = RiskManager(kelly_fraction=0.25, min_confidence=0.55)
    half = RiskManager(kelly_fraction=0.50, min_confidence=0.55)
    size_q = quarter.calculate_position_size(
        portfolio_value=1000.0, confidence=0.80, atr_pct=0.15
    )
    size_h = half.calculate_position_size(
        portfolio_value=1000.0, confidence=0.80, atr_pct=0.15
    )
    assert size_q < size_h
    assert size_q > 0


def test_quarter_kelly_exact_calculation():
    """Verify quarter-Kelly formula: edge * 0.25 * volatility_scalar."""
    rm = RiskManager(kelly_fraction=0.25, min_confidence=0.55, max_portfolio_pct=1.0)
    # confidence=0.80 → edge = 0.80 - 0.20 = 0.60
    # kelly_bet = 0.60 * 0.25 = 0.15
    # atr_pct=0.02 → volatility_scalar = min(1.0, 0.02/0.02) = 1.0
    # raw_size = 1000 * 0.15 * 1.0 = 150
    size = rm.calculate_position_size(
        portfolio_value=1000.0, confidence=0.80, atr_pct=0.02
    )
    assert size == 150.0


def test_default_min_confidence_is_055():
    """Default min_confidence should be 0.55 (percentile-rank scale)."""
    rm = RiskManager()
    assert rm.min_confidence == 0.55
    assert rm.kelly_fraction == 0.25
