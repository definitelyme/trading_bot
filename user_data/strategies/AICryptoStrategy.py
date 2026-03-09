import logging
import os
import pandas as pd
import talib.abstract as ta
from datetime import datetime, timedelta
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, DecimalParameter
from pandas import DataFrame

import sys
from pathlib import Path

# Freqtrade loads strategies as standalone files, so we need to add the
# strategies directory to sys.path for sub-module imports to work.
_strategies_dir = str(Path(__file__).parent)
if _strategies_dir not in sys.path:
    sys.path.insert(0, _strategies_dir)

from risk.risk_manager import RiskManager
from risk.pair_allocator import PairAllocator, TradeResult
from signals.signal_aggregator import SignalAggregator

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
            min_confidence=float(os.getenv("MIN_SIGNAL_CONFIDENCE", "0.55")),
        )
        self._aggregator = SignalAggregator(
            min_confidence=float(os.getenv("MIN_SIGNAL_CONFIDENCE", "0.55"))
        )
        pairs = config.get("exchange", {}).get("pair_whitelist", [])
        self._pair_allocator = PairAllocator(
            pairs=pairs,
            window_days=int(os.getenv("PAIR_ALLOC_WINDOW_DAYS", "30")),
            min_trades=int(os.getenv("PAIR_ALLOC_MIN_TRADES", "5")),
            exploration_pct=float(os.getenv("PAIR_ALLOC_EXPLORATION_PCT", "0.10")),
            pf_threshold=float(os.getenv("PAIR_ALLOC_PF_THRESHOLD", "0.7")),
            pf_cap=float(os.getenv("PAIR_ALLOC_PF_CAP", "5.0")),
            min_stake=float(os.getenv("PAIR_ALLOC_MIN_STAKE", "10.0")),
            refresh_hours=int(os.getenv("PAIR_ALLOC_REFRESH_HOURS", "4")),
        )

    def _refresh_allocator(self) -> None:
        cutoff = datetime.utcnow() - timedelta(days=self._pair_allocator.window_days)
        trades_by_pair: dict[str, list[TradeResult]] = {}
        for pair in self._pair_allocator.pairs:
            raw_trades = Trade.get_trades_proxy(pair=pair, is_open=False)
            trades_by_pair[pair] = [
                TradeResult(profit_abs=t.close_profit_abs, close_date=t.close_date)
                for t in raw_trades
                if t.close_date and t.close_date >= cutoff
            ]
        self._pair_allocator.refresh_weights(trades_by_pair)

    def _get_total_portfolio_value(self) -> float:
        free = self.wallets.get_free(self.config.get("stake_currency", "USDT"))
        deployed = sum(
            t.stake_amount for t in Trade.get_trades_proxy(is_open=True)
        )
        return free + deployed

    def _get_model_confidence(self, pair: str) -> float:
        """Convert raw prediction to 0-1 confidence via percentile rank."""
        df = self.dp.get_pair_dataframe(pair=pair, timeframe=self.timeframe)
        if df.empty or "&-price_change" not in df.columns:
            return 0.0
        predictions = df["&-price_change"].dropna()
        if len(predictions) < 10:
            return 0.0
        current = predictions.iloc[-1]
        abs_preds = predictions.abs()
        current_abs = abs(current)
        rank = (abs_preds < current_abs).sum() / len(abs_preds)
        return round(rank, 4)

    def _get_current_atr_pct(self, pair: str) -> float:
        df = self.dp.get_pair_dataframe(pair=pair, timeframe=self.timeframe)
        if df.empty:
            return 0.05  # conservative default
        atr_cols = [c for c in df.columns if c.startswith("%-atr-")]
        if not atr_cols:
            return 0.05
        atr_val = df[atr_cols[0]].iloc[-1]
        close_val = df["close"].iloc[-1]
        if pd.isna(atr_val) or pd.isna(close_val) or close_val == 0:
            return 0.05
        return atr_val / close_val

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: float | None,
        max_stake: float,
        leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        if self._pair_allocator.needs_refresh():
            self._refresh_allocator()

        weight = self._pair_allocator.get_weight(pair)
        if weight <= 0:
            return 0

        total_portfolio = self._get_total_portfolio_value()
        base_stake = total_portfolio * weight

        # Cap with RiskManager (Quarter-Kelly + ATR)
        confidence = self._get_model_confidence(pair)
        atr_pct = self._get_current_atr_pct(pair)
        risk_cap = self._risk_manager.calculate_position_size(
            portfolio_value=total_portfolio,
            confidence=confidence,
            atr_pct=atr_pct,
        )
        if risk_cap > 0:
            base_stake = min(base_stake, risk_cap)
        else:
            logger.info(
                "Skipping %s: risk_cap=$0 (low confidence=%.4f)", pair, confidence
            )
            return 0

        # Enforce exchange minimum
        effective_min = min_stake or 0
        if base_stake < effective_min:
            logger.info(
                "Skipping %s: stake $%.2f < exchange min $%.2f",
                pair, base_stake, effective_min,
            )
            return 0

        # Cap by available balance and max_stake
        available = self.wallets.get_available_stake_amount()
        final_stake = min(base_stake, available, max_stake)

        logger.info(
            "Allocating %s: weight=%.3f, base=$%.2f, risk_cap=$%.2f, final=$%.2f",
            pair, weight, total_portfolio * weight, risk_cap, final_stake,
        )
        return final_stake

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
        Predict the percentage price change over the next N candles (continuous).
        """
        label_period = self.freqai_info.get("feature_parameters", {}).get(
            "label_period_candles", 24
        )
        dataframe["&-price_change"] = (
            dataframe["close"].shift(-label_period) - dataframe["close"]
        ) / dataframe["close"]
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Called by FreqAI — populates base indicators before ML features."""
        dataframe = self.freqai.start(dataframe, metadata, self)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry signal: predicted price change exceeds threshold."""
        if self._risk_manager.is_circuit_breaker_active():
            logger.warning("Circuit breaker active — no entries allowed")
            dataframe["enter_long"] = 0
            return dataframe

        dataframe.loc[
            (
                (dataframe["&-price_change"] > 0.015)
                & (dataframe["do_predict"] == 1)
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit signal: predicted price change is negative."""
        dataframe.loc[
            (dataframe["&-price_change"] < 0),
            "exit_long",
        ] = 1
        return dataframe
