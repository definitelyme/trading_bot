import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

LUNARCRUSH_BASE_URL = "https://lunarcrush.com/api4/public"

class LunarCrushClient:
    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = httpx.AsyncClient(timeout=10.0)

    async def _fetch(self, endpoint: str, params: dict) -> dict:
        params["key"] = self._api_key
        response = await self._client.get(f"{LUNARCRUSH_BASE_URL}/{endpoint}", params=params)
        response.raise_for_status()
        return response.json()

    async def get_sentiment(self, symbol: str) -> Optional[float]:
        """Returns normalised sentiment score 0.0–1.0. None on error."""
        try:
            data = await self._fetch("coins/list/v2", {"sort": "galaxy_score", "limit": 50})
            coins = data.get("data", [])
            for coin in coins:
                if coin.get("symbol", "").upper() == symbol.upper():
                    galaxy_score = coin.get("galaxy_score", 50)
                    # Galaxy score is 0-100, normalise to 0.0-1.0
                    return round(galaxy_score / 100.0, 4)
            return 0.5  # neutral default if symbol not found
        except Exception as e:
            logger.warning(f"LunarCrush API error for {symbol}: {e}")
            return None

    async def close(self):
        await self._client.aclose()
