import pytest
from unittest.mock import patch
from user_data.strategies.data_clients.glassnode_client import GlassnodeClient

@pytest.fixture
def client():
    return GlassnodeClient(api_key="test_key")

@pytest.mark.asyncio
async def test_get_exchange_inflow_returns_normalised_score(client):
    mock_data = [{"t": 1700000000, "v": 5000.0}]
    with patch.object(client, "_fetch", return_value=mock_data):
        score = await client.get_exchange_inflow_signal("BTC")
    assert 0.0 <= score <= 1.0

@pytest.mark.asyncio
async def test_get_exchange_inflow_returns_neutral_on_error(client):
    with patch.object(client, "_fetch", side_effect=Exception("API error")):
        score = await client.get_exchange_inflow_signal("BTC")
    assert score == 0.5

@pytest.mark.asyncio
async def test_get_exchange_inflow_returns_neutral_on_empty_data(client):
    with patch.object(client, "_fetch", return_value=[]):
        score = await client.get_exchange_inflow_signal("BTC")
    assert score == 0.5

@pytest.mark.asyncio
async def test_high_inflow_returns_bearish_score(client):
    """High inflow to exchanges = selling pressure = low score (bearish)."""
    mock_data = [{"t": 1700000000, "v": 20000.0}]  # at inflow_high baseline
    with patch.object(client, "_fetch", return_value=mock_data):
        score = await client.get_exchange_inflow_signal("BTC")
    assert score == 0.0  # max bearish

@pytest.mark.asyncio
async def test_low_inflow_returns_bullish_score(client):
    """Low inflow to exchanges = no selling pressure = high score (bullish)."""
    mock_data = [{"t": 1700000000, "v": 1000.0}]  # at inflow_low baseline
    with patch.object(client, "_fetch", return_value=mock_data):
        score = await client.get_exchange_inflow_signal("BTC")
    assert score == 1.0  # max bullish

@pytest.mark.asyncio
async def test_mid_inflow_returns_mid_score(client):
    """Mid-range inflow gives roughly 0.5."""
    mid_value = (1000.0 + 20000.0) / 2  # 10500
    mock_data = [{"t": 1700000000, "v": mid_value}]
    with patch.object(client, "_fetch", return_value=mock_data):
        score = await client.get_exchange_inflow_signal("BTC")
    assert 0.4 <= score <= 0.6

@pytest.mark.asyncio
async def test_unknown_symbol_uses_default_baseline(client):
    """Symbols without specific baselines use defaults."""
    mock_data = [{"t": 1700000000, "v": 5000.0}]
    with patch.object(client, "_fetch", return_value=mock_data):
        score = await client.get_exchange_inflow_signal("DOGE")
    assert 0.0 <= score <= 1.0

@pytest.mark.asyncio
async def test_inflow_beyond_high_baseline_clamps(client):
    """Values above inflow_high should clamp to 0.0 (most bearish)."""
    mock_data = [{"t": 1700000000, "v": 50000.0}]  # way above 20000 high
    with patch.object(client, "_fetch", return_value=mock_data):
        score = await client.get_exchange_inflow_signal("BTC")
    assert score == 0.0
