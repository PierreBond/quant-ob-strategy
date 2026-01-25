"""
Order Block Strategy - PineScript Port
======================================
Smart Money Concepts - Order Block detection and trading
Based on PineScript indicator logic

Features:
- Market Structure Detection (swing highs/lows)
- Break of Structure (BOS) detection
- Order Block creation on structure breaks
- OB Mitigation tracking
- Retest detection
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import pandas as pd
import numpy as np

# Handle imports
try:
    from .base import Strategy
    from ..backtest.engine import PositionSide
except ImportError:
    PositionSide = None

    class Strategy:
        """Fallback base strategy class"""
        def __init__(self, name: str = "BaseStrategy"):
            self.name = name
            self.parameters = {}
            self.data = None
            self.initialized = False


class OBState(Enum):
    """Order block state"""
    ACTIVE = 0
    MITIGATED = 1


@dataclass
class OrderBlock:
    """
    Order block structure matching PineScript logic

    Bullish OB: Formed after bearish OB is mitigated
    Bearish OB: Formed when bearish break of structure occurs
    """
    index: int
    timestamp: datetime
    high: float
    low: float
    close: float
    open: float
    ob_type: str  # 'bullish' or 'bearish'
    state: int = OBState.ACTIVE.value  # 0=active, 1=mitigated
    bos_confirmed: bool = False  # Break of structure confirmed

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def top(self) -> float:
        return self.high

    @property
    def bottom(self) -> float:
        return self.low

    @property
    def midpoint(self) -> float:
        return (self.high + self.low) / 2

    def to_dict(self) -> Dict:
        return {
            'index': self.index,
            'timestamp': self.timestamp.isoformat(),
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'open': self.open,
            'type': self.ob_type,
            'state': self.state,
            'bos_confirmed': self.bos_confirmed
        }


class OrderBlockStrategy(Strategy):
    """
    Order Block Strategy - Ported from PineScript

    Trading Logic (matching PineScript):
    1. Track structure: swing highs/lows within inputRange
    2. Bearish BOS: Price crosses below structure low → Create Bearish OB
    3. Bullish BOS: Price breaks above Bearish OB top → Mitigate Bearish OB,
       Create Bullish OB
    4. Bearish OB Mitigation: Price goes below Bullish OB bottom → Remove OB
    5. Bullish OB Mitigation: Price goes above Bullish OB top → Remove OB

    Entry Signals:
    - LONG when price re-tests Bullish OB (with validation)
    - SHORT when price re-tests Bearish OB (with validation)
    """

    def __init__(self,
                 name: str = "OrderBlockStrategy",
                 # Structure Settings (matching PineScript)
                 input_range: int = 25,  # Candle range for swing detection
                 # Trading Settings
                 min_risk_reward: float = 1.5,
                 sl_atr_mult: float = 2.0,
                 tp_rr_mult: float = 2.0,
                 # Filter Settings
                 use_mitigated_blocks: bool = False,  # Show mitigated blocks
                 first_retest_only: bool = True,  # Only trade first retest
                 max_age_bars: int = 1000,  # Max bars since OB formation
                 # Position Settings
                 position_size: float = 0.5):  # 50% of capital per trade
        super().__init__(name=name)

        # Structure Settings
        self.input_range = input_range

        # Trading Settings
        self.min_risk_reward = min_risk_reward
        self.sl_atr_mult = sl_atr_mult
        self.tp_rr_mult = tp_rr_mult

        # Filter Settings
        self.use_mitigated_blocks = use_mitigated_blocks
        self.first_retest_only = first_retest_only
        self.max_age_bars = max_age_bars

        # Position Settings
        self.position_size = position_size

    def on_init(self, df: pd.DataFrame):
        """Initialize strategy with data - calculate all needed values"""
        df = df.copy()

        # Calculate ATR for SL/TP
        df['atr'] = self._calculate_atr(df, 14)

        # Track last up/down candles (for OB placement)
        df['last_down_high'] = 0.0
        df['last_down_index'] = 0
        df['last_down_low'] = 0.0

        df['last_up_close'] = 0.0
        df['last_up_index'] = 0
        df['last_up_low'] = 0.0
        df['last_up_open'] = 0.0
        df['last_high'] = 0.0

        # Track current structure values
        df['structure_low'] = 0.0
        df['structure_low_index'] = 0

        # OB tracking columns
        df['long_ob_top'] = 0.0
        df['long_ob_bottom'] = 0.0
        df['long_ob_index'] = 0
        df['long_ob_state'] = 0  # 0=active, 1=mitigated

        df['short_ob_top'] = 0.0
        df['short_ob_bottom'] = 0.0
        df['short_ob_index'] = 0
        df['short_ob_state'] = 0

        # Signals
        df['bullish_signal'] = False
        df['bearish_signal'] = False
        df['long_retest'] = False
        df['short_retest'] = False

        # Store in strategy
        self.data = df
        self.initialized = True

        # Initialize state tracking
        self._init_state()

    def _init_state(self):
        """Initialize state variables for OB tracking"""
        # Last up/down tracking
        self.last_down_high = 0.0
        self.last_down_index = 0
        self.last_down_low = 0.0

        self.last_up_close = 0.0
        self.last_up_index = 0
        self.last_up_open = 0.0
        self.last_up_low = 0.0
        self.last_high = 0.0

        # Structure tracking
        self.structure_low = float('inf')
        self.structure_low_index = 0

        # OB tracking
        self.long_obs: List[OrderBlock] = []
        self.short_obs: List[OrderBlock] = []

        # Last OB indices (to prevent duplication)
        self.last_long_index = 0
        self.last_short_index = 0

        # Signals
        self.bullish_alert = False
        self.bearish_alert = False
        self.long_retest = False
        self.short_retest = False

    def on_bar(self, df: pd.DataFrame, position: PositionSide = None) -> Dict:
        """Generate trading signal for current bar"""
        if len(df) < self.input_range + 10:
            return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}

        current = df.iloc[-1]
        current_idx = len(df) - 1

        # Update state step by step
        self._update_structure(df, current_idx)
        self._detect_bearish_bos(df, current, current_idx)
        self._detect_bullish_bos(df, current, current_idx)
        self._update_ob_status(df, current, current_idx)

        # Reset candle signals
        self.long_retest = False
        self.short_retest = False

        # Check for entry signals
        return self._check_entries(df, current, position)

    def _update_structure(self, df: pd.DataFrame, current_idx: int):
        """Update structure low and track swing points"""
        lookback = self.input_range

        if current_idx < lookback + 1:
            return

        # Get structure low (lowest low in range)
        self.structure_low = df['low'].iloc[current_idx - lookback:current_idx].min()
        self.structure_low_index = df['low'].iloc[current_idx - lookback:current_idx].idxmin()

        if isinstance(self.structure_low_index, datetime):
            self.structure_low_index = df.index.get_loc(self.structure_low_index)
        else:
            # Already an index
            pass

        # Update last up/down candles
        last_row = df.iloc[current_idx - 1]

        if last_row['close'] < last_row['open']:
            # Bearish candle
            self.last_down_high = last_row['high']
            self.last_down_index = current_idx - 1
            self.last_down_low = last_row['low']
        else:
            # Bullish candle
            self.last_up_close = last_row['close']
            self.last_up_index = current_idx - 1
            self.last_up_open = last_row['open']
            self.last_up_low = last_row['low']
            self.last_high = last_row['high']

        # Update last high/low for accurate OB placement
        self.last_high = max(self.last_high, last_row['high'])
        self.last_low = min(self.last_down_low if self.last_down_low else float('inf'),
                           last_row['low']) if self.last_down_low else last_row['low']

    def _detect_bearish_bos(self, df: pd.DataFrame, current, current_idx: int):
        """Detect bearish break of structure - creates Bearish OB"""
        # Bearish BOS: price crosses below structure low
        prev_close = df.iloc[current_idx - 1]['close']

        if prev_close >= self.structure_low and current['close'] < self.structure_low:
            # Check timing (prevent duplicates)
            if current_idx - self.last_up_index < self.max_age_bars:
                # Create bearish order block
                ob = OrderBlock(
                    index=self.last_up_index,
                    timestamp=df.index[self.last_up_index],
                    high=self.last_high,
                    low=self.last_up_low,
                    close=df.iloc[self.last_up_index]['close'],
                    open=df.iloc[self.last_up_index]['open'],
                    ob_type='bearish'
                )
                self.short_obs.append(ob)
                self.last_short_index = self.last_up_index
                self.bearish_alert = True

    def _detect_bullish_bos(self, df: pd.DataFrame, current, current_idx: int):
        """Detect bullish break of structure - mitigates Bearish OB, creates Bullish OB"""
        if not self.short_obs:
            return

        # Check most recent short OB
        short_ob = self.short_obs[-1]

        # Bullish BOS: price breaks above Bearish OB top
        if current['close'] > short_ob.top and current_idx > short_ob.index:
            # Mitigate/remove short OB
            self.bullish_alert = True

            # Check timing and create Bullish OB
            if current_idx - self.last_down_index < self.max_age_bars and current_idx > self.last_long_index:
                # Create bullish order block
                ob = OrderBlock(
                    index=self.last_down_index,
                    timestamp=df.index[self.last_down_index],
                    high=self.last_down_high,
                    low=self.last_down_low,
                    close=df.iloc[self.last_down_index]['close'],
                    open=df.iloc[self.last_down_index]['open'],
                    ob_type='bullish'
                )
                self.long_obs.append(ob)
                self.last_long_index = current_idx

                # Remove mitigated short OB
                self.short_obs.pop()

    def _update_ob_status(self, df: pd.DataFrame, current, current_idx: int):
        """Update OB status (mitigation checks)"""
        # Check Long OB mitigation
        for i, ob in enumerate(self.long_obs):
            if ob.state == OBState.ACTIVE.value:
                # Long OB mitigated when price goes below bottom
                if current['close'] < ob.bottom:
                    ob.state = OBState.MITIGATED.value
                    if self.first_retest_only:
                        self.long_obs.pop(i)

        # Check Short OB mitigation
        for i, ob in enumerate(self.short_obs):
            if ob.state == OBState.ACTIVE.value:
                # Short OB mitigated when price goes above top
                if current['close'] > ob.top:
                    ob.state = OBState.MITIGATED.value
                    if self.first_retest_only:
                        self.short_obs.pop(i)

    def _check_entries(self, df: pd.DataFrame, current, position) -> Dict:
        """Check for entry signals"""
        if PositionSide and position and position != PositionSide.FLAT:
            return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}

        atr = current.get('atr', current['close'] * 0.02)

        # Check Long OB retest
        for ob in self.long_obs:
            if ob.state == OBState.ACTIVE.value:
                # Price enters OB zone
                if current['low'] <= ob.top and current['high'] > ob.top:
                    self.long_retest = True

                    # Generate LONG signal
                    sl_price = ob.bottom - atr * self.sl_atr_mult
                    risk_distance = current['close'] - sl_price
                    tp_price = current['close'] + risk_distance * self.tp_rr_mult
                    reward_distance = tp_price - current['close']

                    # Check risk/reward
                    rr = reward_distance / risk_distance if risk_distance > 0 else 0
                    if rr < self.min_risk_reward:
                        continue

                    return {
                        'signal': 'LONG',
                        'sl': sl_price,
                        'tp': tp_price,
                        'size': self.position_size,
                        'ob_index': ob.index,
                        'ob_type': 'bullish'
                    }

        # Check Short OB retest
        for ob in self.short_obs:
            if ob.state == OBState.ACTIVE.value:
                # Price enters OB zone
                if current['high'] >= ob.bottom and current['low'] < ob.bottom:
                    self.short_retest = True

                    # Generate SHORT signal
                    sl_price = ob.top + atr * self.sl_atr_mult
                    risk_distance = sl_price - current['close']
                    tp_price = current['close'] - risk_distance * self.tp_rr_mult
                    reward_distance = current['close'] - tp_price

                    # Check risk/reward
                    rr = reward_distance / risk_distance if risk_distance > 0 else 0
                    if rr < self.min_risk_reward:
                        continue

                    return {
                        'signal': 'SHORT',
                        'sl': sl_price,
                        'tp': tp_price,
                        'size': self.position_size,
                        'ob_index': ob.index,
                        'ob_type': 'bearish'
                    }

        return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}

    def _calculate_atr(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate ATR"""
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    def get_ob_zones(self) -> Dict:
        """Get current OB zones for visualization"""
        long_zones = [(ob.index, ob.top, ob.bottom, ob.ob_type, ob.state)
                      for ob in self.long_obs if ob.state == OBState.ACTIVE.value or self.use_mitigated_blocks]
        short_zones = [(ob.index, ob.top, ob.bottom, ob.ob_type, ob.state)
                       for ob in self.short_obs if ob.state == OBState.ACTIVE.value or self.use_mitigated_blocks]

        return {
            'long_zones': long_zones,
            'short_zones': short_zones,
            'structure_low': (self.structure_low_index, self.structure_low)
        }


# ============================================================================
# ORDER BLOCK STRATEGY - TRADE ALL (INCLUDING MITIGATED)
# ============================================================================

class OrderBlockStrategyAll(OrderBlockStrategy):
    """
    Order Block Strategy - Trades ALL Order Blocks (Active + Mitigated)
    
    This variant trades both active and mitigated order blocks, providing
    more trading opportunities. Mitigated OBs can still act as support/resistance
    zones and offer valid entry points.
    
    Key Differences from OrderBlockStrategy:
    - Trades mitigated order blocks (not just active ones)
    - Does NOT remove OBs after mitigation (keeps them for future retests)
    - Tracks retest count per OB to manage multiple entries
    - Optional: Reduced position size for mitigated OB trades
    
    Use Cases:
    - Higher frequency trading
    - Markets with strong historical S/R levels
    - When you want to trade OB zones multiple times
    """
    
    def __init__(self,
                 name: str = "OrderBlockStrategyAll",
                 # Structure Settings
                 input_range: int = 25,
                 # Trading Settings
                 min_risk_reward: float = 1.5,
                 sl_atr_mult: float = 2.0,
                 tp_rr_mult: float = 2.0,
                 # Filter Settings  
                 max_age_bars: int = 1000,
                 max_retests: int = 3,  # Max times to trade same OB
                 # Position Settings
                 position_size: float = 0.5,
                 mitigated_size_mult: float = 0.5):  # Reduce size for mitigated OBs
        
        # Initialize parent with use_mitigated_blocks=True, first_retest_only=False
        super().__init__(
            name=name,
            input_range=input_range,
            min_risk_reward=min_risk_reward,
            sl_atr_mult=sl_atr_mult,
            tp_rr_mult=tp_rr_mult,
            use_mitigated_blocks=True,
            first_retest_only=False,  # Don't remove after first retest
            max_age_bars=max_age_bars,
            position_size=position_size
        )
        
        self.max_retests = max_retests
        self.mitigated_size_mult = mitigated_size_mult
        
        # Track retest counts per OB
        self.ob_retest_counts: Dict[int, int] = {}  # ob_index -> retest_count
    
    def _init_state(self):
        """Initialize state variables - extends parent"""
        super()._init_state()
        self.ob_retest_counts = {}
    
    def _update_ob_status(self, df: pd.DataFrame, current, current_idx: int):
        """
        Update OB status - marks as mitigated but does NOT remove
        Override parent to keep mitigated OBs for trading
        """
        # Check Long OB mitigation
        for ob in self.long_obs:
            if ob.state == OBState.ACTIVE.value:
                # Long OB mitigated when price closes below bottom
                if current['close'] < ob.bottom:
                    ob.state = OBState.MITIGATED.value
                    # Don't remove - keep for future trades
        
        # Check Short OB mitigation  
        for ob in self.short_obs:
            if ob.state == OBState.ACTIVE.value:
                # Short OB mitigated when price closes above top
                if current['close'] > ob.top:
                    ob.state = OBState.MITIGATED.value
                    # Don't remove - keep for future trades
        
        # Clean up old OBs that have exceeded max_retests
        self._cleanup_exhausted_obs()
    
    def _cleanup_exhausted_obs(self):
        """Remove OBs that have been traded max_retests times"""
        self.long_obs = [
            ob for ob in self.long_obs 
            if self.ob_retest_counts.get(ob.index, 0) < self.max_retests
        ]
        self.short_obs = [
            ob for ob in self.short_obs
            if self.ob_retest_counts.get(ob.index, 0) < self.max_retests
        ]
    
    def _check_entries(self, df: pd.DataFrame, current, position) -> Dict:
        """
        Check for entry signals - trades BOTH active and mitigated OBs
        Override parent to include mitigated blocks
        """
        if PositionSide and position and position != PositionSide.FLAT:
            return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}
        
        atr = current.get('atr', current['close'] * 0.02)
        current_idx = len(df) - 1
        
        # Check Long OB retest (both active and mitigated)
        for ob in self.long_obs:
            # Skip if max retests reached
            if self.ob_retest_counts.get(ob.index, 0) >= self.max_retests:
                continue
            
            # Skip if OB is too old
            if current_idx - ob.index > self.max_age_bars:
                continue
            
            # Price enters OB zone (touch the top of bullish OB)
            if current['low'] <= ob.top and current['high'] > ob.top:
                self.long_retest = True
                
                # Generate LONG signal
                sl_price = ob.bottom - atr * self.sl_atr_mult
                risk_distance = current['close'] - sl_price
                tp_price = current['close'] + risk_distance * self.tp_rr_mult
                reward_distance = tp_price - current['close']
                
                # Check risk/reward
                rr = reward_distance / risk_distance if risk_distance > 0 else 0
                if rr < self.min_risk_reward:
                    continue
                
                # Determine position size based on OB state
                is_mitigated = ob.state == OBState.MITIGATED.value
                size = self.position_size
                if is_mitigated:
                    size *= self.mitigated_size_mult
                
                # Record retest
                self.ob_retest_counts[ob.index] = self.ob_retest_counts.get(ob.index, 0) + 1
                
                return {
                    'signal': 'LONG',
                    'sl': sl_price,
                    'tp': tp_price,
                    'size': size,
                    'ob_index': ob.index,
                    'ob_type': 'bullish',
                    'ob_state': 'mitigated' if is_mitigated else 'active',
                    'retest_count': self.ob_retest_counts[ob.index]
                }
        
        # Check Short OB retest (both active and mitigated)
        for ob in self.short_obs:
            # Skip if max retests reached
            if self.ob_retest_counts.get(ob.index, 0) >= self.max_retests:
                continue
            
            # Skip if OB is too old
            if current_idx - ob.index > self.max_age_bars:
                continue
            
            # Price enters OB zone (touch the bottom of bearish OB)
            if current['high'] >= ob.bottom and current['low'] < ob.bottom:
                self.short_retest = True
                
                # Generate SHORT signal
                sl_price = ob.top + atr * self.sl_atr_mult
                risk_distance = sl_price - current['close']
                tp_price = current['close'] - risk_distance * self.tp_rr_mult
                reward_distance = current['close'] - tp_price
                
                # Check risk/reward
                rr = reward_distance / risk_distance if risk_distance > 0 else 0
                if rr < self.min_risk_reward:
                    continue
                
                # Determine position size based on OB state
                is_mitigated = ob.state == OBState.MITIGATED.value
                size = self.position_size
                if is_mitigated:
                    size *= self.mitigated_size_mult
                
                # Record retest
                self.ob_retest_counts[ob.index] = self.ob_retest_counts.get(ob.index, 0) + 1
                
                return {
                    'signal': 'SHORT',
                    'sl': sl_price,
                    'tp': tp_price,
                    'size': size,
                    'ob_index': ob.index,
                    'ob_type': 'bearish',
                    'ob_state': 'mitigated' if is_mitigated else 'active',
                    'retest_count': self.ob_retest_counts[ob.index]
                }
        
        return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}
    
    def get_stats(self) -> Dict:
        """Get strategy statistics"""
        return {
            'active_long_obs': len([ob for ob in self.long_obs if ob.state == OBState.ACTIVE.value]),
            'mitigated_long_obs': len([ob for ob in self.long_obs if ob.state == OBState.MITIGATED.value]),
            'active_short_obs': len([ob for ob in self.short_obs if ob.state == OBState.ACTIVE.value]),
            'mitigated_short_obs': len([ob for ob in self.short_obs if ob.state == OBState.MITIGATED.value]),
            'total_retests': sum(self.ob_retest_counts.values()),
            'obs_traded': len(self.ob_retest_counts)
        }


# ============================================================================
# ORDER BLOCK STRATEGY - INVERSE (CONTRARIAN)
# ============================================================================

class OrderBlockStrategyInverse(OrderBlockStrategy):
    """
    Order Block Strategy - INVERSE / Contrarian
    
    This strategy INVERTS all order block signals:
    - When price retests a BULLISH OB → go SHORT (fade the support)
    - When price retests a BEARISH OB → go LONG (fade the resistance)
    
    Rationale:
    - Order blocks often get "hunted" before reversing
    - Smart money may use OBs as liquidity pools
    - Works well in ranging/choppy markets
    - Can profit when OBs fail (get mitigated)
    
    Risk Management:
    - SL placed beyond the OB zone (if OB holds, exit)
    - TP targets the opposite side of the range
    
    Use Cases:
    - Range-bound markets
    - When OBs are frequently failing
    - Liquidity grab / stop hunt trading
    - Mean reversion strategies
    """
    
    def __init__(self,
                 name: str = "OrderBlockStrategyInverse",
                 # Structure Settings
                 input_range: int = 25,
                 # Trading Settings
                 min_risk_reward: float = 1.5,
                 sl_atr_mult: float = 2.0,
                 tp_rr_mult: float = 2.0,
                 # Filter Settings
                 use_mitigated_blocks: bool = False,
                 first_retest_only: bool = True,
                 max_age_bars: int = 1000,
                 # Position Settings
                 position_size: float = 0.5):
        
        super().__init__(
            name=name,
            input_range=input_range,
            min_risk_reward=min_risk_reward,
            sl_atr_mult=sl_atr_mult,
            tp_rr_mult=tp_rr_mult,
            use_mitigated_blocks=use_mitigated_blocks,
            first_retest_only=first_retest_only,
            max_age_bars=max_age_bars,
            position_size=position_size
        )
    
    def _check_entries(self, df: pd.DataFrame, current, position) -> Dict:
        """
        Check for INVERSE entry signals
        - Bullish OB retest → SHORT (fade support)
        - Bearish OB retest → LONG (fade resistance)
        """
        if PositionSide and position and position != PositionSide.FLAT:
            return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}
        
        atr = current.get('atr', current['close'] * 0.02)
        
        # Check Bullish OB retest → GO SHORT (inverse)
        for ob in self.long_obs:
            if ob.state == OBState.ACTIVE.value:
                # Price enters bullish OB zone
                if current['low'] <= ob.top and current['high'] > ob.top:
                    self.long_retest = True
                    
                    # INVERSE: Generate SHORT signal on bullish OB
                    # SL above the OB top (if OB holds as support, we're wrong)
                    sl_price = ob.top + atr * self.sl_atr_mult
                    risk_distance = sl_price - current['close']
                    # TP below - targeting OB failure/mitigation
                    tp_price = current['close'] - risk_distance * self.tp_rr_mult
                    reward_distance = current['close'] - tp_price
                    
                    # Check risk/reward
                    rr = reward_distance / risk_distance if risk_distance > 0 else 0
                    if rr < self.min_risk_reward:
                        continue
                    
                    return {
                        'signal': 'SHORT',  # INVERSE: SHORT on bullish OB
                        'sl': sl_price,
                        'tp': tp_price,
                        'size': self.position_size,
                        'ob_index': ob.index,
                        'ob_type': 'bullish',
                        'inverse': True
                    }
        
        # Check Bearish OB retest → GO LONG (inverse)
        for ob in self.short_obs:
            if ob.state == OBState.ACTIVE.value:
                # Price enters bearish OB zone
                if current['high'] >= ob.bottom and current['low'] < ob.bottom:
                    self.short_retest = True
                    
                    # INVERSE: Generate LONG signal on bearish OB
                    # SL below the OB bottom (if OB holds as resistance, we're wrong)
                    sl_price = ob.bottom - atr * self.sl_atr_mult
                    risk_distance = current['close'] - sl_price
                    # TP above - targeting OB failure/mitigation
                    tp_price = current['close'] + risk_distance * self.tp_rr_mult
                    reward_distance = tp_price - current['close']
                    
                    # Check risk/reward
                    rr = reward_distance / risk_distance if risk_distance > 0 else 0
                    if rr < self.min_risk_reward:
                        continue
                    
                    return {
                        'signal': 'LONG',  # INVERSE: LONG on bearish OB
                        'sl': sl_price,
                        'tp': tp_price,
                        'size': self.position_size,
                        'ob_index': ob.index,
                        'ob_type': 'bearish',
                        'inverse': True
                    }
        
        return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}


# ============================================================================
# SIMPLE STRATEGIES FOR TESTING
# ============================================================================

class SimpleSMACrossover(Strategy):
    """Simple SMA Crossover Strategy for testing"""

    def __init__(self, fast_period: int = 10, slow_period: int = 20):
        super().__init__(f"SMA_{fast_period}_{slow_period}")
        self.fast_period = fast_period
        self.slow_period = slow_period

    def on_init(self, df: pd.DataFrame):
        df = df.copy()
        df['sma_fast'] = df['close'].rolling(self.fast_period).mean()
        df['sma_slow'] = df['close'].rolling(self.slow_period).mean()
        self.data = df
        self.initialized = True

    def on_bar(self, df: pd.DataFrame, position: PositionSide = None) -> Dict:
        if len(df) < 2:
            return {'signal': 'FLAT'}

        current = df.iloc[-1]
        prev = df.iloc[-2]

        # Golden cross
        if prev['sma_fast'] <= prev['sma_slow'] and current['sma_fast'] > current['sma_slow']:
            return {
                'signal': 'LONG',
                'sl': current['close'] * 0.98,
                'tp': current['close'] * 1.04,
                'size': 0.5
            }

        # Death cross
        if prev['sma_fast'] >= prev['sma_slow'] and current['sma_fast'] < current['sma_slow']:
            return {
                'signal': 'SHORT',
                'sl': current['close'] * 1.02,
                'tp': current['close'] * 0.96,
                'size': 0.5
            }

        return {'signal': 'FLAT'}


class RSIStrategy(Strategy):
    """RSI Mean Reversion Strategy"""

    def __init__(self, rsi_period: int = 14, oversold: int = 30, overbought: int = 70):
        super().__init__(f"RSI_{rsi_period}_{oversold}_{overbought}")
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought

    def on_init(self, df: pd.DataFrame):
        df = df.copy()
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / (loss + 1e-10)
        df['rsi'] = 100 - (100 / (1 + rs))
        self.data = df
        self.initialized = True

    def on_bar(self, df: pd.DataFrame, position: PositionSide = None) -> Dict:
        current = df.iloc[-1]
        rsi = current['rsi']

        if rsi < self.oversold:
            return {
                'signal': 'LONG',
                'sl': current['close'] * 0.98,
                'tp': current['close'] * 1.04,
                'size': 0.5
            }
        elif rsi > self.overbought:
            return {
                'signal': 'SHORT',
                'sl': current['close'] * 1.02,
                'tp': current['close'] * 0.96,
                'size': 0.5
            }

        return {'signal': 'FLAT'}
