import logging
import os
import talib.abstract as ta
from freqtrade.strategy import IStrategy, DecimalParameter
from pandas import DataFrame

from .risk.risk_manager import RiskManager
from .signals.signal_aggregator import SignalAggregator

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
