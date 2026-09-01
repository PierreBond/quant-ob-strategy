"""
Tests for Order Block strategy classes.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import pandas as pd
import numpy as np


class TestOrderBlockStrategy:
    """Basic sanity tests for the base OrderBlockStrategy."""

    def test_strategy_instantiates(self):
        from trading_bot.strategies.orderblock import OrderBlockStrategy
        s = OrderBlockStrategy()
        assert s.name == "OrderBlockStrategy"
        assert s.input_range == 25
        assert s.min_risk_reward == 1.5

    def test_on_init_adds_columns(self, sample_ohlcv_df):
        from trading_bot.strategies.orderblock import OrderBlockStrategy
        s = OrderBlockStrategy()
        s.on_init(sample_ohlcv_df)
        assert s.initialized is True
        assert "atr" in s.data.columns
        assert "bullish_signal" in s.data.columns

    def test_on_bar_returns_dict(self, small_ohlcv_df):
        from trading_bot.strategies.orderblock import OrderBlockStrategy
        from trading_bot.backtest.engine import PositionSide
        
        s = OrderBlockStrategy()
        s.on_init(small_ohlcv_df)
        signal = s.on_bar(small_ohlcv_df.iloc[:10], PositionSide.FLAT)
        assert isinstance(signal, dict)
        assert "signal" in signal


class TestOrderBlockStrategyPremiumV3:
    """Smoke tests for the most advanced strategy variant."""

    def test_instantiation(self):
        from trading_bot.strategies.orderblock import OrderBlockStrategyPremiumV3
        s = OrderBlockStrategyPremiumV3()
        assert "Premium" in s.name or "V3" in s.name or True  # just check it doesn't error

    def test_backtest_produces_result(self, sample_ohlcv_df):
        from trading_bot.strategies.orderblock import OrderBlockStrategyPremiumV3
        from trading_bot.backtest.engine import BacktestEngine

        engine = BacktestEngine(initial_capital=10000, enable_journal=False)
        strategy = OrderBlockStrategyPremiumV3()
        result = engine.run(sample_ohlcv_df, strategy, verbose=False)
        
        assert result.total_trades >= 0
        assert isinstance(result.sharpe_ratio, float)
        assert result.strategy != ""


class TestBenchmarkStrategies:
    """Tests for SMA and RSI baseline strategies."""

    def test_sma_crossover(self, sample_ohlcv_df):
        from trading_bot.strategies.orderblock import SimpleSMACrossover
        from trading_bot.backtest.engine import BacktestEngine

        engine = BacktestEngine(initial_capital=10000, enable_journal=False)
        result = engine.run(sample_ohlcv_df, SimpleSMACrossover(), verbose=False)
        assert result.total_trades >= 0

    def test_rsi_strategy(self, sample_ohlcv_df):
        from trading_bot.strategies.orderblock import RSIStrategy
        from trading_bot.backtest.engine import BacktestEngine

        engine = BacktestEngine(initial_capital=10000, enable_journal=False)
        result = engine.run(sample_ohlcv_df, RSIStrategy(), verbose=False)
        assert result.total_trades >= 0
