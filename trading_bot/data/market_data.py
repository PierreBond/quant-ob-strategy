"""
Market Data Module
==================
Fetch and manage OHLCV data from exchanges using CCXT
"""

import os
import json
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Union
from dataclasses import dataclass, field
import pandas as pd
import numpy as np
from pathlib import Path

# CCXT for exchange connectivity
try:
    import ccxt
except ImportError:
    print("Installing ccxt...")
    import subprocess
    subprocess.run(["pip", "install", "ccxt", "-q"])
    import ccxt

# Handle relative imports
try:
    from ..config.settings import DataConfig, EXCHANGE, SYMBOL, TIMEFRAME, TESTNET
except ImportError:
    # Standalone mode
    EXCHANGE = "binance"
    SYMBOL = "BTC/USDT"
    TIMEFRAME = "15m"
    TESTNET = True

    class DataConfig:
        DATA_SOURCE = "exchange"
        DATA_DIR = "data"
        CACHE_ENABLED = True
        CACHE_DIR = "cache"
        START_DATE = None
        END_DATE = None


@dataclass
class OHLCV:
    """Single OHLCV candle data"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume
        }

    @classmethod
    def from_list(cls, data: List) -> 'OHLCV':
        """Create from CCXT format [timestamp, open, high, low, close, volume]"""
        return cls(
            timestamp=datetime.fromtimestamp(data[0] / 1000),
            open=float(data[1]),
            high=float(data[2]),
            low=float(data[3]),
            close=float(data[4]),
            volume=float(data[5])
        )


@dataclass
class MarketDataConfig:
    """Configuration for market data fetching"""
    exchange_id: str = EXCHANGE
    symbol: str = SYMBOL
    timeframe: str = TIMEFRAME
    testnet: bool = TESTNET
    cache_enabled: bool = True
    cache_dir: str = "cache"
    max_candles: int = 1000  # Per request


class ExchangeClient:
    """CCXT exchange client wrapper"""

    def __init__(self, config: MarketDataConfig):
        self.config = config
        self.exchange = self._init_exchange()

    def _init_exchange(self):
        """Initialize exchange instance"""
        exchange_class = getattr(ccxt, self.config.exchange_id)

        kwargs = {
            'enableRateLimit': True,
            'timeout': 30000,  # 30 seconds
        }

        # Add testnet credentials if needed
        if self.config.testnet:
            if self.config.exchange_id == 'binance':
                kwargs['options'] = {'defaultType': 'spot'}
            # Add testnet API keys here if needed

        return exchange_class(kwargs)

    def fetch_ohlcv(self,
                    since: Optional[datetime] = None,
                    limit: int = 1000) -> List[OHLCV]:
        """
        Fetch OHLCV candles

        Args:
            since: Start datetime (None = recent)
            limit: Max candles to fetch

        Returns:
            List of OHLCV candles
        """
        try:
            # Prepare parameters
            params = {
                'symbol': self.config.symbol,
                'timeframe': self.config.timeframe,
                'limit': limit,
            }

            if since:
                params['since'] = int(since.timestamp() * 1000)

            # Fetch data
            data = self.exchange.fetch_ohlcv(**params)

            # Convert to OHLCV objects
            ohlcv = [OHLCV.from_list(candle) for candle in data]

            return ohlcv

        except Exception as e:
            print(f"Error fetching OHLCV: {e}")
            return []

    def fetch_latest_ohlcv(self, count: int = 1) -> List[OHLCV]:
        """Fetch latest N candles"""
        return self.fetch_ohlcv(limit=count)

    def get_current_price(self) -> float:
        """Get current ticker price"""
        try:
            ticker = self.exchange.fetch_ticker(self.config.symbol)
            return ticker['last']
        except Exception as e:
            print(f"Error fetching price: {e}")
            return 0.0


class DataManager:
    """
    Manage market data - fetch, cache, and provide DataFrames
    """

    def __init__(self,
                 config: Optional[MarketDataConfig] = None,
                 cache_dir: str = "cache"):
        self.config = config or MarketDataConfig()
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

        self.exchange_client: Optional[ExchangeClient] = None
        self._cache = {}

    def connect(self) -> bool:
        """Connect to exchange"""
        try:
            self.exchange_client = ExchangeClient(self.config)
            # Test connection
            self.exchange_client.get_current_price()
            print(f"✓ Connected to {self.config.exchange_id}")
            return True
        except Exception as e:
            print(f"✗ Failed to connect to {self.config.exchange_id}: {e}")
            return False

    def fetch_historical(self,
                         start_date: datetime,
                         end_date: datetime) -> pd.DataFrame:
        """
        Fetch historical data between dates

        Args:
            start_date: Start datetime
            end_date: End datetime

        Returns:
            DataFrame with OHLCV data
        """
        cache_key = f"{self.config.symbol}_{self.config.timeframe}_{start_date.date()}_{end_date.date()}"

        # Check cache
        if self.config.cache_enabled and cache_key in self._cache:
            print(f"✓ Using cached data for {cache_key}")
            return self._cache[cache_key]

        # Fetch from exchange
        candles = []
        current = start_date

        while current < end_date:
            batch = self.exchange_client.fetch_ohlcv(
                since=current,
                limit=self.config.max_candles
            )

            if not batch:
                break

            candles.extend(batch)

            # Update current to last timestamp
            if batch:
                current = batch[-1].timestamp + timedelta(
                    minutes=self._timeframe_to_minutes()
                )

        # Convert to DataFrame
        df = self._candles_to_dataframe(candles)

        # Cache
        if self.config.cache_enabled:
            self._cache[cache_key] = df
            self._save_cache(cache_key, df)

        return df

    def fetch_recent(self, days: int = 30) -> pd.DataFrame:
        """Fetch recent N days of data"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        return self.fetch_historical(start_date, end_date)

    def get_latest_candle(self) -> pd.DataFrame:
        """Get latest candle as DataFrame"""
        ohlcv = self.exchange_client.fetch_latest_ohlcv(1)
        if ohlcv:
            return self._candles_to_dataframe(ohlcv)
        return pd.DataFrame()

    def _timeframe_to_minutes(self) -> int:
        """Convert timeframe string to minutes"""
        timeframe_map = {
            '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
            '1h': 60, '2h': 120, '4h': 240, '6h': 360, '12h': 720,
            '1d': 1440, '1w': 10080
        }
        return timeframe_map.get(self.config.timeframe, 15)

    def _candles_to_dataframe(self, candles: List[OHLCV]) -> pd.DataFrame:
        """Convert OHLCV list to DataFrame"""
        if not candles:
            return pd.DataFrame()

        data = {
            'timestamp': [c.timestamp for c in candles],
            'open': [c.open for c in candles],
            'high': [c.high for c in candles],
            'low': [c.low for c in candles],
            'close': [c.close for c in candles],
            'volume': [c.volume for c in candles]
        }

        df = pd.DataFrame(data)
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)

        return df

    def _save_cache(self, key: str, df: pd.DataFrame):
        """Save DataFrame to cache"""
        filepath = self.cache_dir / f"{key}.parquet"
        df.to_parquet(filepath)

    def load_cache(self, key: str) -> Optional[pd.DataFrame]:
        """Load DataFrame from cache"""
        filepath = self.cache_dir / f"{key}.parquet"
        if filepath.exists():
            return pd.read_parquet(filepath)
        return None


# ============================================================================
# DATA LOADERS
# ============================================================================

def load_csv(filepath: str, index_col: str = 'timestamp') -> pd.DataFrame:
    """Load OHLCV data from CSV"""
    df = pd.read_csv(filepath, index_col=index_col, parse_dates=True)
    return df


def load_parquet(filepath: str) -> pd.DataFrame:
    """Load OHLCV data from Parquet"""
    df = pd.read_parquet(filepath)
    return df


def load_from_config(config: DataConfig) -> pd.DataFrame:
    """Load data based on config settings"""
    data_dir = Path(config.DATA_DIR)

    if config.START_DATE and config.END_DATE:
        # Look for date-specific file
        filename = f"{SYMBOL.replace('/', '_')}_{TIMEFRAME}_{config.START_DATE}_{config.END_DATE}.parquet"
        filepath = data_dir / filename

        if filepath.exists():
            return load_parquet(str(filepath))

    # Default: load recent
    dm = DataManager()
    dm.connect()
    return dm.fetch_recent(days=30)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def resample_data(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Resample data to different timeframe"""
    resample_map = {
        '15m': '15min', '1h': '1H', '4h': '4H', '1d': '1D'
    }

    return df.resample(resample_map.get(timeframe, '15min')).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add common technical indicators"""
    # Simple moving averages
    df['sma_20'] = df['close'].rolling(window=20).mean()
    df['sma_50'] = df['close'].rolling(window=50).mean()
    df['sma_200'] = df['close'].rolling(window=200).mean()

    # Exponential moving averages
    df['ema_12'] = df['close'].ewm(span=12).mean()
    df['ema_26'] = df['close'].ewm(span=26).mean()

    # MACD
    df['macd'] = df['ema_12'] - df['ema_26']
    df['macd_signal'] = df['macd'].ewm(span=9).mean()

    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # Bollinger Bands
    df['bb_middle'] = df['close'].rolling(window=20).mean()
    bb_std = df['close'].rolling(window=20).std()
    df['bb_upper'] = df['bb_middle'] + 2 * bb_std
    df['bb_lower'] = df['bb_middle'] - 2 * bb_std

    # ATR
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(window=14).mean()

    return df


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    # Quick test
    dm = DataManager()
    if dm.connect():
        df = dm.fetch_recent(days=7)
        df = add_indicators(df)
        print(f"Loaded {len(df)} candles")
        print(df.tail())
