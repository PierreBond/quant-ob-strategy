"""
Base Strategy Class
====================
Foundation for all trading strategies
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from abc import ABC, abstractmethod
import pandas as pd


@dataclass
class Signal:
    """Trading signal output"""
    signal: str  # LONG, SHORT, FLAT
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    size: float = 0.0
    confidence: float = 1.0  # 0-1
    reason: str = ""
    timestamp: datetime = None

    def to_dict(self) -> Dict:
        return {
            'signal': self.signal,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'size': self.size,
            'confidence': self.confidence,
            'reason': self.reason,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }


class Strategy(ABC):
    """
    Base class for all trading strategies

    Usage:
    1. Subclass this strategy
    2. Implement on_init() to setup indicators
    3. Implement on_bar() to generate signals
    4. Override parameters as needed
    """

    def __init__(self, name: str = "BaseStrategy"):
        self.name = name
        self.parameters = {}
        self.data = pd.DataFrame()
        self.initialized = False

    def set_parameters(self, **kwargs):
        """Configure strategy parameters"""
        self.parameters.update(kwargs)
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def configure(self, **kwargs):
        """Alias for set_parameters"""
        self.set_parameters(**kwargs)

    @abstractmethod
    def on_init(self, df: pd.DataFrame):
        """
        Initialize strategy with historical data

        Args:
            df: DataFrame with OHLCV data (index=datetime)

        This is called once at the start with the full dataset.
        Use it to calculate indicators and detect patterns.
        """
        pass

    @abstractmethod
    def on_bar(self, df: pd.DataFrame, position: str = "FLAT") -> Dict:
        """
        Generate signal for the current bar

        Args:
            df: DataFrame with OHLCV data (current bar included)
            position: Current position status ("LONG", "SHORT", "FLAT")

        Returns:
            Dict with:
            - signal: "LONG", "SHORT", or "FLAT"
            - sl: stop loss price (optional)
            - tp: take profit price (optional)
            - size: position size 0-1 (optional)
        """
        pass

    def on_tick(self, price: float, volume: float = 0) -> Dict:
        """
        Optional: Handle real-time tick data

        Args:
            price: Current price
            volume: Current volume

        Returns:
            Signal dict (or empty dict for no action)
        """
        return {}

    def on_order_fill(self, order: Dict):
        """Optional: Handle order fill notification"""
        pass

    def on_position_change(self, position: Dict):
        """Optional: Handle position change notification"""
        pass

    def get_indicator(self, name: str, index: int = -1):
        """Get indicator value from data"""
        if not self.initialized or name not in self.data.columns:
            return None
        return self.data[name].iloc[index]

    def get_parameters(self) -> Dict:
        """Get current parameters"""
        return self.parameters.copy()

    def reset(self):
        """Reset strategy state"""
        self.data = pd.DataFrame()
        self.initialized = False


# ============================================================================
# SIMPLE EXAMPLE STRATEGIES
# ============================================================================

class BuyAndHold(Strategy):
    """Simple buy and hold strategy"""

    def __init__(self):
        super().__init__("BuyAndHold")
        self.bought = False

    def on_init(self, df: pd.DataFrame):
        self.data = df.copy()
        self.initialized = True

    def on_bar(self, df: pd.DataFrame, position: str = "FLAT") -> Dict:
        if not self.bought:
            self.bought = True
            return {
                'signal': 'LONG',
                'sl': df.iloc[-1]['close'] * 0.90,  # 10% stop loss
                'tp': None,
                'size': 1.0
            }
        return {'signal': 'FLAT'}


class SimpleMA(Strategy):
    """Moving average crossover strategy"""

    def __init__(self, fast_ma: int = 10, slow_ma: int = 20):
        super().__init__(f"MA_{fast_ma}_{slow_ma}")
        self.fast_ma = fast_ma
        self.slow_ma = slow_ma

    def on_init(self, df: pd.DataFrame):
        df = df.copy()
        df['ma_fast'] = df['close'].rolling(self.fast_ma).mean()
        df['ma_slow'] = df['close'].rolling(self.slow_ma).mean()
        self.data = df
        self.initialized = True

    def on_bar(self, df: pd.DataFrame, position: str = "FLAT") -> Dict:
        if len(df) < 2:
            return {'signal': 'FLAT'}

        ma_fast = df['ma_fast'].iloc[-1]
        ma_fast_prev = df['ma_fast'].iloc[-2]
        ma_slow = df['ma_slow'].iloc[-1]
        ma_slow_prev = df['ma_slow'].iloc[-2]

        # Golden cross (bullish)
        if ma_fast_prev <= ma_slow_prev and ma_fast > ma_slow:
            return {
                'signal': 'LONG',
                'sl': df.iloc[-1]['low'] * 0.99,
                'tp': df.iloc[-1]['close'] * 1.02,
                'size': 0.5
            }

        # Death cross (bearish)
        elif ma_fast_prev >= ma_slow_prev and ma_fast < ma_slow:
            return {
                'signal': 'SHORT',
                'sl': df.iloc[-1]['high'] * 1.01,
                'tp': df.iloc[-1]['close'] * 0.98,
                'size': 0.5
            }

        return {'signal': 'FLAT'}
