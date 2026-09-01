"""
Shared test fixtures and sample data generators.
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime


@pytest.fixture
def sample_ohlcv_df():
    """Generate a deterministic 30-day OHLCV DataFrame for testing."""
    n_bars = 30 * 96  # 96 bars/day at 15-min candles
    dates = pd.date_range(start="2025-01-01", periods=n_bars, freq="15min")

    np.random.seed(42)
    price = 90_000.0
    opens, highs, lows, closes, volumes = [], [], [], [], []

    for _ in range(n_bars):
        change = np.random.randn() * 150
        o = price
        c = price + change
        h = max(o, c) + np.random.rand() * 100
        l = min(o, c) - np.random.rand() * 100
        v = 500 + np.random.rand() * 1000
        opens.append(o)
        highs.append(h)
        lows.append(l)
        closes.append(c)
        volumes.append(v)
        price = c

    df = pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=dates,
    )
    return df


@pytest.fixture
def small_ohlcv_df():
    """Tiny 50-bar DataFrame for fast unit tests."""
    dates = pd.date_range(start="2025-06-01", periods=50, freq="15min")
    np.random.seed(99)
    price = 100_000.0
    opens, highs, lows, closes, volumes = [], [], [], [], []
    for _ in range(50):
        change = np.random.randn() * 80
        o = price
        c = price + change
        h = max(o, c) + np.random.rand() * 50
        l = min(o, c) - np.random.rand() * 50
        opens.append(o)
        highs.append(h)
        lows.append(l)
        closes.append(c)
        volumes.append(500 + np.random.rand() * 500)
        price = c

    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=dates,
    )
