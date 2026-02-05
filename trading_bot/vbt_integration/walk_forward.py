"""
Walk-Forward Analysis
====================

Validates strategy robustness by testing on out-of-sample data.
Prevents overfitting by using rolling train/test windows.

How it works:
1. Split data into training and testing windows
2. Optimize parameters on training window
3. Test on unseen data (testing window)
4. Roll window forward and repeat
5. Average results across all windows

If test results ≈ train results → Strategy is robust
If test results << train results → Overfitting detected
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
import warnings

warnings.filterwarnings('ignore', category=FutureWarning)

try:
    import vectorbt as vbt
except ImportError:
    raise ImportError("VectorBT not installed. Run: pip install vectorbt")

from .optimizer import ParameterOptimizer, OptimizationResult


@dataclass
class WalkForwardWindow:
    """Single walk-forward window result"""
    window_num: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    best_params: Dict[str, Any]
    train_sharpe: float
    train_return: float
    test_sharpe: float
    test_return: float
    test_win_rate: float
    test_trades: int
    overfitting_gap: float  # train_sharpe - test_sharpe


@dataclass
class WalkForwardResult:
    """Complete walk-forward analysis result"""
    windows: List[WalkForwardWindow]
    avg_train_sharpe: float
    avg_test_sharpe: float
    avg_overfitting_gap: float
    total_test_return: float
    is_robust: bool
    robustness_score: float  # 0-100
    analysis_time: float
    
    def to_dict(self) -> Dict:
        return {
            'avg_train_sharpe': self.avg_train_sharpe,
            'avg_test_sharpe': self.avg_test_sharpe,
            'avg_overfitting_gap': self.avg_overfitting_gap,
            'total_test_return': self.total_test_return,
            'is_robust': self.is_robust,
            'robustness_score': self.robustness_score,
            'num_windows': len(self.windows)
        }
    
    def __str__(self) -> str:
        lines = [
            f"\n{'='*70}",
            f"📊 WALK-FORWARD ANALYSIS RESULTS",
            f"{'='*70}",
            f"Total Windows:        {len(self.windows)}",
            f"Analysis Time:        {self.analysis_time:.2f} seconds",
            f"{'─'*70}",
            f"PERFORMANCE METRICS:",
            f"  Avg Train Sharpe:   {self.avg_train_sharpe:.2f}",
            f"  Avg Test Sharpe:    {self.avg_test_sharpe:.2f}",
            f"  Overfitting Gap:    {self.avg_overfitting_gap:.2f}",
            f"  Total Test Return:  {self.total_test_return:.2%}",
            f"{'─'*70}",
            f"ROBUSTNESS ASSESSMENT:",
            f"  Score:    {self.robustness_score:.0f}/100",
            f"  Verdict:  {'✅ ROBUST' if self.is_robust else '⚠️ OVERFITTING DETECTED'}",
            f"{'─'*70}",
            f"WINDOW DETAILS:",
        ]
        
        for w in self.windows:
            status = "✅" if w.overfitting_gap < 0.5 else "⚠️"
            lines.append(
                f"  [{w.window_num}] Train: {w.train_sharpe:.2f} → Test: {w.test_sharpe:.2f} "
                f"(Gap: {w.overfitting_gap:+.2f}) {status}"
            )
        
        lines.append(f"{'='*70}\n")
        return '\n'.join(lines)


class WalkForwardAnalyzer:
    """
    Walk-Forward Analysis for strategy validation
    
    Example:
        analyzer = WalkForwardAnalyzer()
        
        result = analyzer.analyze(
            df=historical_data,
            train_days=210,    # 7 months training
            test_days=90,      # 3 months testing
            step_days=30       # 1 month step
        )
        
        print(result)
        
        if result.is_robust:
            print("Strategy is validated!")
        else:
            print("Strategy may be overfit!")
    """
    
    def __init__(self,
                 initial_capital: float = 10000,
                 fee_pct: float = 0.001,
                 slippage_pct: float = 0.0005,
                 param_ranges: Optional[Dict[str, List]] = None):
        """
        Args:
            initial_capital: Starting capital for backtests
            fee_pct: Trading fee percentage
            slippage_pct: Slippage percentage
            param_ranges: Parameter ranges for optimization (uses defaults if None)
        """
        self.initial_capital = initial_capital
        self.fee_pct = fee_pct
        self.slippage_pct = slippage_pct
        
        # Default parameter ranges for optimization
        self.param_ranges = param_ranges or {
            'input_range': [20, 25, 30],
            'max_age_bars': [100, 150, 200],
            'tp_rr_mult': [2.0, 2.5, 3.0]
        }
        
        self.optimizer = ParameterOptimizer(
            initial_capital=initial_capital,
            fee_pct=fee_pct,
            slippage_pct=slippage_pct
        )
    
    def _bars_per_day(self, timeframe: str = '15m') -> int:
        """Calculate number of bars per day for given timeframe"""
        tf_map = {
            '1m': 1440, '3m': 480, '5m': 288, '15m': 96,
            '30m': 48, '1h': 24, '2h': 12, '4h': 6, '1d': 1
        }
        return tf_map.get(timeframe, 96)
    
    def analyze(self,
                df: pd.DataFrame,
                train_days: int = 210,
                test_days: int = 90,
                step_days: int = 30,
                timeframe: str = '15m',
                verbose: bool = True) -> WalkForwardResult:
        """
        Run walk-forward analysis
        
        Args:
            df: Historical OHLCV data
            train_days: Number of days in training window
            test_days: Number of days in testing window
            step_days: Number of days to step forward each iteration
            timeframe: Candle timeframe (for bar calculation)
            verbose: Print progress
        
        Returns:
            WalkForwardResult with analysis details
        """
        import time
        start_time = time.time()
        
        bars_per_day = self._bars_per_day(timeframe)
        train_bars = train_days * bars_per_day
        test_bars = test_days * bars_per_day
        step_bars = step_days * bars_per_day
        
        total_bars = len(df)
        min_required = train_bars + test_bars
        
        if total_bars < min_required:
            raise ValueError(
                f"Insufficient data: need {min_required} bars "
                f"({(train_days + test_days)} days), have {total_bars} bars"
            )
        
        # Calculate number of windows
        n_windows = (total_bars - min_required) // step_bars + 1
        
        if verbose:
            print(f"\n🔄 Starting Walk-Forward Analysis")
            print(f"   Train Window: {train_days} days ({train_bars} bars)")
            print(f"   Test Window:  {test_days} days ({test_bars} bars)")
            print(f"   Step Size:    {step_days} days ({step_bars} bars)")
            print(f"   Windows:      {n_windows}")
            print(f"   Data Range:   {df.index[0].date()} to {df.index[-1].date()}")
        
        windows = []
        
        for i in range(n_windows):
            # Define window boundaries
            train_start_idx = i * step_bars
            train_end_idx = train_start_idx + train_bars
            test_start_idx = train_end_idx
            test_end_idx = test_start_idx + test_bars
            
            # Check bounds
            if test_end_idx > total_bars:
                break
            
            # Split data
            train_df = df.iloc[train_start_idx:train_end_idx].copy()
            test_df = df.iloc[test_start_idx:test_end_idx].copy()
            
            if verbose:
                print(f"\n   Window {i+1}/{n_windows}:")
                print(f"   Train: {train_df.index[0].date()} to {train_df.index[-1].date()}")
                print(f"   Test:  {test_df.index[0].date()} to {test_df.index[-1].date()}")
            
            # Optimize on training data
            opt_result = self.optimizer.grid_search(
                train_df, 
                self.param_ranges, 
                verbose=False
            )
            
            best_params = opt_result.best_params
            train_sharpe = opt_result.best_sharpe
            train_return = opt_result.best_return
            
            if verbose:
                print(f"   Best params: {best_params}")
                print(f"   Train Sharpe: {train_sharpe:.2f}")
            
            # Test on out-of-sample data
            test_df = self.optimizer._add_indicators(test_df)
            entries, exits = self.optimizer._generate_signals_parametric(test_df, **best_params)
            
            try:
                pf = vbt.Portfolio.from_signals(
                    close=test_df['close'],
                    entries=entries,
                    exits=exits,
                    init_cash=self.initial_capital,
                    fees=self.fee_pct,
                    slippage=self.slippage_pct,
                    freq=timeframe
                )
                
                stats = pf.stats()
                test_sharpe = stats['Sharpe Ratio'] if not np.isnan(stats['Sharpe Ratio']) else 0
                test_return = pf.total_return()
                test_win_rate = stats['Win Rate [%]'] if not np.isnan(stats['Win Rate [%]']) else 0
                test_trades = int(stats['Total Trades'])
                
            except Exception as e:
                if verbose:
                    print(f"   ⚠️ Test error: {e}")
                test_sharpe = 0
                test_return = 0
                test_win_rate = 0
                test_trades = 0
            
            overfitting_gap = train_sharpe - test_sharpe
            
            if verbose:
                status = "✅" if overfitting_gap < 0.5 else "⚠️"
                print(f"   Test Sharpe: {test_sharpe:.2f} (Gap: {overfitting_gap:+.2f}) {status}")
            
            # Store window result
            window = WalkForwardWindow(
                window_num=i + 1,
                train_start=train_df.index[0],
                train_end=train_df.index[-1],
                test_start=test_df.index[0],
                test_end=test_df.index[-1],
                best_params=best_params,
                train_sharpe=train_sharpe,
                train_return=train_return,
                test_sharpe=test_sharpe,
                test_return=test_return,
                test_win_rate=test_win_rate,
                test_trades=test_trades,
                overfitting_gap=overfitting_gap
            )
            windows.append(window)
        
        # Calculate aggregate metrics
        avg_train_sharpe = np.mean([w.train_sharpe for w in windows])
        avg_test_sharpe = np.mean([w.test_sharpe for w in windows])
        avg_overfitting_gap = np.mean([w.overfitting_gap for w in windows])
        
        # Calculate total test return (compounded)
        total_test_return = 1.0
        for w in windows:
            total_test_return *= (1 + w.test_return)
        total_test_return -= 1
        
        # Assess robustness
        # Score based on:
        # 1. Overfitting gap (lower is better)
        # 2. Test Sharpe consistency
        # 3. Positive test returns
        
        gap_score = max(0, 100 - avg_overfitting_gap * 50)  # 0 gap = 100, 2 gap = 0
        sharpe_score = min(100, avg_test_sharpe * 50)  # 2 Sharpe = 100
        return_score = 50 + (total_test_return * 100)  # 0% = 50, +50% = 100
        
        robustness_score = (gap_score + sharpe_score + return_score) / 3
        is_robust = avg_overfitting_gap < 0.5 and avg_test_sharpe > 0
        
        elapsed = time.time() - start_time
        
        result = WalkForwardResult(
            windows=windows,
            avg_train_sharpe=avg_train_sharpe,
            avg_test_sharpe=avg_test_sharpe,
            avg_overfitting_gap=avg_overfitting_gap,
            total_test_return=total_test_return,
            is_robust=is_robust,
            robustness_score=robustness_score,
            analysis_time=elapsed
        )
        
        if verbose:
            print(result)
        
        return result
    
    def anchored_analysis(self,
                          df: pd.DataFrame,
                          anchor_days: int = 180,
                          test_days: int = 30,
                          timeframe: str = '15m',
                          verbose: bool = True) -> WalkForwardResult:
        """
        Anchored walk-forward: training window starts from beginning
        
        Unlike rolling window, training always starts from day 1.
        Training grows larger each iteration while test window stays fixed.
        
        Good for: strategies that benefit from more data
        """
        import time
        start_time = time.time()
        
        bars_per_day = self._bars_per_day(timeframe)
        anchor_bars = anchor_days * bars_per_day
        test_bars = test_days * bars_per_day
        
        total_bars = len(df)
        n_windows = (total_bars - anchor_bars) // test_bars
        
        if verbose:
            print(f"\n🔄 Starting Anchored Walk-Forward Analysis")
            print(f"   Initial Train: {anchor_days} days")
            print(f"   Test Window:   {test_days} days")
            print(f"   Windows:       {n_windows}")
        
        windows = []
        
        for i in range(n_windows):
            # Training always starts at 0
            train_start_idx = 0
            train_end_idx = anchor_bars + (i * test_bars)
            test_start_idx = train_end_idx
            test_end_idx = test_start_idx + test_bars
            
            if test_end_idx > total_bars:
                break
            
            train_df = df.iloc[train_start_idx:train_end_idx].copy()
            test_df = df.iloc[test_start_idx:test_end_idx].copy()
            
            if verbose:
                print(f"\n   Window {i+1}: Train {len(train_df)} bars → Test {len(test_df)} bars")
            
            # Optimize and test (same as rolling)
            opt_result = self.optimizer.grid_search(train_df, self.param_ranges, verbose=False)
            
            test_df = self.optimizer._add_indicators(test_df)
            entries, exits = self.optimizer._generate_signals_parametric(test_df, **opt_result.best_params)
            
            try:
                pf = vbt.Portfolio.from_signals(
                    close=test_df['close'],
                    entries=entries,
                    exits=exits,
                    init_cash=self.initial_capital,
                    fees=self.fee_pct,
                    slippage=self.slippage_pct,
                    freq=timeframe
                )
                
                stats = pf.stats()
                test_sharpe = stats['Sharpe Ratio'] if not np.isnan(stats['Sharpe Ratio']) else 0
                test_return = pf.total_return()
                test_win_rate = stats['Win Rate [%]'] if not np.isnan(stats['Win Rate [%]']) else 0
                test_trades = int(stats['Total Trades'])
            except:
                test_sharpe = test_return = test_win_rate = 0
                test_trades = 0
            
            window = WalkForwardWindow(
                window_num=i + 1,
                train_start=train_df.index[0],
                train_end=train_df.index[-1],
                test_start=test_df.index[0],
                test_end=test_df.index[-1],
                best_params=opt_result.best_params,
                train_sharpe=opt_result.best_sharpe,
                train_return=opt_result.best_return,
                test_sharpe=test_sharpe,
                test_return=test_return,
                test_win_rate=test_win_rate,
                test_trades=test_trades,
                overfitting_gap=opt_result.best_sharpe - test_sharpe
            )
            windows.append(window)
        
        # Calculate metrics
        avg_train_sharpe = np.mean([w.train_sharpe for w in windows])
        avg_test_sharpe = np.mean([w.test_sharpe for w in windows])
        avg_overfitting_gap = np.mean([w.overfitting_gap for w in windows])
        
        total_test_return = 1.0
        for w in windows:
            total_test_return *= (1 + w.test_return)
        total_test_return -= 1
        
        robustness_score = max(0, 100 - avg_overfitting_gap * 50)
        is_robust = avg_overfitting_gap < 0.5 and avg_test_sharpe > 0
        
        elapsed = time.time() - start_time
        
        result = WalkForwardResult(
            windows=windows,
            avg_train_sharpe=avg_train_sharpe,
            avg_test_sharpe=avg_test_sharpe,
            avg_overfitting_gap=avg_overfitting_gap,
            total_test_return=total_test_return,
            is_robust=is_robust,
            robustness_score=robustness_score,
            analysis_time=elapsed
        )
        
        if verbose:
            print(result)
        
        return result


def validate_strategy(df: pd.DataFrame, 
                      verbose: bool = True) -> WalkForwardResult:
    """
    Quick strategy validation using walk-forward analysis
    
    Usage:
        from trading_bot.vectorbt import validate_strategy
        result = validate_strategy(df)
        
        if result.is_robust:
            print("Strategy validated!")
    """
    analyzer = WalkForwardAnalyzer()
    return analyzer.analyze(df, verbose=verbose)
