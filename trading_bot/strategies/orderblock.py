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
    created_at: Optional[datetime] = None  # When OB was created

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
        
        # Track last printed OB to avoid duplicates
        self._last_printed_ob_long = None
        self._last_printed_ob_short = None

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
                    ob_type='bearish',
                    created_at=current.name if hasattr(current, 'name') else df.index[current_idx]
                )
                self.short_obs.append(ob)
                self.last_short_index = self.last_up_index
                self.bearish_alert = True
                
                # Print OB info
                self._print_ob_info(ob, current['close'], df)

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
                    ob_type='bullish',
                    created_at=current.name if hasattr(current, 'name') else df.index[current_idx]
                )
                self.long_obs.append(ob)
                self.last_long_index = current_idx

                # Print OB info
                self._print_ob_info(ob, current['close'], df)

                # Remove mitigated short OB
                self.short_obs.pop()

    def _print_ob_info(self, ob: OrderBlock, current_price: float, df: pd.DataFrame):
        """Print order block information"""
        ob_id = id(ob)
        
        # Check if we already printed this OB
        if ob.ob_type == 'bullish':
            if self._last_printed_ob_long == ob_id:
                return
            self._last_printed_ob_long = ob_id
        else:
            if self._last_printed_ob_short == ob_id:
                return
            self._last_printed_ob_short = ob_id
        
        emoji = "🟢" if ob.ob_type == "bullish" else "🔴"
        ob_range = ob.top - ob.bottom
        
        try:
            if ob.ob_type == "bullish":
                distance_pct = ((current_price - ob.bottom) / ob.bottom * 100) if ob.bottom != 0 else 0
            else:
                distance_pct = ((ob.top - current_price) / current_price * 100) if current_price != 0 else 0
                
            width_pct = (ob_range/ob.bottom*100) if ob.bottom != 0 else 0
        except ZeroDivisionError:
            distance_pct = 0
            width_pct = 0

        print(f"\n{emoji} {'='*60}")
        print(f"NEW {ob.ob_type.upper()} ORDER BLOCK DETECTED")
        print(f"{'='*60}")
        print(f"📍 Price Range:  ${ob.bottom:,.2f} - ${ob.top:,.2f}")
        print(f"📏 OB Width:     ${ob_range:,.2f} ({width_pct:.2f}%)")
        print(f"💰 Current Price: ${current_price:,.2f}")
        print(f"📊 Distance:     {distance_pct:.2f}% {'above' if ob.ob_type == 'bullish' else 'below'} OB")
        print(f"🕐 Created:      {ob.created_at}")
        print(f"📈 State:        {OBState(ob.state).name}")
        print(f"{'='*60}\n")
    
    def get_last_ob_info(self) -> Dict[str, Any]:
        """Get information about the last order blocks"""
        result = {
            'bullish': None,
            'bearish': None
        }
        
        if self.long_obs:
            ob = self.long_obs[-1]
            result['bullish'] = {
                'top': ob.top,
                'bottom': ob.bottom,
                'range': ob.top - ob.bottom,
                'created_at': ob.created_at,
                'state': OBState(ob.state).name,
                'timestamp': ob.timestamp
            }
        
        if self.short_obs:
            ob = self.short_obs[-1]
            result['bearish'] = {
                'top': ob.top,
                'bottom': ob.bottom,
                'range': ob.top - ob.bottom,
                'created_at': ob.created_at,
                'state': OBState(ob.state).name,
                'timestamp': ob.timestamp
            }
        
        return result

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
# ORDER BLOCK STRATEGY - PREMIUM (MSS CONFIRMATION ENTRY)
# ============================================================================

class OrderBlockStrategyPremium(OrderBlockStrategy):
    """
    Order Block Strategy - PREMIUM (MSS Confirmation Entry)
    
    This strategy follows institutional trading methodology:
    
    STEP 1: TOP-DOWN ANALYSIS (OB Detection)
    - Identify valid OBs on higher timeframe with BOS + FVG + Displacement
    - Mark these as Point of Interest (POI)
    
    STEP 2: WAIT FOR PRICE TO RETURN
    - Wait for price to retrace back to the OB zone
    - Don't enter immediately - wait for confirmation
    
    STEP 3: ENTRY CONFIRMATION (MSS)
    - Once price taps OB, look for Market Structure Shift
    - Bullish MSS: Break of lower high (in uptrend setup)
    - Bearish MSS: Break of higher low (in downtrend setup)
    
    STEP 4: ENTRY EXECUTION
    - Entry: After MSS confirmation
    - Stop Loss: Below/above the MSS swing point (tighter SL)
    - Take Profit: Target at least 3x risk
    
    Benefits:
    - Much higher win rate due to confirmation
    - Tighter stop losses = better risk/reward
    - Fewer false entries
    - Aligns with institutional Smart Money Concepts
    """
    
    def __init__(self,
                 name: str = "OrderBlockStrategyPremium",
                 # Structure Settings
                 input_range: int = 25,
                 # Trading Settings
                 min_risk_reward: float = 2.0,  # Higher RR for premium setups
                 sl_atr_mult: float = 1.0,      # Tighter SL (based on MSS swing)
                 tp_rr_mult: float = 3.0,       # At least 3x risk
                 # FVG Settings
                 require_fvg: bool = True,       # Must have FVG for valid OB
                 min_fvg_percent: float = 0.1,   # Min FVG size (0.1% of price)
                 # Displacement Settings
                 require_displacement: bool = True,
                 min_displacement_percent: float = 0.5,  # Min 0.5% move
                 min_displacement_candles: int = 2,      # Min consecutive candles
                 # MSS Settings
                 require_ob_mss: bool = False,    # OB must cause trend shift
                 mss_lookback: int = 50,          # Bars to check for OB trend
                 # Entry Confirmation Settings
                 mss_confirmation_bars: int = 10,  # Bars to wait for MSS after OB tap
                 mss_swing_lookback: int = 5,      # Bars to find swing for MSS
                 # Filter Settings
                 first_retest_only: bool = True,
                 max_age_bars: int = 500,        # OBs expire faster
                 # Position Settings
                 position_size: float = 0.5):
        
        super().__init__(
            name=name,
            input_range=input_range,
            min_risk_reward=min_risk_reward,
            sl_atr_mult=sl_atr_mult,
            tp_rr_mult=tp_rr_mult,
            use_mitigated_blocks=False,
            first_retest_only=first_retest_only,
            max_age_bars=max_age_bars,
            position_size=position_size
        )
        
        # FVG Settings
        self.require_fvg = require_fvg
        self.min_fvg_percent = min_fvg_percent
        
        # Displacement Settings
        self.require_displacement = require_displacement
        self.min_displacement_percent = min_displacement_percent
        self.min_displacement_candles = min_displacement_candles
        
        # MSS Settings (for OB creation)
        self.require_ob_mss = require_ob_mss
        self.mss_lookback = mss_lookback
        
        # Entry Confirmation Settings
        self.mss_confirmation_bars = mss_confirmation_bars
        self.mss_swing_lookback = mss_swing_lookback
        
        # Track qualified OBs
        self.qualified_long_obs: List[OrderBlock] = []
        self.qualified_short_obs: List[OrderBlock] = []
        
        # Track POI (Point of Interest) state
        self.active_poi: Dict[int, Dict] = {}  # ob_index -> poi_state
    
    def _init_state(self):
        """Initialize state variables"""
        super()._init_state()
        self.qualified_long_obs = []
        self.qualified_short_obs = []
        self.prev_trend = None
        self.active_poi = {}
    
    def _detect_fvg(self, df: pd.DataFrame, current_idx: int, direction: str) -> Tuple[bool, float]:
        """
        Detect Fair Value Gap (FVG) / Imbalance
        
        Bullish FVG: Gap between candle[i-2].high and candle[i].low
        Bearish FVG: Gap between candle[i-2].low and candle[i].high
        
        Returns: (has_fvg, fvg_size_percent)
        """
        if current_idx < 3:
            return False, 0.0
        
        candle_1 = df.iloc[current_idx - 2]  # First candle
        candle_3 = df.iloc[current_idx]       # Third candle (current)
        
        if direction == 'bullish':
            # Bullish FVG: candle_3.low > candle_1.high (gap up)
            fvg_size = candle_3['low'] - candle_1['high']
            if fvg_size > 0:
                fvg_percent = (fvg_size / candle_1['high']) * 100
                return fvg_percent >= self.min_fvg_percent, fvg_percent
        else:
            # Bearish FVG: candle_3.high < candle_1.low (gap down)
            fvg_size = candle_1['low'] - candle_3['high']
            if fvg_size > 0:
                fvg_percent = (fvg_size / candle_1['low']) * 100
                return fvg_percent >= self.min_fvg_percent, fvg_percent
        
        return False, 0.0
    
    def _detect_displacement(self, df: pd.DataFrame, ob_idx: int, current_idx: int, direction: str) -> Tuple[bool, float]:
        """
        Detect price displacement (strong momentum move)
        
        Checks:
        1. Total price movement from OB
        2. Number of consecutive same-direction candles
        
        Returns: (has_displacement, displacement_percent)
        """
        if current_idx <= ob_idx + 1:
            return False, 0.0
        
        ob_price = df.iloc[ob_idx]['close']
        current_price = df.iloc[current_idx]['close']
        
        # Calculate total displacement
        if direction == 'bullish':
            displacement = ((current_price - ob_price) / ob_price) * 100
        else:
            displacement = ((ob_price - current_price) / ob_price) * 100
        
        # Check if displacement meets minimum
        if displacement < self.min_displacement_percent:
            return False, displacement
        
        # Count consecutive same-direction candles
        consecutive_count = 0
        for i in range(ob_idx + 1, min(current_idx + 1, ob_idx + 10)):
            candle = df.iloc[i]
            body = candle['close'] - candle['open']
            
            if direction == 'bullish' and body > 0:
                consecutive_count += 1
            elif direction == 'bearish' and body < 0:
                consecutive_count += 1
            else:
                break  # Sequence broken
        
        # Check minimum consecutive candles
        if consecutive_count < self.min_displacement_candles:
            return False, displacement
        
        return True, displacement
    
    def _detect_trend_mss(self, df: pd.DataFrame, current_idx: int, new_direction: str) -> bool:
        """
        Detect Market Structure Shift for OB creation (trend reversal)
        
        MSS occurs when:
        - Previous trend was bullish → now bearish BOS
        - Previous trend was bearish → now bullish BOS
        
        Returns: True if this is a market structure shift
        """
        if current_idx < self.mss_lookback:
            return False
        
        # Determine previous trend using highs and lows
        lookback_data = df.iloc[current_idx - self.mss_lookback:current_idx]
        closes = lookback_data['close'].values
        
        # Simple trend detection: compare first half avg to second half avg
        mid = len(closes) // 2
        first_half_avg = closes[:mid].mean()
        second_half_avg = closes[mid:].mean()
        
        if second_half_avg > first_half_avg * 1.01:  # 1% threshold
            prev_trend = 'bullish'
        elif second_half_avg < first_half_avg * 0.99:
            prev_trend = 'bearish'
        else:
            prev_trend = 'neutral'
        
        # MSS occurs when new direction opposes previous trend
        if new_direction == 'bearish' and prev_trend == 'bullish':
            return True  # Bullish to bearish shift
        elif new_direction == 'bullish' and prev_trend == 'bearish':
            return True  # Bearish to bullish shift
        
        return False
    
    def _find_swing_high(self, df: pd.DataFrame, start_idx: int, end_idx: int) -> Tuple[float, int]:
        """Find the highest swing high in range"""
        if start_idx >= end_idx or start_idx < 0:
            return 0.0, -1
        
        end_idx = min(end_idx, len(df))
        subset = df.iloc[start_idx:end_idx]
        
        if len(subset) == 0:
            return 0.0, -1
        
        max_idx = subset['high'].idxmax()
        if isinstance(max_idx, int):
            return subset.loc[max_idx, 'high'], max_idx
        else:
            # Handle datetime index
            pos = subset.index.get_loc(max_idx)
            return subset.iloc[pos]['high'], start_idx + pos
    
    def _find_swing_low(self, df: pd.DataFrame, start_idx: int, end_idx: int) -> Tuple[float, int]:
        """Find the lowest swing low in range"""
        if start_idx >= end_idx or start_idx < 0:
            return float('inf'), -1
        
        end_idx = min(end_idx, len(df))
        subset = df.iloc[start_idx:end_idx]
        
        if len(subset) == 0:
            return float('inf'), -1
        
        min_idx = subset['low'].idxmin()
        if isinstance(min_idx, int):
            return subset.loc[min_idx, 'low'], min_idx
        else:
            # Handle datetime index
            pos = subset.index.get_loc(min_idx)
            return subset.iloc[pos]['low'], start_idx + pos
    
    def _detect_entry_mss(self, df: pd.DataFrame, current_idx: int, poi: Dict, direction: str) -> Tuple[bool, float]:
        """
        Detect Market Structure Shift for entry confirmation
        
        After price taps OB:
        - For LONG: Look for break of lower high (bullish MSS)
        - For SHORT: Look for break of higher low (bearish MSS)
        
        Returns: (mss_confirmed, sl_price)
        """
        tap_idx = poi['tap_index']
        bars_since_tap = current_idx - tap_idx
        
        if bars_since_tap < 2:
            return False, 0.0
        
        if bars_since_tap > self.mss_confirmation_bars:
            # Too many bars without MSS - invalidate POI
            return False, 0.0
        
        current = df.iloc[current_idx]
        
        if direction == 'bullish':
            # For bullish entry: need break of lower high
            # Find the swing low since tap (this will be our SL reference)
            swing_low, swing_low_idx = self._find_swing_low(df, tap_idx, current_idx)
            
            if swing_low_idx == -1:
                return False, 0.0
            
            # Find swing high after the swing low
            swing_high, swing_high_idx = self._find_swing_high(df, swing_low_idx, current_idx)
            
            if swing_high_idx == -1 or swing_high_idx <= swing_low_idx:
                return False, 0.0
            
            # MSS confirmed when price breaks above the swing high
            if current['close'] > swing_high:
                # SL below the swing low
                sl_price = swing_low - (swing_low * 0.001)  # Small buffer
                return True, sl_price
                
        else:  # bearish
            # For bearish entry: need break of higher low
            # Find the swing high since tap (this will be our SL reference)
            swing_high, swing_high_idx = self._find_swing_high(df, tap_idx, current_idx)
            
            if swing_high_idx == -1:
                return False, 0.0
            
            # Find swing low after the swing high
            swing_low, swing_low_idx = self._find_swing_low(df, swing_high_idx, current_idx)
            
            if swing_low_idx == -1 or swing_low_idx <= swing_high_idx:
                return False, 0.0
            
            # MSS confirmed when price breaks below the swing low
            if current['close'] < swing_low:
                # SL above the swing high
                sl_price = swing_high + (swing_high * 0.001)  # Small buffer
                return True, sl_price
        
        return False, 0.0
    
    def _detect_bearish_bos(self, df: pd.DataFrame, current, current_idx: int):
        """Detect bearish BOS with FVG and displacement validation - creates POI"""
        prev_close = df.iloc[current_idx - 1]['close']
        
        if prev_close >= self.structure_low and current['close'] < self.structure_low:
            # Basic BOS detected - now validate quality
            
            # Check for FVG
            has_fvg, fvg_percent = True, 0.0
            if self.require_fvg:
                has_fvg, fvg_percent = self._detect_fvg(df, current_idx, 'bearish')
            
            # Check for displacement
            has_displacement, displacement_pct = True, 0.0
            if self.require_displacement:
                has_displacement, displacement_pct = self._detect_displacement(
                    df, self.last_up_index, current_idx, 'bearish'
                )
            
            # Check for trend MSS (optional)
            is_trend_mss = False
            if self.require_ob_mss:
                is_trend_mss = self._detect_trend_mss(df, current_idx, 'bearish')
                if not is_trend_mss:
                    return  # Skip if trend MSS required but not detected
            else:
                is_trend_mss = self._detect_trend_mss(df, current_idx, 'bearish')
            
            # Only create OB if all conditions met
            if has_fvg and has_displacement:
                if current_idx - self.last_up_index < self.max_age_bars:
                    ob = OrderBlock(
                        index=self.last_up_index,
                        timestamp=df.index[self.last_up_index],
                        high=self.last_high,
                        low=self.last_up_low,
                        close=df.iloc[self.last_up_index]['close'],
                        open=df.iloc[self.last_up_index]['open'],
                        ob_type='bearish',
                        created_at=current.name if hasattr(current, 'name') else df.index[current_idx]
                    )
                    
                    # Add to qualified list
                    self.short_obs.append(ob)
                    self.qualified_short_obs.append(ob)
                    self.last_short_index = self.last_up_index
                    self.bearish_alert = True
                    
                    # Print premium OB info
                    self._print_premium_ob_info(
                        ob, current['close'], df, 
                        has_fvg, fvg_percent,
                        has_displacement, displacement_pct,
                        is_trend_mss
                    )
    
    def _detect_bullish_bos(self, df: pd.DataFrame, current, current_idx: int):
        """Detect bullish BOS with FVG and displacement validation - creates POI"""
        if not self.short_obs:
            return
        
        short_ob = self.short_obs[-1]
        
        if current['close'] > short_ob.top and current_idx > short_ob.index:
            # Basic BOS detected - now validate quality
            
            # Check for FVG
            has_fvg, fvg_percent = True, 0.0
            if self.require_fvg:
                has_fvg, fvg_percent = self._detect_fvg(df, current_idx, 'bullish')
            
            # Check for displacement
            has_displacement, displacement_pct = True, 0.0
            if self.require_displacement:
                has_displacement, displacement_pct = self._detect_displacement(
                    df, self.last_down_index, current_idx, 'bullish'
                )
            
            # Check for trend MSS (optional)
            is_trend_mss = False
            if self.require_ob_mss:
                is_trend_mss = self._detect_trend_mss(df, current_idx, 'bullish')
                if not is_trend_mss:
                    self.short_obs.pop()
                    return
            else:
                is_trend_mss = self._detect_trend_mss(df, current_idx, 'bullish')
            
            self.bullish_alert = True
            
            # Only create OB if all conditions met
            if has_fvg and has_displacement:
                if current_idx - self.last_down_index < self.max_age_bars and current_idx > self.last_long_index:
                    ob = OrderBlock(
                        index=self.last_down_index,
                        timestamp=df.index[self.last_down_index],
                        high=self.last_down_high,
                        low=self.last_down_low,
                        close=df.iloc[self.last_down_index]['close'],
                        open=df.iloc[self.last_down_index]['open'],
                        ob_type='bullish',
                        created_at=current.name if hasattr(current, 'name') else df.index[current_idx]
                    )
                    
                    # Add to qualified list
                    self.long_obs.append(ob)
                    self.qualified_long_obs.append(ob)
                    self.last_long_index = current_idx
                    
                    # Print premium OB info
                    self._print_premium_ob_info(
                        ob, current['close'], df,
                        has_fvg, fvg_percent,
                        has_displacement, displacement_pct,
                        is_trend_mss
                    )
            
            # Remove mitigated short OB
            self.short_obs.pop()
    
    def _check_entries(self, df: pd.DataFrame, current, position) -> Dict:
        """
        Check for entry signals with MSS confirmation
        
        Entry Logic:
        1. Price must tap into OB zone (POI activation)
        2. Wait for MSS confirmation
        3. Entry after MSS with SL at swing point
        4. TP at least 3x risk
        """
        if PositionSide and position and position != PositionSide.FLAT:
            return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}
        
        current_idx = len(df) - 1
        atr = current.get('atr', current['close'] * 0.02)
        
        # =====================================================================
        # STEP 1: Check for POI activation (price taps OB)
        # =====================================================================
        
        # Check bullish OBs for tap
        for ob in self.long_obs:
            if ob.state != OBState.ACTIVE.value:
                continue
            
            ob_key = f"long_{ob.index}"
            
            # Price taps OB zone (enters from above)
            if current['low'] <= ob.top and current['high'] > ob.bottom:
                if ob_key not in self.active_poi:
                    # Activate POI - don't enter yet, wait for MSS
                    self.active_poi[ob_key] = {
                        'ob': ob,
                        'direction': 'bullish',
                        'tap_index': current_idx,
                        'tap_price': current['low'],
                        'waiting_mss': True
                    }
                    print(f"\n📍 POI ACTIVATED - Bullish OB tapped at ${current['low']:,.2f}")
                    print(f"   Waiting for MSS confirmation...")
        
        # Check bearish OBs for tap
        for ob in self.short_obs:
            if ob.state != OBState.ACTIVE.value:
                continue
            
            ob_key = f"short_{ob.index}"
            
            # Price taps OB zone (enters from below)
            if current['high'] >= ob.bottom and current['low'] < ob.top:
                if ob_key not in self.active_poi:
                    # Activate POI - don't enter yet, wait for MSS
                    self.active_poi[ob_key] = {
                        'ob': ob,
                        'direction': 'bearish',
                        'tap_index': current_idx,
                        'tap_price': current['high'],
                        'waiting_mss': True
                    }
                    print(f"\n📍 POI ACTIVATED - Bearish OB tapped at ${current['high']:,.2f}")
                    print(f"   Waiting for MSS confirmation...")
        
        # =====================================================================
        # STEP 2: Check active POIs for MSS confirmation
        # =====================================================================
        
        expired_pois = []
        
        for poi_key, poi in self.active_poi.items():
            if not poi['waiting_mss']:
                continue
            
            direction = poi['direction']
            ob = poi['ob']
            bars_since_tap = current_idx - poi['tap_index']
            
            # Check if POI expired (too many bars without MSS)
            if bars_since_tap > self.mss_confirmation_bars:
                expired_pois.append(poi_key)
                print(f"\n⏰ POI EXPIRED - No MSS within {self.mss_confirmation_bars} bars")
                continue
            
            # Check for MSS confirmation
            mss_confirmed, sl_price = self._detect_entry_mss(df, current_idx, poi, direction)
            
            if mss_confirmed:
                # =====================================================================
                # STEP 3: ENTRY EXECUTION
                # =====================================================================
                
                entry_price = current['close']
                
                if direction == 'bullish':
                    # LONG entry
                    risk_distance = entry_price - sl_price
                    tp_price = entry_price + (risk_distance * self.tp_rr_mult)
                    
                    # Verify R:R
                    reward = tp_price - entry_price
                    rr = reward / risk_distance if risk_distance > 0 else 0
                    
                    if rr >= self.min_risk_reward:
                        expired_pois.append(poi_key)
                        
                        print(f"\n✅ {'='*60}")
                        print(f"🟢 LONG ENTRY - MSS CONFIRMED!")
                        print(f"{'='*60}")
                        print(f"📍 Entry:     ${entry_price:,.2f}")
                        print(f"🛑 Stop Loss: ${sl_price:,.2f} (MSS swing low)")
                        print(f"🎯 Target:    ${tp_price:,.2f} ({self.tp_rr_mult}x risk)")
                        print(f"📊 Risk:      ${risk_distance:,.2f} ({risk_distance/entry_price*100:.2f}%)")
                        print(f"📈 Reward:    ${reward:,.2f} ({reward/entry_price*100:.2f}%)")
                        print(f"⚖️  R:R:       1:{rr:.1f}")
                        print(f"{'='*60}\n")
                        
                        return {
                            'signal': 'LONG',
                            'sl': sl_price,
                            'tp': tp_price,
                            'size': self.position_size,
                            'ob_index': ob.index,
                            'ob_type': 'bullish',
                            'entry_type': 'mss_confirmation'
                        }
                
                else:  # bearish
                    # SHORT entry
                    risk_distance = sl_price - entry_price
                    tp_price = entry_price - (risk_distance * self.tp_rr_mult)
                    
                    # Verify R:R
                    reward = entry_price - tp_price
                    rr = reward / risk_distance if risk_distance > 0 else 0
                    
                    if rr >= self.min_risk_reward:
                        expired_pois.append(poi_key)
                        
                        print(f"\n✅ {'='*60}")
                        print(f"🔴 SHORT ENTRY - MSS CONFIRMED!")
                        print(f"{'='*60}")
                        print(f"📍 Entry:     ${entry_price:,.2f}")
                        print(f"🛑 Stop Loss: ${sl_price:,.2f} (MSS swing high)")
                        print(f"🎯 Target:    ${tp_price:,.2f} ({self.tp_rr_mult}x risk)")
                        print(f"📊 Risk:      ${risk_distance:,.2f} ({risk_distance/entry_price*100:.2f}%)")
                        print(f"📈 Reward:    ${reward:,.2f} ({reward/entry_price*100:.2f}%)")
                        print(f"⚖️  R:R:       1:{rr:.1f}")
                        print(f"{'='*60}\n")
                        
                        return {
                            'signal': 'SHORT',
                            'sl': sl_price,
                            'tp': tp_price,
                            'size': self.position_size,
                            'ob_index': ob.index,
                            'ob_type': 'bearish',
                            'entry_type': 'mss_confirmation'
                        }
        
        # Clean up expired POIs
        for poi_key in expired_pois:
            del self.active_poi[poi_key]
        
        return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}
    
    def _print_premium_ob_info(self, ob: OrderBlock, current_price: float, df: pd.DataFrame,
                               has_fvg: bool, fvg_percent: float,
                               has_displacement: bool, displacement_pct: float,
                               is_trend_mss: bool):
        """Print premium order block information with quality metrics"""
        ob_id = id(ob)
        
        if ob.ob_type == 'bullish':
            if self._last_printed_ob_long == ob_id:
                return
            self._last_printed_ob_long = ob_id
        else:
            if self._last_printed_ob_short == ob_id:
                return
            self._last_printed_ob_short = ob_id
        
        emoji = "🟢" if ob.ob_type == "bullish" else "🔴"
        quality = "⭐⭐⭐ PREMIUM POI" if is_trend_mss else "⭐⭐ HIGH QUALITY POI"
        ob_range = ob.top - ob.bottom
        
        print(f"\n{emoji} {'='*60}")
        print(f"{quality} - {ob.ob_type.upper()} ORDER BLOCK")
        print(f"{'='*60}")
        print(f"📍 OB Zone:        ${ob.bottom:,.2f} - ${ob.top:,.2f}")
        print(f"📏 OB Width:       ${ob_range:,.2f} ({ob_range/ob.bottom*100:.2f}%)")
        print(f"💰 Current Price:  ${current_price:,.2f}")
        print(f"")
        print(f"✅ QUALITY CHECKS:")
        print(f"   📊 FVG/Imbalance:    {'YES' if has_fvg else 'NO'} ({fvg_percent:.2f}%)")
        print(f"   🚀 Displacement:     {'YES' if has_displacement else 'NO'} ({displacement_pct:.2f}%)")
        print(f"   🔄 Trend Reversal:   {'YES' if is_trend_mss else 'NO'}")
        print(f"")
        print(f"⏳ WAITING: Price to tap OB zone for entry")
        print(f"📋 ENTRY:   Will confirm with MSS on tap")
        print(f"🕐 Created: {ob.created_at}")
        print(f"{'='*60}\n")
    
    def get_stats(self) -> Dict:
        """Get strategy statistics including quality metrics"""
        return {
            'total_long_obs': len(self.long_obs),
            'total_short_obs': len(self.short_obs),
            'qualified_long_obs': len(self.qualified_long_obs),
            'qualified_short_obs': len(self.qualified_short_obs),
            'active_pois': len(self.active_poi),
            'require_fvg': self.require_fvg,
            'require_displacement': self.require_displacement,
            'require_ob_mss': self.require_ob_mss,
            'mss_confirmation_bars': self.mss_confirmation_bars
        }


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
