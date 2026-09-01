"""
Order Block Variants - All & Inverse Strategies
================================================
"""

from typing import Dict, List
import pandas as pd

from .ob_core import (
    OrderBlockStrategy, OrderBlock, OBState, Strategy, PositionSide
)


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
    """

    def __init__(self,
                 name: str = "OrderBlockStrategyAll",
                 input_range: int = 25,
                 min_risk_reward: float = 1.5,
                 sl_atr_mult: float = 2.0,
                 tp_rr_mult: float = 2.0,
                 max_age_bars: int = 1000,
                 max_retests: int = 3,
                 position_size: float = 0.5,
                 mitigated_size_mult: float = 0.5):

        super().__init__(
            name=name, input_range=input_range,
            min_risk_reward=min_risk_reward, sl_atr_mult=sl_atr_mult,
            tp_rr_mult=tp_rr_mult, use_mitigated_blocks=True,
            first_retest_only=False, max_age_bars=max_age_bars,
            position_size=position_size
        )
        self.max_retests = max_retests
        self.mitigated_size_mult = mitigated_size_mult
        self.ob_retest_counts: Dict[int, int] = {}

    def _init_state(self):
        super()._init_state()
        self.ob_retest_counts = {}

    def _update_ob_status(self, df, current, current_idx):
        for ob in self.long_obs:
            if ob.state == OBState.ACTIVE.value and current['close'] < ob.bottom:
                ob.state = OBState.MITIGATED.value
        for ob in self.short_obs:
            if ob.state == OBState.ACTIVE.value and current['close'] > ob.top:
                ob.state = OBState.MITIGATED.value
        self._cleanup_exhausted_obs()

    def _cleanup_exhausted_obs(self):
        self.long_obs = [ob for ob in self.long_obs
                         if self.ob_retest_counts.get(ob.index, 0) < self.max_retests]
        self.short_obs = [ob for ob in self.short_obs
                          if self.ob_retest_counts.get(ob.index, 0) < self.max_retests]

    def _check_entries(self, df, current, position):
        if PositionSide and position and position != PositionSide.FLAT:
            return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}

        atr = current.get('atr', current['close'] * 0.02)
        current_idx = len(df) - 1

        for ob in self.long_obs:
            if self.ob_retest_counts.get(ob.index, 0) >= self.max_retests:
                continue
            if current_idx - ob.index > self.max_age_bars:
                continue
            if current['low'] <= ob.top and current['high'] > ob.top:
                self.long_retest = True
                sl_price = ob.bottom - atr * self.sl_atr_mult
                risk_distance = current['close'] - sl_price
                tp_price = current['close'] + risk_distance * self.tp_rr_mult
                rr = (tp_price - current['close']) / risk_distance if risk_distance > 0 else 0
                if rr < self.min_risk_reward:
                    continue
                is_mitigated = ob.state == OBState.MITIGATED.value
                size = self.position_size * (self.mitigated_size_mult if is_mitigated else 1.0)
                self.ob_retest_counts[ob.index] = self.ob_retest_counts.get(ob.index, 0) + 1
                return {
                    'signal': 'LONG', 'sl': sl_price, 'tp': tp_price, 'size': size,
                    'ob_index': ob.index, 'ob_type': 'bullish',
                    'ob_state': 'mitigated' if is_mitigated else 'active',
                    'retest_count': self.ob_retest_counts[ob.index]
                }

        for ob in self.short_obs:
            if self.ob_retest_counts.get(ob.index, 0) >= self.max_retests:
                continue
            if current_idx - ob.index > self.max_age_bars:
                continue
            if current['high'] >= ob.bottom and current['low'] < ob.bottom:
                self.short_retest = True
                sl_price = ob.top + atr * self.sl_atr_mult
                risk_distance = sl_price - current['close']
                tp_price = current['close'] - risk_distance * self.tp_rr_mult
                rr = (current['close'] - tp_price) / risk_distance if risk_distance > 0 else 0
                if rr < self.min_risk_reward:
                    continue
                is_mitigated = ob.state == OBState.MITIGATED.value
                size = self.position_size * (self.mitigated_size_mult if is_mitigated else 1.0)
                self.ob_retest_counts[ob.index] = self.ob_retest_counts.get(ob.index, 0) + 1
                return {
                    'signal': 'SHORT', 'sl': sl_price, 'tp': tp_price, 'size': size,
                    'ob_index': ob.index, 'ob_type': 'bearish',
                    'ob_state': 'mitigated' if is_mitigated else 'active',
                    'retest_count': self.ob_retest_counts[ob.index]
                }

        return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}

    def get_stats(self):
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

    Inverts all order block signals:
    - Bullish OB retest -> SHORT (fade the support)
    - Bearish OB retest -> LONG (fade the resistance)
    """

    def __init__(self,
                 name: str = "OrderBlockStrategyInverse",
                 input_range: int = 25,
                 min_risk_reward: float = 1.5,
                 sl_atr_mult: float = 2.0,
                 tp_rr_mult: float = 2.0,
                 use_mitigated_blocks: bool = False,
                 first_retest_only: bool = True,
                 max_age_bars: int = 1000,
                 position_size: float = 0.5):

        super().__init__(
            name=name, input_range=input_range,
            min_risk_reward=min_risk_reward, sl_atr_mult=sl_atr_mult,
            tp_rr_mult=tp_rr_mult, use_mitigated_blocks=use_mitigated_blocks,
            first_retest_only=first_retest_only, max_age_bars=max_age_bars,
            position_size=position_size
        )

    def _check_entries(self, df, current, position):
        if PositionSide and position and position != PositionSide.FLAT:
            return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}

        atr = current.get('atr', current['close'] * 0.02)

        # Bullish OB retest -> SHORT (inverse)
        for ob in self.long_obs:
            if ob.state == OBState.ACTIVE.value:
                if current['low'] <= ob.top and current['high'] > ob.top:
                    self.long_retest = True
                    sl_price = ob.top + atr * self.sl_atr_mult
                    risk_distance = sl_price - current['close']
                    tp_price = current['close'] - risk_distance * self.tp_rr_mult
                    rr = (current['close'] - tp_price) / risk_distance if risk_distance > 0 else 0
                    if rr < self.min_risk_reward:
                        continue
                    return {
                        'signal': 'SHORT', 'sl': sl_price, 'tp': tp_price,
                        'size': self.position_size, 'ob_index': ob.index,
                        'ob_type': 'bullish', 'inverse': True
                    }

        # Bearish OB retest -> LONG (inverse)
        for ob in self.short_obs:
            if ob.state == OBState.ACTIVE.value:
                if current['high'] >= ob.bottom and current['low'] < ob.bottom:
                    self.short_retest = True
                    sl_price = ob.bottom - atr * self.sl_atr_mult
                    risk_distance = current['close'] - sl_price
                    tp_price = current['close'] + risk_distance * self.tp_rr_mult
                    rr = (tp_price - current['close']) / risk_distance if risk_distance > 0 else 0
                    if rr < self.min_risk_reward:
                        continue
                    return {
                        'signal': 'LONG', 'sl': sl_price, 'tp': tp_price,
                        'size': self.position_size, 'ob_index': ob.index,
                        'ob_type': 'bearish', 'inverse': True
                    }

        return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}
