"""
VectorBT Parameter Optimizer
============================

Enables rapid parameter optimization using VectorBT's vectorized approach.
Test 1000+ parameter combinations in seconds instead of hours.

Features:
- Grid search optimization
- Random search optimization
- Best parameter discovery
- Heatmap visualization
- Optimization report generation
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import warnings

warnings.filterwarnings('ignore', category=FutureWarning)

try:
    import vectorbt as vbt
except ImportError:
    raise ImportError("VectorBT not installed. Run: pip install vectorbt")


@dataclass
class OptimizationResult:
    """Results from parameter optimization"""
    best_params: Dict[str, Any]
    best_sharpe: float
    best_return: float
    best_win_rate: float
    all_results: pd.DataFrame
    optimization_time: float
    total_combinations: int
    
    def to_dict(self) -> Dict:
        return {
            'best_params': self.best_params,
            'best_sharpe': self.best_sharpe,
            'best_return': self.best_return,
            'best_win_rate': self.best_win_rate,
            'optimization_time': self.optimization_time,
            'total_combinations': self.total_combinations
        }
    
    def __str__(self) -> str:
        lines = [
            f"\n{'='*60}",
            f"📊 OPTIMIZATION RESULTS",
            f"{'='*60}",
            f"Total Combinations Tested: {self.total_combinations:,}",
            f"Optimization Time: {self.optimization_time:.2f} seconds",
            f"{'─'*60}",
            f"BEST PARAMETERS:",
        ]
        for k, v in self.best_params.items():
            lines.append(f"  {k}: {v}")
        lines.extend([
            f"{'─'*60}",
            f"BEST METRICS:",
            f"  Sharpe Ratio: {self.best_sharpe:.2f}",
            f"  Total Return: {self.best_return:.2%}",
            f"  Win Rate:     {self.best_win_rate:.1f}%",
            f"{'='*60}\n"
        ])
        return '\n'.join(lines)


class ParameterOptimizer:
    """
    Optimize strategy parameters using VectorBT
    
    Example:
        optimizer = ParameterOptimizer()
        
        param_ranges = {
            'input_range': [15, 20, 25, 30],
            'ema_fast': [20, 50, 100],
            'ema_slow': [100, 200, 300]
        }
        
        result = optimizer.grid_search(df, param_ranges)
        print(result)
    """
    
    def __init__(self, 
                 initial_capital: float = 10000,
                 fee_pct: float = 0.001,
                 slippage_pct: float = 0.0005):
        self.initial_capital = initial_capital
        self.fee_pct = fee_pct
        self.slippage_pct = slippage_pct
    
    def _add_indicators(self, df: pd.DataFrame, ema_fast: int = 50, 
                        ema_slow: int = 200, input_range: int = 25) -> pd.DataFrame:
        """Add indicators with configurable parameters"""
        df = df.copy()
        
        # ATR
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift(1)).abs()
        low_close = (df['low'] - df['close'].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(14).mean()
        
        return df
    
    def _generate_signals_parametric(self, df: pd.DataFrame,
                                     input_range: int = 25,
                                     ema_fast: int = 50,
                                     ema_slow: int = 200,
                                     max_age_bars: int = 150,
                                     require_trend: bool = True,
                                     sl_atr_mult: float = 1.5,
                                     tp_rr_mult: float = 2.5) -> Tuple[pd.Series, pd.Series]:
        """Generate signals with configurable parameters"""
                # Convert numpy types to Python types for pandas
        input_range = int(input_range)
        ema_fast = int(ema_fast)
        ema_slow = int(ema_slow)
        max_age_bars = int(max_age_bars)
                # EMAs
        ema_f = df['close'].ewm(span=ema_fast, adjust=False).mean()
        ema_s = df['close'].ewm(span=ema_slow, adjust=False).mean()
        uptrend = ema_f > ema_s
        
        # Structure
        swing_low = df['low'].rolling(input_range).min()
        
        # BOS
        bos_bearish = (df['close'] < swing_low.shift(1)) & (df['close'].shift(1) >= swing_low.shift(1))
        
        # OB zone
        bullish_ob_zone = bos_bearish.rolling(max_age_bars, min_periods=1).max().astype(bool)
        
        # Retest
        retest = (df['low'] <= swing_low * 1.005) & (df['close'] > swing_low)
        
        # Entries
        entries = bullish_ob_zone & retest & (df['close'] > df['open'])
        if require_trend:
            entries = entries & uptrend
        
        # Exits
        atr_sl = df['atr'] * sl_atr_mult
        sl_price = df['close'] - atr_sl
        tp_price = df['close'] + atr_sl * tp_rr_mult
        exits = (df['low'] < sl_price.shift(1)) | (df['high'] > tp_price.shift(1))
        
        return entries.fillna(False), exits.fillna(False)
    
    def grid_search(self, df: pd.DataFrame, 
                    param_ranges: Dict[str, List],
                    metric: str = 'sharpe',
                    verbose: bool = True) -> OptimizationResult:
        """
        Grid search over all parameter combinations
        
        Args:
            df: OHLCV DataFrame
            param_ranges: Dict of parameter name -> list of values
            metric: Optimization target ('sharpe', 'return', 'win_rate')
            verbose: Print progress
        
        Returns:
            OptimizationResult with best parameters
        """
        import time
        from itertools import product
        
        start_time = time.time()
        
        # Add base indicators
        df = self._add_indicators(df)
        
        # Generate all combinations
        param_names = list(param_ranges.keys())
        param_values = list(param_ranges.values())
        combinations = list(product(*param_values))
        
        if verbose:
            print(f"\n🔍 Starting Grid Search Optimization")
            print(f"   Parameters: {param_names}")
            print(f"   Combinations: {len(combinations):,}")
        
        results = []
        
        for i, combo in enumerate(combinations):
            params = dict(zip(param_names, combo))
            
            # Generate signals with these params
            entries, exits = self._generate_signals_parametric(df, **params)
            
            # Quick backtest
            try:
                pf = vbt.Portfolio.from_signals(
                    close=df['close'],
                    entries=entries,
                    exits=exits,
                    init_cash=self.initial_capital,
                    fees=self.fee_pct,
                    slippage=self.slippage_pct,
                    freq='15min'
                )
                
                stats = pf.stats()
                result = {
                    **params,
                    'sharpe': stats['Sharpe Ratio'] if not np.isnan(stats['Sharpe Ratio']) else -999,
                    'return': pf.total_return(),
                    'win_rate': stats['Win Rate [%]'] if not np.isnan(stats['Win Rate [%]']) else 0,
                    'total_trades': stats['Total Trades'],
                    'max_dd': stats['Max Drawdown [%]']
                }
                results.append(result)
                
            except Exception as e:
                results.append({
                    **params,
                    'sharpe': -999,
                    'return': -1,
                    'win_rate': 0,
                    'total_trades': 0,
                    'max_dd': 100
                })
            
            if verbose and (i + 1) % max(1, len(combinations) // 10) == 0:
                print(f"   Progress: {i+1}/{len(combinations)} ({(i+1)/len(combinations)*100:.0f}%)")
        
        # Create results DataFrame
        results_df = pd.DataFrame(results)
        
        # Find best based on metric
        if metric == 'sharpe':
            best_idx = results_df['sharpe'].idxmax()
        elif metric == 'return':
            best_idx = results_df['return'].idxmax()
        elif metric == 'win_rate':
            best_idx = results_df['win_rate'].idxmax()
        else:
            best_idx = results_df['sharpe'].idxmax()
        
        best_row = results_df.iloc[best_idx]
        best_params = {k: best_row[k] for k in param_names}
        
        elapsed = time.time() - start_time
        
        result = OptimizationResult(
            best_params=best_params,
            best_sharpe=best_row['sharpe'],
            best_return=best_row['return'],
            best_win_rate=best_row['win_rate'],
            all_results=results_df,
            optimization_time=elapsed,
            total_combinations=len(combinations)
        )
        
        if verbose:
            print(result)
        
        return result
    
    def random_search(self, df: pd.DataFrame,
                      param_distributions: Dict[str, Tuple[float, float]],
                      n_iterations: int = 100,
                      metric: str = 'sharpe',
                      verbose: bool = True) -> OptimizationResult:
        """
        Random search over parameter distributions
        
        Args:
            df: OHLCV DataFrame
            param_distributions: Dict of parameter name -> (min, max) tuple
            n_iterations: Number of random samples
            metric: Optimization target
            verbose: Print progress
        
        Returns:
            OptimizationResult with best parameters
        """
        import time
        
        start_time = time.time()
        
        # Add base indicators
        df = self._add_indicators(df)
        
        if verbose:
            print(f"\n🎲 Starting Random Search Optimization")
            print(f"   Parameters: {list(param_distributions.keys())}")
            print(f"   Iterations: {n_iterations}")
        
        results = []
        param_names = list(param_distributions.keys())
        
        for i in range(n_iterations):
            # Generate random params
            params = {}
            for name, (min_val, max_val) in param_distributions.items():
                if isinstance(min_val, int) and isinstance(max_val, int):
                    params[name] = np.random.randint(min_val, max_val + 1)
                else:
                    params[name] = np.random.uniform(min_val, max_val)
            
            # Generate signals
            entries, exits = self._generate_signals_parametric(df, **params)
            
            try:
                pf = vbt.Portfolio.from_signals(
                    close=df['close'],
                    entries=entries,
                    exits=exits,
                    init_cash=self.initial_capital,
                    fees=self.fee_pct,
                    slippage=self.slippage_pct,
                    freq='15min'
                )
                
                stats = pf.stats()
                result = {
                    **params,
                    'sharpe': stats['Sharpe Ratio'] if not np.isnan(stats['Sharpe Ratio']) else -999,
                    'return': pf.total_return(),
                    'win_rate': stats['Win Rate [%]'] if not np.isnan(stats['Win Rate [%]']) else 0,
                    'total_trades': stats['Total Trades'],
                    'max_dd': stats['Max Drawdown [%]']
                }
                results.append(result)
                
            except Exception:
                pass
            
            if verbose and (i + 1) % max(1, n_iterations // 10) == 0:
                print(f"   Progress: {i+1}/{n_iterations} ({(i+1)/n_iterations*100:.0f}%)")
        
        results_df = pd.DataFrame(results)
        
        # Find best
        if metric == 'sharpe':
            best_idx = results_df['sharpe'].idxmax()
        elif metric == 'return':
            best_idx = results_df['return'].idxmax()
        else:
            best_idx = results_df['sharpe'].idxmax()
        
        best_row = results_df.iloc[best_idx]
        best_params = {k: best_row[k] for k in param_names}
        
        elapsed = time.time() - start_time
        
        result = OptimizationResult(
            best_params=best_params,
            best_sharpe=best_row['sharpe'],
            best_return=best_row['return'],
            best_win_rate=best_row['win_rate'],
            all_results=results_df,
            optimization_time=elapsed,
            total_combinations=n_iterations
        )
        
        if verbose:
            print(result)
        
        return result
    
    def generate_heatmap(self, results_df: pd.DataFrame,
                         param_x: str, param_y: str,
                         metric: str = 'sharpe',
                         save_path: Optional[str] = None) -> None:
        """
        Generate 2D heatmap of optimization results
        
        Args:
            results_df: DataFrame from OptimizationResult
            param_x: X-axis parameter
            param_y: Y-axis parameter
            metric: Metric to visualize
            save_path: Path to save image
        """
        try:
            import plotly.express as px
            
            # Pivot for heatmap
            pivot = results_df.pivot_table(
                values=metric,
                index=param_y,
                columns=param_x,
                aggfunc='mean'
            )
            
            fig = px.imshow(
                pivot,
                labels={'x': param_x, 'y': param_y, 'color': metric},
                title=f'Parameter Optimization Heatmap ({metric})',
                color_continuous_scale='RdYlGn'
            )
            
            if save_path:
                fig.write_image(save_path)
                print(f"✓ Heatmap saved to {save_path}")
            else:
                fig.show()
                
        except ImportError:
            print("Plotly not available for heatmap visualization")


def optimize_strategy(df: pd.DataFrame, 
                      quick: bool = True,
                      verbose: bool = True) -> OptimizationResult:
    """
    Quick optimization with sensible parameter ranges
    
    Usage:
        from trading_bot.vectorbt import optimize_strategy
        result = optimize_strategy(df)
        print(f"Best params: {result.best_params}")
    """
    optimizer = ParameterOptimizer()
    
    if quick:
        # Quick search with fewer combinations
        param_ranges = {
            'input_range': [20, 25, 30],
            'ema_fast': [50],
            'ema_slow': [200],
            'max_age_bars': [100, 150, 200],
            'tp_rr_mult': [2.0, 2.5, 3.0]
        }
    else:
        # Full search
        param_ranges = {
            'input_range': [15, 20, 25, 30, 35],
            'ema_fast': [20, 50, 100],
            'ema_slow': [100, 200, 300],
            'max_age_bars': [100, 150, 200, 250],
            'sl_atr_mult': [1.0, 1.5, 2.0],
            'tp_rr_mult': [1.5, 2.0, 2.5, 3.0]
        }
    
    return optimizer.grid_search(df, param_ranges, verbose=verbose)
