import sys
from pathlib import Path

# Mirror the sys.path hack in AICryptoStrategy.py so that bare `signals.xxx`
# imports in fear_greed.py and news_sentiment.py resolve correctly during tests.
# At runtime, AICryptoStrategy adds user_data/strategies/ to sys.path before
# importing those modules. In tests, that file is never loaded, so we do it here.
_strategies_dir = str(Path(__file__).parent.parent / "user_data" / "strategies")
if _strategies_dir not in sys.path:
    sys.path.insert(0, _strategies_dir)
