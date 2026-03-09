import logging
import time
from typing import Optional

import requests

from user_data.strategies.signals.signal_aggregator import Signal

logger = logging.getLogger(__name__)


class FearGreedSignal:
    """Fetches Fear & Greed Index from Alternative.me (free, no key needed).

    Enabled via FEAR_GREED_ENABLED=true env var. When disabled, get_signal()
    returns None and the aggregator skips it.

    Interpretation:
    - 0-25 (Extreme Fear) → contrarian BUY signal (market oversold)
    - 25-45 (Fear) → weak BUY signal
    - 45-55 (Neutral) → HOLD
    - 55-75 (Greed) → weak SELL signal
    - 75-100 (Extreme Greed) → contrarian SELL signal (market overheated)
    """

    API_URL = "https://api.alternative.me/fng/"
    CACHE_SECONDS = 3600  # cache for 1 hour (index updates daily)

    def __init__(self, enabled: bool = False):
        self._enabled = enabled
        self._cached_value: Optional[int] = None
        self._last_fetch: float = 0.0

    def _fetch(self) -> Optional[int]:
        """Fetch current Fear & Greed value (0-100)."""
        now = time.time()
        if self._cached_value is not None and (now - self._last_fetch) < self.CACHE_SECONDS:
            return self._cached_value
        try:
            resp = requests.get(self.API_URL, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            value = int(data["data"][0]["value"])
            self._cached_value = value
            self._last_fetch = now
            logger.info("Fear & Greed Index: %d", value)
            return value
        except Exception:
            logger.warning("Failed to fetch Fear & Greed Index", exc_info=True)
            return self._cached_value  # return stale cache if available

    def get_signal(self) -> Optional[Signal]:
        """Return a Signal based on Fear & Greed Index, or None if disabled."""
        if not self._enabled:
            return None

        value = self._fetch()
        if value is None:
            return None

        if value <= 25:
            return Signal(direction="BUY", confidence=0.7, strategy="fear_greed")
        elif value <= 45:
            return Signal(direction="BUY", confidence=0.55, strategy="fear_greed")
        elif value <= 55:
            return Signal(direction="HOLD", confidence=0.5, strategy="fear_greed")
        elif value <= 75:
            return Signal(direction="SELL", confidence=0.55, strategy="fear_greed")
        else:
            return Signal(direction="SELL", confidence=0.7, strategy="fear_greed")
