"""
VectorBT Strategy Adapter
=========================

Converts loop-based Order Block strategies to vectorized VectorBT format.
Achieves 100x speedup through numpy/pandas vectorization.

Usage:
    from trading_bot.vectorbt import VectorBTOrderBlock
    
    strategy = VectorBTOrderBlock()
    portfolio = strategy.backtest(df, initial_capital=10000)
    print(f"Return: {portfolio.total_return():.2%}")
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional, List
from dataclasses import dataclass
import warnings

# Suppress VectorBT warnings
warnings.filterwarnings('ignore', category=FutureWarning)

try:
    import vectorbt as vbt
except ImportError:
    raise ImportError("VectorBT not installed. Run: pip install vectorbt")


@dataclass
class VectorBTConfig:
    """Configuration for VectorBT strategy"""
    # Structure detection
    input_range: int = 25
    
    # Entry conditions
    min_risk_reward: float = 1.5
    max_age_bars: int = 150
    
    # Trend filter (V2)
    use_trend_filter: bool = True
    ema_fast: int = 50
    ema_slow: int = 200
    
    # FVG filter
    require_fvg: bool = True
    min_fvg_percent: float = 0.1
    
    # Displacement filter
    require_displacement: bool = True
    min_displacement_percent: float = 0.5
    
    # Risk management
    sl_atr_mult: float = 1.5
    tp_rr_mult: float = 2.5
    position_size: float = 0.02  # 2% per trade
    
    # Fees
    fee_pct: float = 0.001  # 0.1%
    slippage_pct: float = 0.0005  # 0.05%


class VectorBTStrategyAdapter:
    """
    Base adapter for converting strategies to VectorBT format
    
    Subclasses implement _generate_signals() method
    """
    
    def __init__(self, config: Optional[VectorBTConfig] = None):
        self.config = config or VectorBTConfig()
        self._indicators_calculated = False
    
    def _add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add all technical indicators (vectorized)"""
        df = df.copy()
        
        # ATR (Average True Range)
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift(1)).abs()
        low_close = (df['low'] - df['close'].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(14).mean()
        df['atr_pct'] = (df['atr'] / df['close']) * 100
        
        # EMAs for trend
        df['ema_fast'] = df['close'].ewm(span=self.config.ema_fast, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=self.config.ema_slow, adjust=False).mean()
        
        # Trend direction
        df['uptrend'] = df['ema_fast'] > df['ema_slow']
        df['downtrend'] = df['ema_fast'] < df['ema_slow']
        
        # Candle types
        df['bullish_candle'] = df['close'] > df['open']
        df['bearish_candle'] = df['close'] < df['open']
        
        # Swing highs/lows (structure)
        df['swing_high'] = df['high'].rolling(self.config.input_range).max()
        df['swing_low'] = df['low'].rolling(self.config.input_range).min()
        
        # Structure breaks
        df['bos_bearish'] = (df['close'] < df['swing_low'].shift(1)) & (df['close'].shift(1) >= df['swing_low'].shift(1))
        df['bos_bullish'] = (df['close'] > df['swing_high'].shift(1)) & (df['close'].shift(1) <= df['swing_high'].shift(1))
        
        # FVG detection (vectorized approximation)
        # Bullish FVG: gap between candle N-2 high and candle N low
        df['bullish_fvg'] = df['low'] > df['high'].shift(2)
        df['bullish_fvg_size'] = (df['low'] - df['high'].shift(2)) / df['close'] * 100
        
        # Bearish FVG: gap between candle N-2 low and candle N high
        df['bearish_fvg'] = df['high'] < df['low'].shift(2)
        df['bearish_fvg_size'] = (df['low'].shift(2) - df['high']) / df['close'] * 100
        
        # Volume spike (for displacement)
        df['volume_ma'] = df['volume'].rolling(20).mean()
        df['volume_spike'] = df['volume'] > df['volume_ma'] * 1.5
        
        # Price displacement (big move)
        df['price_change'] = df['close'].pct_change(2).abs() * 100
        df['displacement'] = df['price_change'] > self.config.min_displacement_percent
        
        self._indicators_calculated = True
        return df
    
    def _generate_signals(self, df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """
        Generate entry/exit signals (to be overridden by subclasses)
        
        Returns:
            entries: Boolean series (True = enter position)
            exits: Boolean series (True = exit position)
        """
        raise NotImplementedError("Subclasses must implement _generate_signals()")
    
    def backtest(self, df: pd.DataFrame, initial_capital: float = 10000, 
                 verbose: bool = True) -> 'vbt.Portfolio':
        """
        Run vectorized backtest
        
        Args:
            df: OHLCV DataFrame with datetime index
            initial_capital: Starting capital
            verbose: Print results
        
        Returns:
            VectorBT Portfolio object
        """
        # Add indicators
        df = self._add_indicators(df)
        
        # Generate signals
        entries, exits = self._generate_signals(df)
        
        # Create portfolio
        pf = vbt.Portfolio.from_signals(
            close=df['close'],
            entries=entries,
            exits=exits,
            init_cash=initial_capital,
            fees=self.config.fee_pct,
            slippage=self.config.slippage_pct,
            freq='15min'
        )
        
        if verbose:
            self._print_results(pf, df)
        
        return pf
    
    def _print_results(self, pf: 'vbt.Portfolio', df: pd.DataFrame):
        """Print backtest results"""
        stats = pf.stats()
        
        print(f"\n{'='*60}")
        print(f"📊 VECTORBT BACKTEST RESULTS")
        print(f"{'='*60}")
        print(f"Period:          {df.index[0].date()} to {df.index[-1].date()}")
        print(f"Total Bars:      {len(df):,}")
        print(f"{'─'*60}")
        print(f"Initial Capital: ${float(pf.init_cash):,.2f}")
        print(f"Final Value:     ${float(pf.final_value()):,.2f}")
        print(f"Total Return:    {float(pf.total_return()):.2%}")
        print(f"{'─'*60}")
        print(f"Total Trades:    {stats['Total Trades']:.0f}")
        win_rate = stats['Win Rate [%]']
        print(f"Win Rate:        {win_rate:.1f}%" if not pd.isna(win_rate) else "Win Rate:        N/A")
        pf_val = stats['Profit Factor']
        print(f"Profit Factor:   {pf_val:.2f}" if not pd.isna(pf_val) else "Profit Factor:   N/A")
        print(f"{'─'*60}")
        max_dd = stats['Max Drawdown [%]']
        print(f"Max Drawdown:    {max_dd:.2f}%" if not pd.isna(max_dd) else "Max Drawdown:    N/A")
        sharpe = stats['Sharpe Ratio']
        print(f"Sharpe Ratio:    {sharpe:.2f}" if not pd.isna(sharpe) else "Sharpe Ratio:    N/A")
        sortino = stats['Sortino Ratio']
        print(f"Sortino Ratio:   {sortino:.2f}" if not pd.isna(sortino) else "Sortino Ratio:   N/A")
        print(f"{'='*60}\n")


class VectorBTOrderBlock(VectorBTStrategyAdapter):
    """
    Vectorized Order Block Strategy (Premium V2 equivalent)
    
    Logic:
    1. Detect structure breaks (swing high/low violations)
    2. Identify order blocks at structure break locations
    3. Wait for price to retest the OB zone
    4. Enter with trend filter confirmation
    5. Exit at TP or SL
    
    Note: This is an approximation of the loop-based strategy.
    Some nuances (like exact OB placement) are simplified for speed.
    """
    
    def __init__(self, config: Optional[VectorBTConfig] = None):
        super().__init__(config)
        self.name = "VectorBT_OrderBlock_V2"
    
    def _generate_signals(self, df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """
        Generate Order Block entry/exit signals (vectorized)
        
        Entry Logic (LONG):
        - Bearish BOS occurred recently (created potential bullish OB)
        - Price retests the OB zone (price touches swing low area)
        - Current bar is bullish
        - Uptrend confirmed (EMA50 > EMA200) if filter enabled
        - FVG present if required
        - Displacement present if required
        
        Exit Logic:
        - TP hit (price moves up by SL * RR multiplier)
        - SL hit (price moves down by ATR * SL multiplier)
        """
        cfg = self.config
        
        # Track potential OB locations (bars after BOS)
        # Bullish OB forms after bearish BOS
        bullish_ob_zone = df['bos_bearish'].rolling(cfg.max_age_bars, min_periods=1).max().astype(bool)
        
        # Bearish OB forms after bullish BOS  
        bearish_ob_zone = df['bos_bullish'].rolling(cfg.max_age_bars, min_periods=1).max().astype(bool)
        
        # Retest detection: price touches swing low/high zone
        # For LONG: price touches swing low but doesn't break it
        retest_long = (df['low'] <= df['swing_low'] * 1.005) & (df['close'] > df['swing_low'])
        
        # For SHORT: price touches swing high but doesn't break it
        retest_short = (df['high'] >= df['swing_high'] * 0.995) & (df['close'] < df['swing_high'])
        
        # Base entry conditions
        long_base = (
            bullish_ob_zone &  # OB zone active
            retest_long &  # Price retesting OB
            df['bullish_candle']  # Confirmation candle
        )
        
        short_base = (
            bearish_ob_zone &  # OB zone active
            retest_short &  # Price retesting OB
            df['bearish_candle']  # Confirmation candle
        )
        
        # Apply trend filter (V2 feature)
        if cfg.use_trend_filter:
            long_entries = long_base & df['uptrend']
            short_entries = short_base & df['downtrend']
        else:
            long_entries = long_base
            short_entries = short_base
        
        # Apply FVG filter
        if cfg.require_fvg:
            # Check if FVG occurred recently (within 10 bars)
            recent_bullish_fvg = df['bullish_fvg'].rolling(10, min_periods=1).max().astype(bool)
            recent_bearish_fvg = df['bearish_fvg'].rolling(10, min_periods=1).max().astype(bool)
            
            long_entries = long_entries & recent_bullish_fvg
            short_entries = short_entries & recent_bearish_fvg
        
        # Apply displacement filter
        if cfg.require_displacement:
            recent_displacement = df['displacement'].rolling(5, min_periods=1).max().astype(bool)
            long_entries = long_entries & recent_displacement
            short_entries = short_entries & recent_displacement
        
        # Combine entries (long only for simplicity, can extend to short)
        # VectorBT's from_signals by default handles long-only
        entries = long_entries
        
        # Exit signals based on ATR
        # Exit when price moves against by SL amount
        atr_sl = df['atr'] * cfg.sl_atr_mult
        sl_price = df['close'] - atr_sl  # For longs
        
        # Exit if price drops below SL
        exits = df['low'] < sl_price.shift(1)
        
        # Also exit at TP (price rises by RR * SL)
        tp_price = df['close'] + atr_sl * cfg.tp_rr_mult
        exits = exits | (df['high'] > tp_price.shift(1))
        
        return entries.fillna(False), exits.fillna(False)
    
    def backtest_with_sl_tp(self, df: pd.DataFrame, initial_capital: float = 10000,
                            verbose: bool = True) -> 'vbt.Portfolio':
        """
        Run backtest with proper SL/TP using VectorBT's advanced features
        
        Uses vbt.Portfolio.from_signals with sl_stop and tp_stop parameters
        """
        # Add indicators
        df = self._add_indicators(df)
        
        # Generate entry signals only
        entries, _ = self._generate_signals(df)
        
        # Calculate SL/TP percentages
        sl_pct = df['atr'] / df['close'] * self.config.sl_atr_mult
        tp_pct = sl_pct * self.config.tp_rr_mult
        
        # Create portfolio with SL/TP
        pf = vbt.Portfolio.from_signals(
            close=df['close'],
            entries=entries,
            sl_stop=sl_pct,  # Stop loss as % of entry
            tp_stop=tp_pct,  # Take profit as % of entry
            init_cash=initial_capital,
            fees=self.config.fee_pct,
            slippage=self.config.slippage_pct,
            freq='15min'
        )
        
        if verbose:
            self._print_results(pf, df)
        
        return pf
    
    def get_trades_df(self, pf: 'vbt.Portfolio') -> pd.DataFrame:
        """Extract trades DataFrame from portfolio"""
        return pf.trades.records_readable


class VectorBTOrderBlockShort(VectorBTOrderBlock):
    """
    Vectorized Order Block Strategy - SHORT only version
    """
    
    def __init__(self, config: Optional[VectorBTConfig] = None):
        super().__init__(config)
        self.name = "VectorBT_OrderBlock_V2_Short"
    
    def _generate_signals(self, df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """Generate SHORT entry/exit signals"""
        cfg = self.config
        
        # Bearish OB forms after bullish BOS
        bearish_ob_zone = df['bos_bullish'].rolling(cfg.max_age_bars, min_periods=1).max().astype(bool)
        
        # Retest detection
        retest_short = (df['high'] >= df['swing_high'] * 0.995) & (df['close'] < df['swing_high'])
        
        # Base entry
        short_base = (
            bearish_ob_zone &
            retest_short &
            df['bearish_candle']
        )
        
        # Apply trend filter
        if cfg.use_trend_filter:
            short_entries = short_base & df['downtrend']
        else:
            short_entries = short_base
        
        # Apply FVG filter
        if cfg.require_fvg:
            recent_bearish_fvg = df['bearish_fvg'].rolling(10, min_periods=1).max().astype(bool)
            short_entries = short_entries & recent_bearish_fvg
        
        # Apply displacement filter
        if cfg.require_displacement:
            recent_displacement = df['displacement'].rolling(5, min_periods=1).max().astype(bool)
            short_entries = short_entries & recent_displacement
        
        # Exits
        atr_sl = df['atr'] * cfg.sl_atr_mult
        sl_price = df['close'] + atr_sl  # For shorts
        exits = df['high'] > sl_price.shift(1)
        
        # TP exit
        tp_price = df['close'] - atr_sl * cfg.tp_rr_mult
        exits = exits | (df['low'] < tp_price.shift(1))
        
        return short_entries.fillna(False), exits.fillna(False)


class VectorBTOrderBlockBidirectional(VectorBTStrategyAdapter):
    """
    Vectorized Order Block Strategy - Both LONG and SHORT
    
    Uses VectorBT's direction parameter to handle both directions
    """
    
    def __init__(self, config: Optional[VectorBTConfig] = None):
        super().__init__(config)
        self.name = "VectorBT_OrderBlock_V2_Bidirectional"
    
    def _generate_signals(self, df: pd.DataFrame) -> Tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
        """
        Generate both LONG and SHORT signals
        
        Returns:
            long_entries, long_exits, short_entries, short_exits
        """
        cfg = self.config
        
        # OB zones
        bullish_ob_zone = df['bos_bearish'].rolling(cfg.max_age_bars, min_periods=1).max().astype(bool)
        bearish_ob_zone = df['bos_bullish'].rolling(cfg.max_age_bars, min_periods=1).max().astype(bool)
        
        # Retests
        retest_long = (df['low'] <= df['swing_low'] * 1.005) & (df['close'] > df['swing_low'])
        retest_short = (df['high'] >= df['swing_high'] * 0.995) & (df['close'] < df['swing_high'])
        
        # Base entries
        long_base = bullish_ob_zone & retest_long & df['bullish_candle']
        short_base = bearish_ob_zone & retest_short & df['bearish_candle']
        
        # Apply filters
        if cfg.use_trend_filter:
            long_entries = long_base & df['uptrend']
            short_entries = short_base & df['downtrend']
        else:
            long_entries = long_base
            short_entries = short_base
        
        if cfg.require_fvg:
            recent_bullish_fvg = df['bullish_fvg'].rolling(10, min_periods=1).max().astype(bool)
            recent_bearish_fvg = df['bearish_fvg'].rolling(10, min_periods=1).max().astype(bool)
            long_entries = long_entries & recent_bullish_fvg
            short_entries = short_entries & recent_bearish_fvg
        
        if cfg.require_displacement:
            recent_displacement = df['displacement'].rolling(5, min_periods=1).max().astype(bool)
            long_entries = long_entries & recent_displacement
            short_entries = short_entries & recent_displacement
        
        # Exits
        atr_sl = df['atr'] * cfg.sl_atr_mult
        
        # Long exits
        long_sl = df['close'] - atr_sl
        long_tp = df['close'] + atr_sl * cfg.tp_rr_mult
        long_exits = (df['low'] < long_sl.shift(1)) | (df['high'] > long_tp.shift(1))
        
        # Short exits
        short_sl = df['close'] + atr_sl
        short_tp = df['close'] - atr_sl * cfg.tp_rr_mult
        short_exits = (df['high'] > short_sl.shift(1)) | (df['low'] < short_tp.shift(1))
        
        return (
            long_entries.fillna(False),
            long_exits.fillna(False),
            short_entries.fillna(False),
            short_exits.fillna(False)
        )
    
    def backtest(self, df: pd.DataFrame, initial_capital: float = 10000,
                 verbose: bool = True) -> 'vbt.Portfolio':
        """Run bidirectional backtest"""
        df = self._add_indicators(df)
        long_entries, long_exits, short_entries, short_exits = self._generate_signals(df)
        
        # Create separate portfolios for long and short
        pf_long = vbt.Portfolio.from_signals(
            close=df['close'],
            entries=long_entries,
            exits=long_exits,
            init_cash=initial_capital / 2,  # Split capital
            fees=self.config.fee_pct,
            slippage=self.config.slippage_pct,
            freq='15min'
        )
        
        pf_short = vbt.Portfolio.from_signals(
            close=df['close'],
            entries=short_entries,
            exits=short_exits,
            short_entries=short_entries,  # Mark as short
            init_cash=initial_capital / 2,
            fees=self.config.fee_pct,
            slippage=self.config.slippage_pct,
            freq='15min',
            direction='shortonly'
        )
        
        if verbose:
            print(f"\n{'='*60}")
            print(f"📊 VECTORBT BIDIRECTIONAL RESULTS")
            print(f"{'='*60}")
            print(f"\n🟢 LONG POSITIONS:")
            self._print_results(pf_long, df)
            print(f"\n🔴 SHORT POSITIONS:")
            self._print_results(pf_short, df)
            
            # Combined stats
            combined_return = (pf_long.final_value + pf_short.final_value) / initial_capital - 1
            print(f"\n📊 COMBINED:")
            print(f"Combined Return: {combined_return:.2%}")
            print(f"{'='*60}\n")
        
        return pf_long  # Return long portfolio (can modify to return both)


# Convenience function
def quick_backtest(df: pd.DataFrame, 
                   initial_capital: float = 10000,
                   use_trend_filter: bool = True,
                   require_fvg: bool = True,
                   verbose: bool = True) -> 'vbt.Portfolio':
    """
    Quick backtest with sensible defaults
    
    Usage:
        from trading_bot.vectorbt import quick_backtest
        pf = quick_backtest(df)
    """
    config = VectorBTConfig(
        use_trend_filter=use_trend_filter,
        require_fvg=require_fvg
    )
    strategy = VectorBTOrderBlock(config)
    return strategy.backtest(df, initial_capital, verbose)
