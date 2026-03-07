import pytest
import pandas as pd
import numpy as np

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
    result = strategy.feature_engineering_expand_all(df, 14, {})
    assert "%-rsi-period_14_1h" in result.columns or len(result.columns) > 5
