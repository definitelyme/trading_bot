import logging
import time
from typing import Optional

import requests

from signals.signal_aggregator import Signal

logger = logging.getLogger(__name__)


class NewsSentimentSignal:
    """Runs FinBERT on crypto news headlines from CryptoPanic.

    Enabled via NEWS_SENTIMENT_ENABLED=true env var.
    Requires CRYPTOPANIC_API_KEY env var.

    When disabled or missing API key, get_signal() returns None.
    """

    CRYPTOPANIC_URL = "https://cryptopanic.com/api/free/v1/posts/"
    CACHE_SECONDS = 1800  # cache per pair for 30 minutes

    # Map trading pair base currency to CryptoPanic filter
    PAIR_TO_CURRENCY = {
        "BTC/USDT": "BTC",
        "ETH/USDT": "ETH",
        "SOL/USDT": "SOL",
        "AVAX/USDT": "AVAX",
        "XRP/USDT": "XRP",
        "DOGE/USDT": "DOGE",
        "PEPE/USDT": "PEPE",
        "SUI/USDT": "SUI",
        "WIF/USDT": "WIF",
        "NEAR/USDT": "NEAR",
        "FET/USDT": "FET",
    }

    def __init__(self, enabled: bool = False, api_key: str = ""):
        self._enabled = enabled
        self._api_key = api_key
        self._pipeline = None  # lazy-loaded FinBERT pipeline
        self._cache: dict[str, tuple[float, float]] = {}  # pair → (timestamp, score)

    def _load_pipeline(self):
        """Lazy-load FinBERT pipeline on first use."""
        if self._pipeline is not None:
            return
        try:
            from transformers import pipeline
            self._pipeline = pipeline(
                "sentiment-analysis",
                model="ProsusAI/finbert",
                tokenizer="ProsusAI/finbert",
            )
            logger.info("FinBERT pipeline loaded successfully")
        except Exception:
            logger.warning("Failed to load FinBERT pipeline", exc_info=True)
            self._pipeline = None

    def _fetch_headlines(self, currency: str, limit: int = 10) -> list[str]:
        """Fetch recent headlines from CryptoPanic for a currency."""
        try:
            resp = requests.get(
                self.CRYPTOPANIC_URL,
                params={
                    "auth_token": self._api_key,
                    "currencies": currency,
                    "kind": "news",
                    "filter": "important",
                },
                timeout=10,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            return [r["title"] for r in results[:limit]]
        except Exception:
            logger.warning("Failed to fetch CryptoPanic headlines for %s", currency, exc_info=True)
            return []

    def _score_headlines(self, headlines: list[str]) -> float:
        """Run FinBERT on headlines, return 0-1 score (0=bearish, 0.5=neutral, 1=bullish)."""
        if not headlines or self._pipeline is None:
            return 0.5

        results = self._pipeline(headlines, truncation=True)
        total_score = 0.0
        for r in results:
            label = r["label"].lower()
            score = r["score"]
            if label == "positive":
                total_score += score
            elif label == "negative":
                total_score -= score
            # neutral contributes 0

        # Normalize from [-1, 1] to [0, 1]
        avg = total_score / len(results)
        return (avg + 1.0) / 2.0

    def get_signal(self, pair: str) -> Optional[Signal]:
        """Return a Signal based on news sentiment, or None if disabled."""
        if not self._enabled or not self._api_key:
            return None

        currency = self.PAIR_TO_CURRENCY.get(pair)
        if not currency:
            return None

        # Check cache
        now = time.time()
        if pair in self._cache:
            cached_time, cached_score = self._cache[pair]
            if (now - cached_time) < self.CACHE_SECONDS:
                return self._score_to_signal(cached_score)

        self._load_pipeline()
        if self._pipeline is None:
            return None

        headlines = self._fetch_headlines(currency)
        if not headlines:
            return None

        score = self._score_headlines(headlines)
        self._cache[pair] = (now, score)

        return self._score_to_signal(score)

    @staticmethod
    def _score_to_signal(score: float) -> Signal:
        """Convert 0-1 sentiment score to a Signal."""
        if score >= 0.65:
            return Signal(direction="BUY", confidence=score, strategy="news_sentiment")
        elif score <= 0.35:
            return Signal(direction="SELL", confidence=1.0 - score, strategy="news_sentiment")
        else:
            return Signal(direction="HOLD", confidence=0.5, strategy="news_sentiment")
