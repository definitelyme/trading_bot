import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

GLASSNODE_BASE_URL = "https://api.glassnode.com/v1/metrics"

class GlassnodeClient:
    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = httpx.AsyncClient(timeout=15.0)
        # Rolling 30-day baseline values for normalisation (updated periodically)
        self._baselines = {
            "BTC": {"inflow_low": 1000.0, "inflow_high": 20000.0},
            "ETH": {"inflow_low": 5000.0, "inflow_high": 100000.0},
        }

    async def _fetch(self, endpoint: str, params: dict) -> list:
        params["api_key"] = self._api_key
        response = await self._client.get(f"{GLASSNODE_BASE_URL}/{endpoint}", params=params)
        response.raise_for_status()
        return response.json()

    async def get_exchange_inflow_signal(self, symbol: str) -> float:
        """
        High inflow to exchanges = bearish (selling pressure).
        Returns 0.0 (high inflow = bearish) to 1.0 (low inflow = bullish).
        Returns 0.5 (neutral) on error.
        """
        try:
            data = await self._fetch(
                "transactions/transfers_volume_to_exchanges_sum",
                {"a": symbol, "i": "24h", "limit": 1}
            )
            if not data:
                return 0.5
            inflow = data[-1].get("v", 0.0)
            baseline = self._baselines.get(symbol, {"inflow_low": 1000.0, "inflow_high": 20000.0})
            # Clamp and invert: high inflow is bearish (low score)
            clamped = max(baseline["inflow_low"], min(inflow, baseline["inflow_high"]))
            normalised = (clamped - baseline["inflow_low"]) / (baseline["inflow_high"] - baseline["inflow_low"])
            return round(1.0 - normalised, 4)  # invert: high inflow = low score
        except Exception as e:
            logger.warning(f"Glassnode API error for {symbol}: {e}")
            return 0.5

    async def close(self):
        await self._client.aclose()
