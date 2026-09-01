"""
Tests for BacktestEngine and BacktestResult.
"""
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np
from trading_bot.backtest.engine import BacktestEngine, BacktestResult, PositionSide


class TestBacktestResult:
    """Verify BacktestResult fields and serialization."""

    def test_empty_result_defaults(self):
        r = BacktestResult()
        assert r.total_trades == 0
        assert r.sharpe_ratio == 0.0
        assert r.total_return_pct == 0.0
        assert r.max_drawdown_pct == 0.0
        assert r.strategy == ""

    def test_to_dict_contains_new_fields(self):
        r = BacktestResult(
            total_trades=10,
            sharpe_ratio=1.5,
            total_return_pct=12.34,
            max_drawdown_pct=5.67,
            strategy="TestStrategy",
        )
        d = r.to_dict()
        assert d["sharpe_ratio"] == 1.5
        assert d["total_return_pct"] == 12.34
        assert d["max_drawdown_pct"] == 5.67
        assert d["strategy"] == "TestStrategy"

    def test_to_dict_keys_complete(self):
        d = BacktestResult().to_dict()
        expected_keys = {
            "total_trades", "win_rate", "winning_trades", "losing_trades",
            "total_pnl", "total_pnl_percent", "total_return_pct",
            "avg_win", "avg_loss", "best_trade", "worst_trade",
            "profit_factor", "max_drawdown", "max_drawdown_pct",
            "sharpe_ratio", "avg_trade_duration", "strategy",
            "trades", "equity_curve",
        }
        assert set(d.keys()) == expected_keys


class TestBacktestEngine:
    """Core backtest engine tests."""

    def test_engine_initializes(self):
        engine = BacktestEngine(initial_capital=10000)
        assert engine.capital == 10000
        assert engine.position == PositionSide.FLAT

    def test_run_with_flat_strategy(self, sample_ohlcv_df):
        """A strategy that never trades should produce 0 trades, 0 PnL."""
        from trading_bot.backtest.engine import Strategy
        
        engine = BacktestEngine(initial_capital=10000, enable_journal=False)
        strategy = Strategy(name="DoNothing")
        result = engine.run(sample_ohlcv_df, strategy, verbose=False)

        assert result.total_trades == 0
        assert result.total_pnl == 0.0
        assert result.sharpe_ratio == 0.0
        assert result.strategy == "DoNothing"

    def test_sharpe_ratio_is_computed(self, sample_ohlcv_df):
        """Run SMA crossover and check Sharpe is a finite number."""
        try:
            from trading_bot.strategies.orderblock import SimpleSMACrossover
        except ImportError:
            pytest.skip("SimpleSMACrossover not importable")

        engine = BacktestEngine(initial_capital=10000, enable_journal=False)
        strategy = SimpleSMACrossover()
        result = engine.run(sample_ohlcv_df, strategy, verbose=False)

        assert np.isfinite(result.sharpe_ratio)
        assert isinstance(result.sharpe_ratio, float)

    def test_result_json_roundtrip(self, sample_ohlcv_df):
        """to_dict() should produce JSON-serializable output."""
        import json
        from trading_bot.backtest.engine import Strategy

        engine = BacktestEngine(initial_capital=10000, enable_journal=False)
        result = engine.run(sample_ohlcv_df, Strategy("Test"), verbose=False)
        serialized = json.dumps(result.to_dict(), default=str)
        assert isinstance(serialized, str)
        parsed = json.loads(serialized)
        assert "sharpe_ratio" in parsed
        assert "total_return_pct" in parsed
        assert "max_drawdown_pct" in parsed
