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
