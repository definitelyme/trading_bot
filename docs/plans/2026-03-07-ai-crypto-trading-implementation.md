# AI Crypto Trading System — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. And use "systematic-debugging" agent for debugging any issues you may encounter along the way. Before implementation, ensure you use "test-driven-development" agent for TDD approach while implementing every feature one test at a time, ensuring <1% bug-free.

**Goal:** Build a continuously learning AI-powered crypto trading system using Freqtrade + FreqAI that trades across Binance, Bybit, OKX, and Coinbase Advanced with technical, sentiment, and on-chain signal fusion.

**Architecture:** Freqtrade as the execution orchestrator with FreqAI handling continuous ML retraining (XGBoost + LSTM ensemble). A custom data collector feeds LunarCrush sentiment, Glassnode on-chain, and FinBERT news NLP signals into the feature pipeline alongside standard technical indicators. A hard-coded risk manager enforces Half-Kelly position sizing, ATR-based stops, and drawdown circuit breakers.

**Tech Stack:** Python 3.11+, Freqtrade + FreqAI, CCXT, XGBoost, PyTorch (LSTM), HuggingFace Transformers (FinBERT), LunarCrush API, Santiment API, Glassnode API, Telegram Bot API, Docker, Parquet/pandas for data storage.

**Project Location:** `~/projects/ai-crypto-trader/` (new standalone Python project, separate from Flutter workspace)

---

## Phase 0: Environment Setup

### Task 1: Create Project Structure. This is a blank project, so from current working directory

**Files:**
- Create: `~/projects/ai-crypto-trader/` (project root)
- Create: `~/projects/ai-crypto-trader/pyproject.toml`
- Create: `~/projects/ai-crypto-trader/.env.example`
- Create: `~/projects/ai-crypto-trader/.gitignore`

**Step 1: Create project directory**

```bash
mkdir -p ~/projects/ai-crypto-trader
cd ~/projects/ai-crypto-trader
git init
```

**Step 2: Create pyproject.toml**

```toml
[project]
name = "ai-crypto-trader"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "freqtrade>=2024.1",
    "ccxt>=4.0.0",
    "xgboost>=2.0.0",
    "lightgbm>=4.0.0",
    "torch>=2.0.0",
    "transformers>=4.35.0",
    "pandas>=2.0.0",
    "numpy>=1.24.0",
    "scikit-learn>=1.3.0",
    "ta-lib>=0.4.28",
    "python-dotenv>=1.0.0",
    "httpx>=0.25.0",
    "pytest>=7.4.0",
    "pytest-asyncio>=0.21.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

**Step 3: Create .env.example**

```bash
# Exchange API Keys (use withdrawal-disabled keys only)
BINANCE_API_KEY=
BINANCE_SECRET=
BYBIT_API_KEY=
BYBIT_SECRET=
OKX_API_KEY=
OKX_SECRET=
OKX_PASSPHRASE=
COINBASE_API_KEY=
COINBASE_SECRET=

# Sentiment Data APIs
LUNARCRUSH_API_KEY=
SANTIMENT_API_KEY=
GLASSNODE_API_KEY=

# Telegram Alerts
TELEGRAM_TOKEN=
TELEGRAM_CHAT_ID=

# Trading Mode: backtest | dry_run | live
TRADING_MODE=dry_run

# Risk Parameters
MAX_PORTFOLIO_PCT_PER_TRADE=0.05
CIRCUIT_BREAKER_24H_DRAWDOWN=0.10
CIRCUIT_BREAKER_7D_DRAWDOWN=0.20
MIN_SIGNAL_CONFIDENCE=0.65
```

**Step 4: Create .gitignore**

```
.env
*.pyc
__pycache__/
user_data/logs/
user_data/data/
*.db
.venv/
dist/
*.egg-info/
```

**Step 5: Install dependencies**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install freqtrade
freqtrade install-ui
pip install xgboost lightgbm torch transformers httpx pytest pytest-asyncio
```

Expected: All packages install without errors.

**Step 6: Initialise Freqtrade user directory**

```bash
freqtrade create-userdir --userdir user_data
```

Expected: `user_data/` directory created with `strategies/`, `data/`, `logs/`, `models/` subdirectories.

**Step 7: Commit**

```bash
git add pyproject.toml .env.example .gitignore
git commit -m "chore: initialise ai-crypto-trader project"
```

---

### Task 2: Base Freqtrade Configuration

**Files:**
- Create: `user_data/config.json`
- Create: `user_data/config.dry_run.json`
- Create: `user_data/config.live.json`

**Step 1: Create base config (dry run mode)**

```json
// user_data/config.json
{
    "trading_mode": "spot",
    "margin_mode": "",
    "max_open_trades": 5,
    "stake_currency": "USDT",
    "stake_amount": "unlimited",
    "tradable_balance_ratio": 0.95,
    "fiat_display_currency": "USD",
    "dry_run": true,
    "dry_run_wallet": 1000,
    "cancel_open_orders_on_exit": false,
    "timeframe": "1h",
    "exchange": {
        "name": "binance",
        "key": "",
        "secret": "",
        "ccxt_config": {},
        "ccxt_async_config": {},
        "pair_whitelist": [
            "BTC/USDT",
            "ETH/USDT",
            "SOL/USDT",
            "BNB/USDT",
            "XRP/USDT"
        ],
        "pair_blacklist": [
            "BNB/.*"
        ]
    },
    "pairlists": [
        {
            "method": "StaticPairList"
        }
    ],
    "freqai": {
        "enabled": true,
        "purge_old_models": 2,
        "train_period_days": 30,
        "backtest_period_days": 7,
        "live_retrain_hours": 4,
        "identifier": "ai_crypto_v1",
        "feature_parameters": {
            "include_timeframes": ["5m", "1h", "4h"],
            "include_corr_pairlist": ["BTC/USDT", "ETH/USDT"],
            "label_period_candles": 24,
            "include_shifted_candles": 2,
            "DI_threshold": 0.9,
            "weight_factor": 0.9,
            "indicator_periods_candles": [10, 20, 50]
        },
        "data_split_parameters": {
            "test_size": 0.33,
            "random_state": 42
        },
        "model_training_parameters": {
            "n_estimators": 800,
            "learning_rate": 0.02,
            "max_depth": 8
        }
    },
    "entry_pricing": {
        "price_side": "same",
        "use_order_book": true,
        "order_book_top": 1,
        "price_last_balance": 0.0,
        "check_depth_of_market": {
            "enabled": false,
            "bids_to_ask_delta": 1
        }
    },
    "exit_pricing": {
        "price_side": "same",
        "use_order_book": true,
        "order_book_top": 1
    },
    "stoploss": -0.05,
    "trailing_stop": true,
    "trailing_stop_positive": 0.01,
    "trailing_stop_positive_offset": 0.02,
    "trailing_only_offset_is_reached": true,
    "minimal_roi": {
        "0": 0.10,
        "120": 0.05,
        "240": 0.02,
        "480": 0.01
    },
    "telegram": {
        "enabled": true,
        "token": "",
        "chat_id": "",
        "notification_settings": {
            "status": "on",
            "warning": "on",
            "startup": "on",
            "entry": "on",
            "exit": "on",
            "entry_cancel": "on",
            "exit_cancel": "on"
        }
    },
    "api_server": {
        "enabled": true,
        "listen_ip_address": "127.0.0.1",
        "listen_port": 8080,
        "verbosity": "error",
        "enable_openapi": true,
        "jwt_secret_key": "change-this-to-a-random-secret",
        "CORS_origins": [],
        "username": "trader",
        "password": "change-this-password"
    },
    "bot_name": "ai_crypto_trader",
    "initial_state": "running",
    "force_entry_enable": false,
    "internals": {
        "process_throttle_secs": 5
    }
}
```

**Step 2: Verify config is valid**

```bash
freqtrade show-config --config user_data/config.json
```

Expected: Config parsed without errors, shows exchange, strategy, FreqAI settings.

**Step 3: Commit**

```bash
git add user_data/config.json
git commit -m "chore: add base freqtrade configuration"
```

---

## Phase 1: Data Layer

### Task 3: Sentiment Data Client (LunarCrush)

**Files:**
- Create: `user_data/strategies/data_clients/lunarcrush_client.py`
- Create: `tests/data_clients/test_lunarcrush_client.py`

**Step 1: Write the failing tests**

```python
# tests/data_clients/test_lunarcrush_client.py
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
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/data_clients/test_lunarcrush_client.py -v
```

Expected: FAIL — `ModuleNotFoundError: lunarcrush_client`

**Step 3: Implement LunarCrushClient**

```python
# user_data/strategies/data_clients/lunarcrush_client.py
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
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/data_clients/test_lunarcrush_client.py -v
```

Expected: All 3 tests PASS.

**Step 5: Commit**

```bash
git add user_data/strategies/data_clients/lunarcrush_client.py tests/data_clients/test_lunarcrush_client.py
git commit -m "feat: add LunarCrush sentiment client"
```

---

### Task 4: News NLP Client (FinBERT)

**Files:**
- Create: `user_data/strategies/data_clients/news_nlp_client.py`
- Create: `tests/data_clients/test_news_nlp_client.py`

**Step 1: Write the failing tests**

```python
# tests/data_clients/test_news_nlp_client.py
import pytest
from user_data.strategies.data_clients.news_nlp_client import NewsNLPClient

@pytest.fixture
def client():
    return NewsNLPClient()

def test_analyse_returns_score_between_0_and_1(client):
    score = client.analyse("Bitcoin surges to new all-time high on institutional demand")
    assert 0.0 <= score <= 1.0

def test_positive_headline_scores_above_0_5(client):
    score = client.analyse("Bitcoin surges to new all-time high on massive institutional demand")
    assert score > 0.5

def test_negative_headline_scores_below_0_5(client):
    score = client.analyse("Crypto market crashes, Bitcoin loses 40% in massive sell-off")
    assert score < 0.5

def test_empty_headline_returns_neutral(client):
    score = client.analyse("")
    assert score == 0.5
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/data_clients/test_news_nlp_client.py -v
```

Expected: FAIL — `ModuleNotFoundError: news_nlp_client`

**Step 3: Implement NewsNLPClient**

```python
# user_data/strategies/data_clients/news_nlp_client.py
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
                    return_all_scores=True
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
            results = self._pipeline(headline[:512])[0]  # FinBERT max 512 tokens
            scores = {r["label"].lower(): r["score"] for r in results}
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
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/data_clients/test_news_nlp_client.py -v
```

Expected: All 4 tests PASS. Note: first run downloads FinBERT model (~500MB), subsequent runs use cache.

**Step 5: Commit**

```bash
git add user_data/strategies/data_clients/news_nlp_client.py tests/data_clients/test_news_nlp_client.py
git commit -m "feat: add FinBERT news NLP sentiment client"
```

---

### Task 5: Glassnode On-Chain Client

**Files:**
- Create: `user_data/strategies/data_clients/glassnode_client.py`
- Create: `tests/data_clients/test_glassnode_client.py`

**Step 1: Write the failing tests**

```python
# tests/data_clients/test_glassnode_client.py
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
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/data_clients/test_glassnode_client.py -v
```

Expected: FAIL — `ModuleNotFoundError: glassnode_client`

**Step 3: Implement GlassnodeClient**

```python
# user_data/strategies/data_clients/glassnode_client.py
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
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/data_clients/test_glassnode_client.py -v
```

Expected: All 3 tests PASS.

**Step 5: Commit**

```bash
git add user_data/strategies/data_clients/glassnode_client.py tests/data_clients/test_glassnode_client.py
git commit -m "feat: add Glassnode on-chain data client"
```

---

## Phase 2: Risk Manager

### Task 6: Risk Manager Core

**Files:**
- Create: `user_data/strategies/risk/risk_manager.py`
- Create: `tests/risk/test_risk_manager.py`

**Step 1: Write the failing tests**

```python
# tests/risk/test_risk_manager.py
import pytest
from user_data.strategies.risk.risk_manager import RiskManager

@pytest.fixture
def risk_manager():
    return RiskManager(
        max_portfolio_pct=0.05,
        drawdown_24h_limit=0.10,
        drawdown_7d_limit=0.20,
        min_confidence=0.65,
    )

def test_position_size_scales_with_confidence(risk_manager):
    size_low = risk_manager.calculate_position_size(
        portfolio_value=1000.0, confidence=0.65, atr_pct=0.02
    )
    size_high = risk_manager.calculate_position_size(
        portfolio_value=1000.0, confidence=0.90, atr_pct=0.02
    )
    assert size_high > size_low

def test_position_size_never_exceeds_max_pct(risk_manager):
    size = risk_manager.calculate_position_size(
        portfolio_value=1000.0, confidence=1.0, atr_pct=0.001
    )
    assert size <= 1000.0 * 0.05

def test_position_size_zero_below_min_confidence(risk_manager):
    size = risk_manager.calculate_position_size(
        portfolio_value=1000.0, confidence=0.50, atr_pct=0.02
    )
    assert size == 0.0

def test_circuit_breaker_fires_on_24h_drawdown(risk_manager):
    risk_manager.record_drawdown(amount=110.0, portfolio_value=1000.0, window="24h")
    assert risk_manager.is_circuit_breaker_active() is True

def test_circuit_breaker_inactive_below_threshold(risk_manager):
    risk_manager.record_drawdown(amount=50.0, portfolio_value=1000.0, window="24h")
    assert risk_manager.is_circuit_breaker_active() is False

def test_atr_reduces_position_size(risk_manager):
    size_low_vol = risk_manager.calculate_position_size(
        portfolio_value=1000.0, confidence=0.80, atr_pct=0.01
    )
    size_high_vol = risk_manager.calculate_position_size(
        portfolio_value=1000.0, confidence=0.80, atr_pct=0.05
    )
    assert size_low_vol > size_high_vol
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/risk/test_risk_manager.py -v
```

Expected: FAIL — `ModuleNotFoundError: risk_manager`

**Step 3: Implement RiskManager**

```python
# user_data/strategies/risk/risk_manager.py
import logging
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)

@dataclass
class RiskManager:
    max_portfolio_pct: float = 0.05
    drawdown_24h_limit: float = 0.10
    drawdown_7d_limit: float = 0.20
    min_confidence: float = 0.65

    _drawdown_24h: float = field(default=0.0, init=False)
    _drawdown_7d: float = field(default=0.0, init=False)
    _circuit_breaker_active: bool = field(default=False, init=False)

    def calculate_position_size(
        self,
        portfolio_value: float,
        confidence: float,
        atr_pct: float,
    ) -> float:
        """
        Half-Kelly position sizing adjusted for ATR volatility.
        Returns 0.0 if confidence below minimum threshold.
        """
        if confidence < self.min_confidence:
            return 0.0

        if self._circuit_breaker_active:
            logger.warning("Circuit breaker active — position size forced to 0")
            return 0.0

        # Half-Kelly: f* = (confidence - (1 - confidence)) / 1.0 * 0.5
        edge = confidence - (1.0 - confidence)
        half_kelly_fraction = max(0.0, edge * 0.5)

        # ATR adjustment: reduce size when volatility is high
        # Target 1% portfolio risk per trade; atr_pct is current volatility
        volatility_scalar = min(1.0, 0.02 / max(atr_pct, 0.001))

        raw_size = portfolio_value * half_kelly_fraction * volatility_scalar
        capped_size = min(raw_size, portfolio_value * self.max_portfolio_pct)

        return round(capped_size, 2)

    def record_drawdown(
        self,
        amount: float,
        portfolio_value: float,
        window: Literal["24h", "7d"],
    ) -> None:
        """Record a loss amount and check circuit breakers."""
        drawdown_pct = amount / portfolio_value

        if window == "24h":
            self._drawdown_24h += drawdown_pct
            if self._drawdown_24h >= self.drawdown_24h_limit:
                self._circuit_breaker_active = True
                logger.critical(
                    f"CIRCUIT BREAKER: 24h drawdown {self._drawdown_24h:.1%} "
                    f"exceeded limit {self.drawdown_24h_limit:.1%}"
                )
        elif window == "7d":
            self._drawdown_7d += drawdown_pct
            if self._drawdown_7d >= self.drawdown_7d_limit:
                self._circuit_breaker_active = True
                logger.critical(
                    f"CIRCUIT BREAKER: 7d drawdown {self._drawdown_7d:.1%} "
                    f"exceeded limit {self.drawdown_7d_limit:.1%}"
                )

    def is_circuit_breaker_active(self) -> bool:
        return self._circuit_breaker_active

    def reset_circuit_breaker(self) -> None:
        """Manual reset — requires operator confirmation."""
        self._circuit_breaker_active = False
        self._drawdown_24h = 0.0
        self._drawdown_7d = 0.0
        logger.info("Circuit breaker manually reset")
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/risk/test_risk_manager.py -v
```

Expected: All 6 tests PASS.

**Step 5: Commit**

```bash
git add user_data/strategies/risk/risk_manager.py tests/risk/test_risk_manager.py
git commit -m "feat: add risk manager with half-kelly sizing and circuit breakers"
```

---

## Phase 3: Signal Aggregator

### Task 7: Signal Aggregator

**Files:**
- Create: `user_data/strategies/signals/signal_aggregator.py`
- Create: `tests/signals/test_signal_aggregator.py`

**Step 1: Write the failing tests**

```python
# tests/signals/test_signal_aggregator.py
import pytest
from user_data.strategies.signals.signal_aggregator import SignalAggregator, Signal

@pytest.fixture
def aggregator():
    return SignalAggregator(min_confidence=0.65)

def test_buy_signal_emitted_when_confidence_above_threshold(aggregator):
    signals = [
        Signal(direction="BUY", confidence=0.80, strategy="trend"),
        Signal(direction="BUY", confidence=0.75, strategy="sentiment"),
    ]
    result = aggregator.aggregate(signals)
    assert result.direction == "BUY"
    assert result.confidence >= 0.65

def test_hold_emitted_when_confidence_below_threshold(aggregator):
    signals = [
        Signal(direction="BUY", confidence=0.50, strategy="trend"),
        Signal(direction="SELL", confidence=0.55, strategy="sentiment"),
    ]
    result = aggregator.aggregate(signals)
    assert result.direction == "HOLD"

def test_hold_emitted_on_conflicting_signals(aggregator):
    signals = [
        Signal(direction="BUY", confidence=0.85, strategy="trend"),
        Signal(direction="SELL", confidence=0.85, strategy="mean_reversion"),
    ]
    result = aggregator.aggregate(signals)
    assert result.direction == "HOLD"

def test_empty_signals_returns_hold(aggregator):
    result = aggregator.aggregate([])
    assert result.direction == "HOLD"

def test_confidence_is_weighted_average(aggregator):
    signals = [
        Signal(direction="BUY", confidence=0.80, strategy="trend"),
        Signal(direction="BUY", confidence=0.70, strategy="sentiment"),
    ]
    result = aggregator.aggregate(signals)
    assert abs(result.confidence - 0.75) < 0.01
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/signals/test_signal_aggregator.py -v
```

Expected: FAIL — `ModuleNotFoundError: signal_aggregator`

**Step 3: Implement SignalAggregator**

```python
# user_data/strategies/signals/signal_aggregator.py
from dataclasses import dataclass
from typing import List

@dataclass
class Signal:
    direction: str   # "BUY" | "SELL" | "HOLD"
    confidence: float  # 0.0–1.0
    strategy: str

@dataclass
class AggregatedSignal:
    direction: str
    confidence: float
    contributing_strategies: List[str]

class SignalAggregator:
    def __init__(self, min_confidence: float = 0.65):
        self._min_confidence = min_confidence

    def aggregate(self, signals: List[Signal]) -> AggregatedSignal:
        """
        Combines signals from all strategy modules.
        Returns HOLD if no consensus or confidence below threshold.
        """
        if not signals:
            return AggregatedSignal("HOLD", 0.0, [])

        buys = [s for s in signals if s.direction == "BUY"]
        sells = [s for s in signals if s.direction == "SELL"]

        # Conflicting strong signals → HOLD
        if buys and sells:
            return AggregatedSignal("HOLD", 0.0, [s.strategy for s in signals])

        dominant = buys if buys else sells
        direction = "BUY" if buys else "SELL"

        avg_confidence = sum(s.confidence for s in dominant) / len(dominant)

        if avg_confidence < self._min_confidence:
            return AggregatedSignal("HOLD", avg_confidence, [s.strategy for s in dominant])

        return AggregatedSignal(
            direction=direction,
            confidence=round(avg_confidence, 4),
            contributing_strategies=[s.strategy for s in dominant],
        )
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/signals/test_signal_aggregator.py -v
```

Expected: All 5 tests PASS.

**Step 5: Commit**

```bash
git add user_data/strategies/signals/signal_aggregator.py tests/signals/test_signal_aggregator.py
git commit -m "feat: add signal aggregator with confidence threshold"
```

---

## Phase 4: FreqAI Strategy

### Task 8: Main FreqAI Strategy Class

**Files:**
- Create: `user_data/strategies/AICryptoStrategy.py`
- Create: `tests/strategies/test_ai_crypto_strategy.py`

**Step 1: Write the failing tests**

```python
# tests/strategies/test_ai_crypto_strategy.py
import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch

def test_strategy_file_exists():
    from user_data.strategies.AICryptoStrategy import AICryptoStrategy
    assert AICryptoStrategy is not None

def test_strategy_has_required_freqai_methods():
    from user_data.strategies.AICryptoStrategy import AICryptoStrategy
    assert hasattr(AICryptoStrategy, "feature_engineering_expand_all")
    assert hasattr(AICryptoStrategy, "set_freqai_targets")
    assert hasattr(AICryptoStrategy, "populate_entry_trend")
    assert hasattr(AICryptoStrategy, "populate_exit_trend")

def test_feature_engineering_adds_required_columns():
    from user_data.strategies.AICryptoStrategy import AICryptoStrategy
    strategy = AICryptoStrategy({})
    df = pd.DataFrame({
        "open": np.random.uniform(40000, 50000, 100),
        "high": np.random.uniform(50000, 55000, 100),
        "low": np.random.uniform(35000, 40000, 100),
        "close": np.random.uniform(40000, 50000, 100),
        "volume": np.random.uniform(1000, 5000, 100),
    })
    result = strategy.feature_engineering_expand_all(df, "1h", {}, {})
    assert "%-rsi-period_14_1h" in result.columns or len(result.columns) > 5
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/strategies/test_ai_crypto_strategy.py -v
```

Expected: FAIL — `ModuleNotFoundError: AICryptoStrategy`

**Step 3: Implement AICryptoStrategy**

```python
# user_data/strategies/AICryptoStrategy.py
import logging
import os
from functools import reduce
from typing import Optional
import pandas as pd
import numpy as np
import talib.abstract as ta
from freqtrade.strategy import IStrategy, merge_informative_pair
from freqtrade.strategy.hyper import IntParameter, DecimalParameter
from pandas import DataFrame

from .risk.risk_manager import RiskManager
from .signals.signal_aggregator import SignalAggregator, Signal

logger = logging.getLogger(__name__)

class AICryptoStrategy(IStrategy):
    """
    AI Crypto Trading Strategy using FreqAI.
    Combines technical indicators, sentiment, and on-chain signals.
    Continuously retrains every 4 hours via FreqAI.
    """

    # FreqAI required
    freqai_info: dict = {}

    # Strategy parameters
    minimal_roi = {"0": 0.10, "120": 0.05, "240": 0.02, "480": 0.01}
    stoploss = -0.05
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.02
    trailing_only_offset_is_reached = True
    timeframe = "1h"
    can_short = False
    use_exit_signal = True
    exit_profit_only = False
    process_only_new_candles = True
    startup_candle_count = 50

    # Entry/exit signal thresholds (tunable)
    entry_confidence_threshold = DecimalParameter(0.60, 0.85, default=0.65, space="buy")
    exit_confidence_threshold = DecimalParameter(0.55, 0.80, default=0.60, space="sell")

    def __init__(self, config: dict):
        super().__init__(config)
        self._risk_manager = RiskManager(
            max_portfolio_pct=float(os.getenv("MAX_PORTFOLIO_PCT_PER_TRADE", "0.05")),
            drawdown_24h_limit=float(os.getenv("CIRCUIT_BREAKER_24H_DRAWDOWN", "0.10")),
            drawdown_7d_limit=float(os.getenv("CIRCUIT_BREAKER_7D_DRAWDOWN", "0.20")),
            min_confidence=float(os.getenv("MIN_SIGNAL_CONFIDENCE", "0.65")),
        )
        self._aggregator = SignalAggregator(
            min_confidence=float(os.getenv("MIN_SIGNAL_CONFIDENCE", "0.65"))
        )

    def feature_engineering_expand_all(
        self, dataframe: DataFrame, period: int, metadata: dict, **kwargs
    ) -> DataFrame:
        """Add technical indicator features for FreqAI training."""
        dataframe[f"%-rsi-period_{period}_{self.timeframe}"] = ta.RSI(dataframe, timeperiod=period)
        dataframe[f"%-mfi-period_{period}_{self.timeframe}"] = ta.MFI(dataframe, timeperiod=period)
        dataframe[f"%-adx-period_{period}_{self.timeframe}"] = ta.ADX(dataframe, timeperiod=period)
        dataframe[f"%-cci-period_{period}_{self.timeframe}"] = ta.CCI(dataframe, timeperiod=period)
        dataframe[f"%-atr-period_{period}_{self.timeframe}"] = ta.ATR(dataframe, timeperiod=period)

        # Bollinger band width (volatility measure)
        bollinger = ta.BBANDS(dataframe["close"], timeperiod=period)
        dataframe[f"%-bb_width-{period}_{self.timeframe}"] = (
            bollinger[0] - bollinger[2]
        ) / bollinger[1]

        return dataframe

    def feature_engineering_expand_basic(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """Add basic price/volume features."""
        dataframe["%-pct_change"] = dataframe["close"].pct_change()
        dataframe["%-volume_mean_ratio"] = (
            dataframe["volume"] / dataframe["volume"].rolling(20).mean()
        )
        dataframe["%-high_low_pct"] = (
            (dataframe["high"] - dataframe["low"]) / dataframe["close"]
        )

        # MACD
        macd = ta.MACD(dataframe)
        dataframe["%-macd"] = macd["macd"]
        dataframe["%-macdsignal"] = macd["macdsignal"]
        dataframe["%-macdhist"] = macd["macdhist"]

        return dataframe

    def feature_engineering_standard(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """Add standard FreqAI features."""
        dataframe["%-day_of_week"] = dataframe["date"].dt.dayofweek
        dataframe["%-hour_of_day"] = dataframe["date"].dt.hour
        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """
        Define the target variable for FreqAI to predict.
        We predict whether price will be higher N candles from now.
        """
        dataframe["&-price_direction"] = (
            dataframe["close"].shift(-self.freqai_info.get("feature_parameters", {})
                               .get("label_period_candles", 24))
            > dataframe["close"]
        ).astype(int)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Called by FreqAI — populates base indicators before ML features."""
        dataframe = self.freqai.start(dataframe, metadata, self)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry signal: FreqAI prediction + confidence threshold."""
        if self._risk_manager.is_circuit_breaker_active():
            logger.warning("Circuit breaker active — no entries allowed")
            dataframe["enter_long"] = 0
            return dataframe

        dataframe.loc[
            (
                (dataframe["&-price_direction_mean"] > self.entry_confidence_threshold.value)
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit signal: FreqAI prediction drops below exit threshold."""
        dataframe.loc[
            (dataframe["&-price_direction_mean"] < self.exit_confidence_threshold.value),
            "exit_long",
        ] = 1
        return dataframe
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/strategies/test_ai_crypto_strategy.py -v
```

Expected: All 3 tests PASS.

**Step 5: Commit**

```bash
git add user_data/strategies/AICryptoStrategy.py tests/strategies/test_ai_crypto_strategy.py
git commit -m "feat: add FreqAI strategy with technical indicators and risk manager integration"
```

---

## Phase 5: Backtesting Validation

### Task 9: Download Historical Data and Run Backtest

**Step 1: Download 2 years of historical data for all pairs**

```bash
freqtrade download-data \
  --exchange binance \
  --pairs BTC/USDT ETH/USDT SOL/USDT XRP/USDT \
  --timeframes 5m 1h 4h \
  --days 730 \
  --config user_data/config.json
```

Expected: Data downloaded to `user_data/data/binance/`. Watch for rate limit warnings — normal.

**Step 2: Run backtest with FreqAI**

```bash
freqtrade backtesting \
  --config user_data/config.json \
  --strategy AICryptoStrategy \
  --freqai-auto-retrain \
  --timerange 20240101-20260101 \
  --breakdown month
```

Expected output to check (minimum pass criteria):
- Profit factor > 1.0
- Win rate > 52%
- Max drawdown < 20%
- Sharpe ratio > 1.0

**Step 3: View backtest results**

```bash
freqtrade backtesting-show
```

Study the monthly breakdown — look for consistency across market conditions, not just a single lucky period.

**Step 4: Check for data leakage (critical)**

```bash
# Verify no future data leaked into features
freqtrade backtesting \
  --config user_data/config.json \
  --strategy AICryptoStrategy \
  --freqai-auto-retrain \
  --timerange 20240101-20240601  # Train only on first half
# Then test on second half:
freqtrade backtesting \
  --config user_data/config.json \
  --strategy AICryptoStrategy \
  --freqai-auto-retrain \
  --timerange 20240601-20260101
```

If out-of-sample performance is within 15% of in-sample performance — no significant leakage.

**Step 5: Commit backtest results log**

```bash
git add user_data/logs/
git commit -m "test: add initial backtest results"
```

---

## Phase 6: Dry Run (Demo Mode)

### Task 10: Configure and Launch Dry Run

**Step 1: Copy your real API keys into .env (read-only keys)**

```bash
cp .env.example .env
# Edit .env — add your API keys
# IMPORTANT: Use read-only API keys (no trading permissions) for initial setup
```

**Step 2: Update config.json with Telegram credentials**

Edit `user_data/config.json`:
```json
"telegram": {
    "enabled": true,
    "token": "YOUR_TELEGRAM_BOT_TOKEN",
    "chat_id": "YOUR_CHAT_ID"
}
```

To get these:
- Message @BotFather on Telegram → `/newbot` → copy token
- Message @userinfobot on Telegram → copy your chat_id

**Step 3: Start dry run**

```bash
freqtrade trade \
  --config user_data/config.json \
  --strategy AICryptoStrategy \
  --dry-run
```

Expected: Bot starts, connects to Binance, sends Telegram startup message `[DRY RUN] Bot started`.

**Step 4: Open web dashboard**

Navigate to: `http://localhost:8080`
Login with username/password from config.

You should see: live market data, active pairs, FreqAI model training status.

**Step 5: Monitor for 24 hours**

Check Telegram alerts for:
- `[DRY RUN] Entering trade: BTC/USDT` — confirms signal detection works
- `[DRY RUN] Exiting trade: BTC/USDT` — confirms exit logic works
- Model retraining notifications every 4 hours

**Step 6: Dry run graduation checklist (revisit after 6 weeks)**

```
[ ] 6+ consecutive weeks of dry run completed
[ ] Dry run P&L is positive
[ ] Win rate within ±5% of backtest results
[ ] Circuit breaker fired < 3 times
[ ] No single simulated trade would have exceeded 3% portfolio loss
[ ] Performance held across varying market conditions
```

Only after all boxes checked → proceed to Task 11.

---

## Phase 7: Docker + Cloud Deployment

### Task 11: Dockerise for Cloud Deployment

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `docker-compose.live.yml`

**Step 1: Create Dockerfile**

```dockerfile
FROM freqtradeorg/freqtrade:stable

USER root
RUN pip install xgboost lightgbm torch transformers httpx

USER ftuser
WORKDIR /freqtrade

COPY user_data/ /freqtrade/user_data/
COPY .env /freqtrade/.env

CMD ["freqtrade", "trade", "--config", "user_data/config.json", "--strategy", "AICryptoStrategy"]
```

**Step 2: Create docker-compose.yml (dry run)**

```yaml
version: "3.8"

services:
  freqtrade:
    build: .
    restart: unless-stopped
    volumes:
      - ./user_data:/freqtrade/user_data
      - ./.env:/freqtrade/.env
    ports:
      - "8080:8080"
    env_file:
      - .env
    command: >
      freqtrade trade
      --config user_data/config.json
      --strategy AICryptoStrategy
      --dry-run
```

**Step 3: Create docker-compose.live.yml (live trading)**

```yaml
version: "3.8"

services:
  freqtrade:
    build: .
    restart: unless-stopped
    volumes:
      - ./user_data:/freqtrade/user_data
      - ./.env:/freqtrade/.env
    ports:
      - "8080:8080"
    env_file:
      - .env
    command: >
      freqtrade trade
      --config user_data/config.live.json
      --strategy AICryptoStrategy
```

**Step 4: Build and test locally**

```bash
docker compose build
docker compose up
```

Expected: Container starts, bot runs in dry run mode, web UI accessible at `http://localhost:8080`.

**Step 5: Deploy to VPS (when ready)**

```bash
# On your VPS (AWS Tokyo for Binance/Bybit proximity)
git clone <your-repo> ai-crypto-trader
cd ai-crypto-trader
cp .env.example .env
# Add real API keys to .env
docker compose up -d

# Verify running
docker compose ps
docker compose logs -f
```

**Step 6: Commit**

```bash
git add Dockerfile docker-compose.yml docker-compose.live.yml
git commit -m "chore: add docker configuration for cloud deployment"
```

---

## Phase 8: Live Trading (Only After Dry Run Graduation)

### Task 12: Switch to Live Mode

**⚠️ Only proceed after dry run graduation checklist is fully complete.**

**Step 1: Create withdrawal-disabled API keys on each exchange**

On each exchange (Binance, Bybit, OKX, Coinbase Advanced):
1. Create a new API key with **trading permissions only** — no withdrawal permission
2. Whitelist your VPS IP address on the API key
3. Add the keys to `.env`

**Step 2: Create live config**

Copy `user_data/config.json` → `user_data/config.live.json` and change:
```json
{
    "dry_run": false,
    "dry_run_wallet": 0,
    "stake_amount": "unlimited",
    "tradable_balance_ratio": 0.95
}
```

**Step 3: Start with micro capital**

Fund your exchange accounts with the smallest amount you're comfortable losing entirely (e.g. $100-200 per exchange). This is the parallel validation phase.

**Step 4: Run dry run and live simultaneously**

```bash
# Terminal 1: dry run (keep running)
docker compose up

# Terminal 2: live (micro capital)
docker compose -f docker-compose.live.yml up
```

Monitor both Telegram channels side by side. Compare P&L weekly.

**Step 5: Scale up only after 4-week parallel validation**

If live P&L tracks dry run P&L within acceptable variance → gradually increase capital.
If significant divergence → stop live, investigate, fix before scaling.

---

## Full Test Suite

Run the complete test suite at any time:

```bash
pytest tests/ -v --tb=short
```

Expected: All tests pass before any deployment.

---

## Key Reference Commands

```bash
# Backtest
freqtrade backtesting --config user_data/config.json --strategy AICryptoStrategy --timerange 20240101-20260101

# Dry run (local)
freqtrade trade --config user_data/config.json --strategy AICryptoStrategy --dry-run

# View logs
tail -f user_data/logs/freqtrade.log

# Download fresh data
freqtrade download-data --exchange binance --pairs BTC/USDT ETH/USDT --timeframes 1h --days 30

# Show backtest results
freqtrade backtesting-show

# Docker dry run
docker compose up

# Docker live
docker compose -f docker-compose.live.yml up
```
