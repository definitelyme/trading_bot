import pytest
from unittest.mock import patch, AsyncMock
from user_data.strategies.data_clients.lunarcrush_client import LunarCrushClient

@pytest.fixture
def client():
    return LunarCrushClient(api_key="test_key")

@pytest.mark.asyncio
async def test_get_sentiment_returns_score_between_0_and_1(client):
    mock_response = {
        "data": [{"symbol": "BTC", "galaxy_score": 75, "sentiment": 3.8}]
    }
    with patch.object(client, "_fetch", return_value=mock_response):
        score = await client.get_sentiment("BTC")
    assert 0.0 <= score <= 1.0

@pytest.mark.asyncio
async def test_get_sentiment_returns_none_on_api_error(client):
    with patch.object(client, "_fetch", side_effect=Exception("API error")):
        score = await client.get_sentiment("BTC")
    assert score is None

@pytest.mark.asyncio
async def test_get_sentiment_normalises_galaxy_score(client):
    mock_response = {
        "data": [{"symbol": "BTC", "galaxy_score": 100, "sentiment": 5.0}]
    }
    with patch.object(client, "_fetch", return_value=mock_response):
        score = await client.get_sentiment("BTC")
    assert score == 1.0
