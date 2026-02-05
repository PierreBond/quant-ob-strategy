"""
VectorBT Integration Module
==========================

Provides 100x faster backtesting using vectorized operations.

Features:
- Vectorized Order Block strategy
- Parameter optimization
- Walk-forward analysis
- Performance analytics
- Benchmark comparisons
"""

from .strategy_adapter import VectorBTOrderBlock, VectorBTStrategyAdapter
from .optimizer import ParameterOptimizer, OptimizationResult
from .walk_forward import WalkForwardAnalyzer
from .benchmark import BacktestBenchmark

__all__ = [
    'VectorBTOrderBlock',
    'VectorBTStrategyAdapter', 
    'ParameterOptimizer',
    'OptimizationResult',
    'WalkForwardAnalyzer',
    'BacktestBenchmark'
]
