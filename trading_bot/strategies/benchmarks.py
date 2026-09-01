"""
Benchmark Strategies
====================
Simple strategies (SMA Crossover, RSI) for testing and baseline comparison.
"""

from typing import Dict
import pandas as pd

# Handle imports
try:
    from .base import Strategy
    from ..backtest.engine import PositionSide
except ImportError:
    PositionSide = None

    class Strategy:
        """Fallback base strategy class"""
        def __init__(self, name: str = "BaseStrategy"):
            self.name = name
            self.parameters = {}
            self.data = None
            self.initialized = False


class SimpleSMACrossover(Strategy):
    """Simple SMA Crossover Strategy for testing"""

    def __init__(self, fast_period: int = 10, slow_period: int = 20):
        super().__init__(f"SMA_{fast_period}_{slow_period}")
        self.fast_period = fast_period
        self.slow_period = slow_period

    def on_init(self, df: pd.DataFrame):
        df = df.copy()
        df['sma_fast'] = df['close'].rolling(self.fast_period).mean()
        df['sma_slow'] = df['close'].rolling(self.slow_period).mean()
        self.data = df
        self.initialized = True

    def on_bar(self, df: pd.DataFrame, position: PositionSide = None) -> Dict:
        if len(df) < 2:
            return {'signal': 'FLAT'}

        idx = len(df) - 1
        if idx >= len(self.data) or idx < 1:
            return {'signal': 'FLAT'}

        current = self.data.iloc[idx]
        prev = self.data.iloc[idx - 1]

        # Skip if SMA values are NaN (not enough data yet)
        if pd.isna(current.get('sma_fast')) or pd.isna(current.get('sma_slow')):
            return {'signal': 'FLAT'}
        if pd.isna(prev.get('sma_fast')) or pd.isna(prev.get('sma_slow')):
            return {'signal': 'FLAT'}

        # Golden cross
        if prev['sma_fast'] <= prev['sma_slow'] and current['sma_fast'] > current['sma_slow']:
            return {
                'signal': 'LONG',
                'sl': current['close'] * 0.98,
                'tp': current['close'] * 1.04,
                'size': 0.5
            }

        # Death cross
        if prev['sma_fast'] >= prev['sma_slow'] and current['sma_fast'] < current['sma_slow']:
            return {
                'signal': 'SHORT',
                'sl': current['close'] * 1.02,
                'tp': current['close'] * 0.96,
                'size': 0.5
            }

        return {'signal': 'FLAT'}


class RSIStrategy(Strategy):
    """RSI Mean Reversion Strategy"""

    def __init__(self, rsi_period: int = 14, oversold: int = 30, overbought: int = 70):
        super().__init__(f"RSI_{rsi_period}_{oversold}_{overbought}")
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought

    def on_init(self, df: pd.DataFrame):
        df = df.copy()
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / (loss + 1e-10)
        df['rsi'] = 100 - (100 / (1 + rs))
        self.data = df
        self.initialized = True

    def on_bar(self, df: pd.DataFrame, position: PositionSide = None) -> Dict:
        idx = len(df) - 1
        if idx >= len(self.data) or idx < 0:
            return {'signal': 'FLAT'}

        current = self.data.iloc[idx]
        rsi = current.get('rsi')

        if pd.isna(rsi):
            return {'signal': 'FLAT'}

        if rsi < self.oversold:
            return {
                'signal': 'LONG',
                'sl': current['close'] * 0.98,
                'tp': current['close'] * 1.04,
                'size': 0.5
            }
        elif rsi > self.overbought:
            return {
                'signal': 'SHORT',
                'sl': current['close'] * 1.02,
                'tp': current['close'] * 0.96,
                'size': 0.5
            }

        return {'signal': 'FLAT'}
