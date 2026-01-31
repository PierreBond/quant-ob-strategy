"""
Multi-Timeframe Analysis
Confirms trading signals across multiple timeframes for higher probability trades

Features:
- Analyze trend on multiple timeframes (5m, 15m, 1h, 4h, 1d)
- Require confluence before taking trades
- Calculate trend alignment score
- Identify divergences between timeframes
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from enum import Enum
import ccxt


class Trend(Enum):
    """Trend classification"""
    STRONG_BULLISH = 2
    BULLISH = 1
    NEUTRAL = 0
    BEARISH = -1
    STRONG_BEARISH = -2


@dataclass
class TimeframeAnalysis:
    """Analysis results for a single timeframe"""
    timeframe: str
    trend: Trend
    ema_fast: float
    ema_slow: float
    ema_diff_pct: float  # % difference between EMAs
    rsi: float
    atr_pct: float
    last_close: float
    last_high: float
    last_low: float


class MultiTimeframeAnalyzer:
    """
    Analyze multiple timeframes for trend confirmation
    
    Trading Rule: Only take trades when multiple timeframes agree
    
    Usage:
        mtf = MultiTimeframeAnalyzer()
        mtf.fetch_all_timeframes('BTC/USDT')
        
        # Check if 15m LONG is confirmed by higher TFs
        confirmed, details = mtf.get_confirmation('15m', 'LONG')
        if confirmed:
            # Take trade
            pass
    """
    
    # Timeframe hierarchy (lower to higher)
    TIMEFRAME_ORDER = ['1m', '5m', '15m', '30m', '1h', '4h', '1d']
    
    # Minutes per timeframe (for data requirements)
    TIMEFRAME_MINUTES = {
        '1m': 1, '5m': 5, '15m': 15, '30m': 30,
        '1h': 60, '4h': 240, '1d': 1440
    }
    
    def __init__(
        self,
        ema_fast_period: int = 50,
        ema_slow_period: int = 200,
        rsi_period: int = 14,
        atr_period: int = 14,
        exchange_id: str = 'binance'
    ):
        self.ema_fast_period = ema_fast_period
        self.ema_slow_period = ema_slow_period
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.exchange_id = exchange_id
        
        # Store data for each timeframe
        self.data: Dict[str, pd.DataFrame] = {}
        self.analysis: Dict[str, TimeframeAnalysis] = {}
        
        # Initialize exchange
        self._init_exchange()
    
    def _init_exchange(self):
        """Initialize exchange connection"""
        try:
            exchange_class = getattr(ccxt, self.exchange_id)
            self.exchange = exchange_class({'enableRateLimit': True})
        except Exception as e:
            print(f"⚠️ Could not initialize exchange: {e}")
            self.exchange = None
    
    def fetch_timeframe_data(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 300
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV data for a specific timeframe
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            timeframe: Timeframe (e.g., '15m', '1h')
            limit: Number of candles to fetch
        
        Returns:
            DataFrame with OHLCV data or None on error
        """
        if self.exchange is None:
            return None
        
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            print(f"⚠️ Error fetching {timeframe} data: {e}")
            return None
    
    def fetch_all_timeframes(
        self,
        symbol: str,
        timeframes: List[str] = None
    ):
        """
        Fetch data for all specified timeframes
        
        Args:
            symbol: Trading pair
            timeframes: List of timeframes to fetch (default: 15m, 1h, 4h, 1d)
        """
        if timeframes is None:
            timeframes = ['15m', '1h', '4h', '1d']
        
        print(f"📊 Fetching multi-timeframe data for {symbol}...")
        
        for tf in timeframes:
            df = self.fetch_timeframe_data(symbol, tf)
            if df is not None and len(df) >= self.ema_slow_period:
                self.add_data(tf, df)
                print(f"   ✅ {tf}: {len(df)} candles")
            else:
                print(f"   ❌ {tf}: Failed or insufficient data")
    
    def add_data(self, timeframe: str, df: pd.DataFrame):
        """
        Add OHLCV data for a timeframe (manual)
        
        Args:
            timeframe: e.g., '15m', '1h', '4h'
            df: DataFrame with columns: open, high, low, close, volume
        """
        if timeframe not in self.TIMEFRAME_ORDER:
            print(f"⚠️ Unknown timeframe: {timeframe}")
            return
        
        # Calculate indicators
        df = df.copy()
        df['ema_fast'] = df['close'].ewm(span=self.ema_fast_period, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=self.ema_slow_period, adjust=False).mean()
        df['rsi'] = self._calculate_rsi(df['close'], self.rsi_period)
        df['atr'] = self._calculate_atr(df, self.atr_period)
        df['atr_pct'] = df['atr'] / df['close'] * 100
        
        self.data[timeframe] = df
        self._analyze_timeframe(timeframe)
    
    def _calculate_rsi(self, prices: pd.Series, period: int) -> pd.Series:
        """Calculate RSI indicator"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def _calculate_atr(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate ATR indicator"""
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()
    
    def _analyze_timeframe(self, timeframe: str):
        """Analyze a single timeframe and store results"""
        df = self.data[timeframe]
        
        if len(df) < self.ema_slow_period:
            return
        
        last = df.iloc[-1]
        
        # Calculate EMA difference percentage
        ema_diff_pct = (last['ema_fast'] - last['ema_slow']) / last['ema_slow'] * 100
        
        # Determine trend based on EMA position and RSI
        if ema_diff_pct > 2 and last['rsi'] > 55:
            trend = Trend.STRONG_BULLISH
        elif ema_diff_pct > 0.5 or (ema_diff_pct > 0 and last['rsi'] > 50):
            trend = Trend.BULLISH
        elif ema_diff_pct < -2 and last['rsi'] < 45:
            trend = Trend.STRONG_BEARISH
        elif ema_diff_pct < -0.5 or (ema_diff_pct < 0 and last['rsi'] < 50):
            trend = Trend.BEARISH
        else:
            trend = Trend.NEUTRAL
        
        self.analysis[timeframe] = TimeframeAnalysis(
            timeframe=timeframe,
            trend=trend,
            ema_fast=last['ema_fast'],
            ema_slow=last['ema_slow'],
            ema_diff_pct=ema_diff_pct,
            rsi=last['rsi'],
            atr_pct=last['atr_pct'],
            last_close=last['close'],
            last_high=last['high'],
            last_low=last['low']
        )
    
    def get_confirmation(
        self,
        entry_timeframe: str,
        direction: str,  # 'LONG' or 'SHORT'
        require_all: bool = False,
        min_higher_tfs: int = 1
    ) -> Tuple[bool, Dict]:
        """
        Check if higher timeframes confirm the trade direction
        
        Args:
            entry_timeframe: The timeframe you want to trade on (e.g., '15m')
            direction: 'LONG' or 'SHORT'
            require_all: If True, ALL higher TFs must confirm
            min_higher_tfs: Minimum number of higher TFs that must confirm
        
        Returns:
            (confirmed: bool, details: dict)
        """
        if entry_timeframe not in self.TIMEFRAME_ORDER:
            return False, {'error': f'Unknown timeframe: {entry_timeframe}'}
        
        entry_idx = self.TIMEFRAME_ORDER.index(entry_timeframe)
        higher_tfs = self.TIMEFRAME_ORDER[entry_idx + 1:]
        
        # Filter to only timeframes we have data for
        higher_tfs = [tf for tf in higher_tfs if tf in self.analysis]
        
        if not higher_tfs:
            # No higher timeframes available - allow trade with warning
            return True, {
                'confirmed': True,
                'message': 'No higher timeframes to check',
                'warning': True
            }
        
        # Check entry timeframe trend
        entry_analysis = self.analysis.get(entry_timeframe)
        entry_aligned = True
        if entry_analysis:
            if direction == 'LONG':
                entry_aligned = entry_analysis.trend.value >= 0
            else:
                entry_aligned = entry_analysis.trend.value <= 0
        
        # Check each higher timeframe
        confirmations = []
        details = {
            'entry_tf': entry_timeframe,
            'direction': direction,
            'entry_aligned': entry_aligned,
            'higher_tfs': {}
        }
        
        for tf in higher_tfs:
            analysis = self.analysis[tf]
            
            if direction == 'LONG':
                # For LONG: need bullish or neutral (not bearish)
                confirmed = analysis.trend.value >= 0
            else:  # SHORT
                # For SHORT: need bearish or neutral (not bullish)
                confirmed = analysis.trend.value <= 0
            
            confirmations.append(confirmed)
            details['higher_tfs'][tf] = {
                'trend': analysis.trend.name,
                'trend_value': analysis.trend.value,
                'confirmed': confirmed,
                'ema_diff_pct': analysis.ema_diff_pct,
                'rsi': analysis.rsi
            }
        
        # Determine overall confirmation
        confirm_count = sum(confirmations)
        
        if require_all:
            overall_confirmed = all(confirmations) and entry_aligned
        else:
            overall_confirmed = confirm_count >= min_higher_tfs and entry_aligned
        
        details['confirmed'] = overall_confirmed
        details['confirmation_count'] = confirm_count
        details['confirmation_rate'] = f"{confirm_count}/{len(confirmations)}"
        details['required'] = 'all' if require_all else f'>={min_higher_tfs}'
        
        return overall_confirmed, details
    
    def get_trend_alignment_score(self) -> Tuple[float, str]:
        """
        Get overall trend alignment score (-1 to +1)
        
        Returns:
            (score, description)
            score > 0.5: Strong bullish alignment
            score < -0.5: Strong bearish alignment
            -0.5 to 0.5: Mixed/neutral
        """
        if not self.analysis:
            return 0, "No data"
        
        # Weight higher timeframes more
        weights = {
            '1m': 0.5, '5m': 1, '15m': 2, '30m': 2,
            '1h': 3, '4h': 4, '1d': 5
        }
        
        total_score = 0
        total_weight = 0
        
        for tf, analysis in self.analysis.items():
            weight = weights.get(tf, 1)
            # Normalize trend value to -1 to +1
            normalized_trend = analysis.trend.value / 2
            total_score += normalized_trend * weight
            total_weight += weight
        
        if total_weight == 0:
            return 0, "No data"
        
        normalized = total_score / total_weight
        
        if normalized > 0.5:
            desc = "STRONG BULLISH 🟢🟢"
        elif normalized > 0.2:
            desc = "BULLISH 🟢"
        elif normalized < -0.5:
            desc = "STRONG BEARISH 🔴🔴"
        elif normalized < -0.2:
            desc = "BEARISH 🔴"
        else:
            desc = "NEUTRAL ⚪"
        
        return normalized, desc
    
    def get_best_direction(self) -> Tuple[str, float]:
        """
        Get the best trading direction based on MTF analysis
        
        Returns:
            (direction: 'LONG'/'SHORT'/'NEUTRAL', confidence: 0-1)
        """
        score, _ = self.get_trend_alignment_score()
        
        if score > 0.3:
            return 'LONG', min(abs(score), 1.0)
        elif score < -0.3:
            return 'SHORT', min(abs(score), 1.0)
        else:
            return 'NEUTRAL', 0
    
    def print_analysis(self):
        """Print formatted analysis for all timeframes"""
        print("\n" + "="*70)
        print("📊 MULTI-TIMEFRAME ANALYSIS")
        print("="*70)
        
        if not self.analysis:
            print("No data loaded. Call fetch_all_timeframes() or add_data() first.")
            return
        
        # Header
        print(f"{'TF':<6} {'Trend':<18} {'EMA50/200':<20} {'RSI':<8} {'ATR%':<8}")
        print("-"*70)
        
        for tf in self.TIMEFRAME_ORDER:
            if tf not in self.analysis:
                continue
            
            a = self.analysis[tf]
            trend_emoji = "🟢" if a.trend.value > 0 else "🔴" if a.trend.value < 0 else "⚪"
            
            ema_str = f"{a.ema_fast:.2f} / {a.ema_slow:.2f}"
            
            print(f"{tf:<6} {trend_emoji} {a.trend.name:<15} {ema_str:<20} "
                  f"{a.rsi:.1f}{'':>3} {a.atr_pct:.2f}%")
        
        # Alignment score
        score, desc = self.get_trend_alignment_score()
        direction, confidence = self.get_best_direction()
        
        print("-"*70)
        print(f"ALIGNMENT SCORE: {score:+.2f} | {desc}")
        print(f"SUGGESTED BIAS:  {direction} (confidence: {confidence:.0%})")
        print("="*70 + "\n")
    
    def should_take_trade(
        self,
        entry_timeframe: str,
        direction: str
    ) -> Tuple[bool, str]:
        """
        Simple check if trade should be taken
        
        Args:
            entry_timeframe: Your trading timeframe
            direction: 'LONG' or 'SHORT'
        
        Returns:
            (should_trade: bool, reason: str)
        """
        confirmed, details = self.get_confirmation(
            entry_timeframe, direction, require_all=False, min_higher_tfs=1
        )
        
        if confirmed:
            rate = details.get('confirmation_rate', '?/?')
            return True, f"MTF confirmed ({rate} higher TFs align)"
        else:
            # Find which TFs disagree
            disagreeing = []
            for tf, info in details.get('higher_tfs', {}).items():
                if not info.get('confirmed', True):
                    disagreeing.append(f"{tf}={info.get('trend', '?')}")
            
            return False, f"MTF rejection: {', '.join(disagreeing)}"


# Global instance
_mtf_analyzer = None

def get_mtf_analyzer(exchange_id: str = 'binance') -> MultiTimeframeAnalyzer:
    """Get or create global MTF analyzer instance"""
    global _mtf_analyzer
    if _mtf_analyzer is None:
        _mtf_analyzer = MultiTimeframeAnalyzer(exchange_id=exchange_id)
    return _mtf_analyzer


if __name__ == "__main__":
    # Example usage
    mtf = MultiTimeframeAnalyzer(exchange_id='binance')
    
    # Fetch data for BTC/USDT
    mtf.fetch_all_timeframes('BTC/USDT', timeframes=['15m', '1h', '4h', '1d'])
    
    # Print analysis
    mtf.print_analysis()
    
    # Check confirmation for a 15m LONG
    confirmed, details = mtf.get_confirmation('15m', 'LONG')
    print(f"\n15m LONG Confirmed: {confirmed}")
    print(f"Details: {details}")
    
    # Simple trade check
    should_trade, reason = mtf.should_take_trade('15m', 'LONG')
    print(f"\nShould take 15m LONG? {should_trade}")
    print(f"Reason: {reason}")
