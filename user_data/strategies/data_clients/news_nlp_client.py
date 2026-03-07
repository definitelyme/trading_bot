import logging
from typing import Optional

logger = logging.getLogger(__name__)

class NewsNLPClient:
    """
    FinBERT-based sentiment analyser for crypto news headlines.
    Lazy-loads model on first use to avoid startup delay.
    """

    def __init__(self):
        self._pipeline = None

    def _load_model(self):
        if self._pipeline is None:
            try:
                from transformers import pipeline
                self._pipeline = pipeline(
                    "text-classification",
                    model="ProsusAI/finbert",
                    top_k=None
                )
                logger.info("FinBERT model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load FinBERT: {e}")
                self._pipeline = None

    def analyse(self, headline: str) -> float:
        """
        Returns sentiment score 0.0 (very negative) to 1.0 (very positive).
        Returns 0.5 (neutral) on empty input or model failure.
        """
        if not headline.strip():
            return 0.5

        self._load_model()

        if self._pipeline is None:
            return 0.5

        try:
            results = self._pipeline(headline[:512])
            # top_k=None returns [[{label, score}, ...]] for single input
            label_scores = results[0] if results else []
            if label_scores and isinstance(label_scores[0], list):
                label_scores = label_scores[0]
            scores = {r["label"].lower(): r["score"] for r in label_scores}
            positive = scores.get("positive", 0.0)
            negative = scores.get("negative", 0.0)
            # Map to 0.0-1.0: pure negative = 0.0, pure positive = 1.0
            total = positive + negative
            if total == 0:
                return 0.5
            return round(positive / total, 4)
        except Exception as e:
            logger.warning(f"FinBERT inference error: {e}")
            return 0.5
