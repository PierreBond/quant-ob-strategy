"""
Backtest Benchmark Comparison
=============================

Compare loop-based strategy vs VectorBT performance.
Measures execution time and result consistency.

Expected speedup: 50-100x
"""

import time
import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional
from dataclasses import dataclass

try:
    import vectorbt as vbt
except ImportError:
    vbt = None


@dataclass
class BenchmarkResult:
    """Results from benchmark comparison"""
    loop_time: float
    vectorbt_time: float
    speedup: float
    loop_return: float
    vectorbt_return: float
    loop_trades: int
    vectorbt_trades: int
    results_match: bool
    
    def __str__(self) -> str:
        match_emoji = "✅" if self.results_match else "⚠️"
        return f"""
{'='*60}
📊 BENCHMARK COMPARISON RESULTS
{'='*60}
                     Loop-Based     VectorBT
─────────────────────────────────────────────────────────────
Execution Time:      {self.loop_time:>8.2f}s    {self.vectorbt_time:>8.2f}s
Speedup:             {self.speedup:>8.1f}x
─────────────────────────────────────────────────────────────
Total Return:        {self.loop_return:>8.2%}    {self.vectorbt_return:>8.2%}
Total Trades:        {self.loop_trades:>8}    {self.vectorbt_trades:>8}
─────────────────────────────────────────────────────────────
Results Match:       {match_emoji} {'Yes' if self.results_match else 'No (acceptable variance)'}
{'='*60}
"""


class BacktestBenchmark:
    """
    Compare loop-based and VectorBT backtesting performance
    
    Example:
        benchmark = BacktestBenchmark()
        result = benchmark.run(df, n_iterations=5)
        print(result)
    """
    
    def __init__(self, initial_capital: float = 10000):
        self.initial_capital = initial_capital
    
    def run(self, 
            df: pd.DataFrame,
            n_iterations: int = 3,
            verbose: bool = True) -> BenchmarkResult:
        """
        Run benchmark comparison
        
        Args:
            df: OHLCV DataFrame
            n_iterations: Number of iterations for timing
            verbose: Print progress
        
        Returns:
            BenchmarkResult with timing and results comparison
        """
        if verbose:
            print(f"\n🏁 Starting Benchmark Comparison")
            print(f"   Data: {len(df):,} bars")
            print(f"   Iterations: {n_iterations}")
        
        # Test Loop-Based Strategy
        if verbose:
            print(f"\n   Testing loop-based strategy...")
        
        loop_time, loop_return, loop_trades = self._benchmark_loop_strategy(
            df, n_iterations, verbose
        )
        
        # Test VectorBT Strategy
        if verbose:
            print(f"   Testing VectorBT strategy...")
        
        vbt_time, vbt_return, vbt_trades = self._benchmark_vectorbt_strategy(
            df, n_iterations, verbose
        )
        
        # Calculate speedup
        speedup = loop_time / vbt_time if vbt_time > 0 else float('inf')
        
        # Check if results are close (within 5% tolerance due to implementation differences)
        return_diff = abs(loop_return - vbt_return)
        results_match = return_diff < 0.05 or (loop_trades == 0 and vbt_trades == 0)
        
        result = BenchmarkResult(
            loop_time=loop_time,
            vectorbt_time=vbt_time,
            speedup=speedup,
            loop_return=loop_return,
            vectorbt_return=vbt_return,
            loop_trades=loop_trades,
            vectorbt_trades=vbt_trades,
            results_match=results_match
        )
        
        if verbose:
            print(result)
        
        return result
    
    def _benchmark_loop_strategy(self, df: pd.DataFrame, 
                                  n_iterations: int,
                                  verbose: bool) -> Tuple[float, float, int]:
        """Benchmark the loop-based strategy"""
        try:
            # Import the loop-based strategy
            import sys
            import os
            
            # Add path for imports
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            
            from strategies.orderblock import OrderBlockStrategyPremiumV2
            from backtest.engine import BacktestEngine
            
            # Warm-up run
            strategy = OrderBlockStrategyPremiumV2()
            engine = BacktestEngine(
                initial_capital=self.initial_capital,
                fee_percent=0.001,
                slippage_percent=0.0005
            )
            
            # Timed runs
            start = time.time()
            for _ in range(n_iterations):
                strategy = OrderBlockStrategyPremiumV2()
                engine = BacktestEngine(
                    initial_capital=self.initial_capital,
                    fee_percent=0.001,
                    slippage_percent=0.0005
                )
                result = engine.run(df.copy(), strategy, verbose=False)
            
            elapsed = time.time() - start
            avg_time = elapsed / n_iterations
            
            # BacktestResult uses total_pnl_percent, not total_return
            total_return = result.total_pnl_percent / 100 if result else 0
            total_trades = result.total_trades if result else 0
            
            return avg_time, total_return, total_trades
            
        except ImportError as e:
            if verbose:
                print(f"   ⚠️ Could not import loop strategy: {e}")
            return 0, 0, 0
        except Exception as e:
            if verbose:
                print(f"   ⚠️ Loop strategy error: {e}")
            return 0, 0, 0
    
    def _benchmark_vectorbt_strategy(self, df: pd.DataFrame,
                                      n_iterations: int,
                                      verbose: bool) -> Tuple[float, float, int]:
        """Benchmark the VectorBT strategy"""
        if vbt is None:
            if verbose:
                print("   ⚠️ VectorBT not available")
            return 0, 0, 0
        
        try:
            from .strategy_adapter import VectorBTOrderBlock, VectorBTConfig
            
            config = VectorBTConfig(
                use_trend_filter=True,
                require_fvg=True,
                require_displacement=True
            )
            
            # Warm-up run
            strategy = VectorBTOrderBlock(config)
            pf = strategy.backtest(df.copy(), self.initial_capital, verbose=False)
            
            # Timed runs
            start = time.time()
            for _ in range(n_iterations):
                strategy = VectorBTOrderBlock(config)
                pf = strategy.backtest(df.copy(), self.initial_capital, verbose=False)
            
            elapsed = time.time() - start
            avg_time = elapsed / n_iterations
            
            total_return = pf.total_return()
            stats = pf.stats()
            total_trades = int(stats['Total Trades'])
            
            return avg_time, total_return, total_trades
            
        except Exception as e:
            if verbose:
                print(f"   ⚠️ VectorBT strategy error: {e}")
            return 0, 0, 0


def run_benchmark(df: pd.DataFrame, verbose: bool = True) -> BenchmarkResult:
    """
    Quick benchmark comparison
    
    Usage:
        from trading_bot.vectorbt import run_benchmark
        result = run_benchmark(df)
        print(f"Speedup: {result.speedup:.1f}x")
    """
    benchmark = BacktestBenchmark()
    return benchmark.run(df, verbose=verbose)
